import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";
import type { AgentFrame, AnimName } from "../../timeline/replay";
import { MODEL_URLS, type CharacterVisual } from "./visual";

/**
 * Which clip(s) in the Quaternius rigs play for each body state, first match wins. Missing clips
 * (Casual_Bald has no Run) fall through to the next name, so every state works on every rig.
 */
const CLIPS: Record<AnimName, { names: string[]; once?: boolean }> = {
  idle: { names: ["Idle"] },
  walk: { names: ["Walk"] },
  run: { names: ["Run", "Walk"] },
  carry: { names: ["Walk_Carry", "Walk"] },
  flinch: { names: ["RecieveHit"], once: true },
  collapse: { names: ["Death"], once: true },
  celebrate: { names: ["Victory"], once: true },
  pickup: { names: ["PickUp"], once: true },
  sit: { names: ["SitDown"], once: true },
  plead: { names: ["Defeat"], once: true },
  argue: { names: ["Defeat"], once: true },
};

/** Ground speed (m/s) a clip looks right at 1x, so feet don't skate. */
const NOMINAL_SPEED: Partial<Record<AnimName, number>> = { walk: 1.3, carry: 1.2, run: 3.0 };

const FADE_SECONDS = 0.25;
/** After a pose change, keep animating this long even when playback is paused, so scrubbing to a moment shows the finished pose. */
const SETTLE_SECONDS = 2.8;
const SNAP_DISTANCE = 3.5; // meters: larger jumps (scrubbing, floor changes on seek) teleport instead of gliding

interface Built {
  holder: THREE.Group;
  mixer: THREE.AnimationMixer;
  clips: Map<string, THREE.AnimationClip>;
}

/** The rigs ship with a near-black skin material; give each person a natural, varied tone instead. */
const SKIN_TONES = ["#f1c9a5", "#e0ac84", "#c68e63", "#a9714b", "#8a5a3a", "#6f4429"];

function skinFor(label: string): THREE.Color {
  let h = 0;
  for (const ch of label) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return new THREE.Color(SKIN_TONES[h % SKIN_TONES.length]);
}

/** Cloned rig, tinted outfit, scaled to the persona's height with its feet on y = 0. */
function build(gltf: { scene: THREE.Object3D; animations: THREE.AnimationClip[] }, visual: CharacterVisual): Built {
  const root = cloneSkinned(gltf.scene);
  const tint = new THREE.Color(visual.color);
  const skin = skinFor(visual.label);

  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.castShadow = true;
    mesh.frustumCulled = false; // skinned bounds are the bind pose; animated limbs would pop out of view
    const recolor = (mat: THREE.Material) => {
      const copy = mat.clone(); // clones share materials; tinting one agent must not tint the others
      const named = copy as THREE.MeshStandardMaterial;
      if (/^(shirt|vest|hat)$/i.test(copy.name) && named.color) named.color.copy(tint);
      if (/^skin$/i.test(copy.name) && named.color) named.color.copy(skin);
      // The helmet replaces the hair/hat volume so it doesn't poke through the dome.
      if (visual.helmet && /^(hair|hat)$/i.test(copy.name)) copy.visible = false;
      // A little self-illumination so people stay readable in the dark street and smoky rooms.
      if (named.emissive && named.color) named.emissive.copy(named.color).multiplyScalar(0.22);
      return copy;
    };
    mesh.material = Array.isArray(mesh.material) ? mesh.material.map(recolor) : recolor(mesh.material);
  });

  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root, true);
  const naturalHeight = Math.max(box.max.y - box.min.y, 1e-3);
  const scale = (visual.height ?? 1.7) / naturalHeight;

  const holder = new THREE.Group();
  holder.scale.setScalar(scale);
  root.position.y -= box.min.y; // feet on the ground
  holder.add(root);
  holder.updateMatrixWorld(true);

  if (visual.helmet) addHelmet(root, tint);

  const clips = new Map(gltf.animations.map((clip) => [clip.name, clip]));
  return { holder, mixer: new THREE.AnimationMixer(root), clips };
}

/** A hard hat on the Head bone, sized in world meters regardless of the rig's internal scale. */
function addHelmet(root: THREE.Object3D, color: THREE.Color) {
  const head = root.getObjectByName("Head");
  if (!head) return;
  const world = new THREE.Vector3();
  head.getWorldScale(world);
  const k = 1 / Math.max(world.x, 1e-6);
  const radius = 0.36 * k; // chibi heads are big: ~0.6 m across in the rig's 1.8 m body

  const helmet = new THREE.Group();
  const shell = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshStandardMaterial({ color, roughness: 0.35, metalness: 0.1 }),
  );
  const brim = new THREE.Mesh(
    new THREE.CylinderGeometry(radius * 1.18, radius * 1.18, radius * 0.08, 20),
    new THREE.MeshStandardMaterial({ color, roughness: 0.4 }),
  );
  helmet.add(shell, brim);
  // The Head bone's origin is the neck (~1.2 m up); the head's crown line is ~0.22 m above it.
  helmet.position.set(0, 0.22 * k, 0.01 * k);
  head.add(helmet);
}

function findClip(clips: Map<string, THREE.AnimationClip>, names: string[]): THREE.AnimationClip | undefined {
  for (const name of names) {
    const clip = clips.get(name);
    if (clip) return clip;
  }
  return undefined;
}

/**
 * One agent's on-screen body: a rigged character that plays real clips (idle, walk, run, carry,
 * flinch, collapse, celebrate, pick up, sit, plead) chosen from the replay frame, crossfading between
 * them. Purely presentational -- position, facing and pose all come from `frame`, which the timeline
 * player derives from the event log. Mount as a child of `<Engine9Scene>`.
 */
export function RiggedCharacter({
  visual,
  frame,
  paused = false,
}: {
  visual: CharacterVisual;
  frame: AgentFrame;
  paused?: boolean;
}) {
  const gltf = useGLTF(MODEL_URLS[visual.model]);
  const built = useMemo(() => build(gltf, visual), [gltf, visual]);
  const group = useRef<THREE.Group>(null);
  const current = useRef<THREE.AnimationAction | null>(null);
  const placed = useRef(false);
  const changedAt = useRef(performance.now() / 1000);
  const height = visual.height ?? 1.7;

  // Crossfade whenever the requested animation (or its restart key) changes.
  useEffect(() => {
    const spec = CLIPS[frame.anim];
    const clip = findClip(built.clips, spec.names);
    if (!clip) return;
    const next = built.mixer.clipAction(clip);
    const prev = current.current;
    next.reset();
    next.enabled = true;
    next.setLoop(spec.once ? THREE.LoopOnce : THREE.LoopRepeat, Infinity);
    next.clampWhenFinished = Boolean(spec.once); // hold the final pose (collapsed, seated) instead of snapping to T-pose
    next.setEffectiveWeight(1);
    if (prev && prev !== next) next.crossFadeFrom(prev, FADE_SECONDS, false);
    next.play();
    current.current = next;
    changedAt.current = performance.now() / 1000;
  }, [built, frame.anim, frame.animKey]);

  // Match walk/run playback rate to the distance actually covered so feet don't skate.
  useEffect(() => {
    const action = current.current;
    if (!action) return;
    const nominal = NOMINAL_SPEED[frame.anim];
    action.setEffectiveTimeScale(nominal ? THREE.MathUtils.clamp(frame.speed / nominal, 0.6, 1.8) : 1);
  }, [built, frame.anim, frame.animKey, frame.speed]);

  useEffect(() => () => void built.mixer.stopAllAction(), [built]);

  useFrame(({ clock }, delta) => {
    const settling = performance.now() / 1000 - changedAt.current < SETTLE_SECONDS;
    built.mixer.update(paused && !settling ? 0 : delta);
    const g = group.current;
    if (!g) return;

    // The replay updates ~20x per second; glide between samples so motion is smooth at display rate.
    const [tx, ty, tz] = frame.position;
    const far = Math.hypot(g.position.x - tx, g.position.y - ty, g.position.z - tz) > SNAP_DISTANCE;
    if (!placed.current || far) {
      g.position.set(tx, ty, tz);
      g.rotation.y = frame.heading;
      placed.current = true;
    } else {
      g.position.x = THREE.MathUtils.damp(g.position.x, tx, 14, delta);
      g.position.y = THREE.MathUtils.damp(g.position.y, ty, 14, delta);
      g.position.z = THREE.MathUtils.damp(g.position.z, tz, 14, delta);
      const diff = Math.atan2(Math.sin(frame.heading - g.rotation.y), Math.cos(frame.heading - g.rotation.y));
      g.rotation.y += diff * (1 - Math.exp(-9 * delta));
    }

    // Talking: a small body sway on top of whatever clip is playing.
    const t = clock.elapsedTime;
    const talk = frame.speaking && !paused ? 1 : 0;
    built.holder.rotation.z = THREE.MathUtils.damp(built.holder.rotation.z, talk * Math.sin(t * 9) * 0.035, 10, delta);
  });

  return (
    <group ref={group} name={`char-${visual.label}`}>
      <primitive object={built.holder} />
      <Html position={[0, height + 0.32, 0]} center distanceFactor={9} zIndexRange={[100, 0]} sprite>
        <div style={labelStyle(visual.color, frame.speaking)}>{visual.label}</div>
      </Html>
    </group>
  );
}

/** `speaking` highlights whoever the caption bar is currently quoting. */
function labelStyle(color: string, speaking: boolean): React.CSSProperties {
  return {
    padding: "2px 8px",
    borderRadius: 4,
    background: speaking ? color : "rgba(5,6,10,0.92)",
    border: `1px solid ${color}`,
    color: speaking ? "#05060a" : color,
    fontSize: 12,
    fontWeight: 700,
    fontFamily: "monospace",
    whiteSpace: "nowrap",
    boxShadow: speaking ? `0 0 12px ${color}` : "none",
  };
}
