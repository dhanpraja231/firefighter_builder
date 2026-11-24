import { useEffect, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { createFirefighter, createPerson, type FirefighterRig, type PersonRig } from "./models";
import { RUN, groundSpeed } from "./runCycle.js";

import type { CharacterVisual } from "./visual";
export type { CharacterKind, CharacterVisual } from "./visual";

/**
 * One agent's on-screen body. Purely presentational: the caller (a timeline
 * player) computes `position`/`heading`/`moving`/`utterance` every frame
 * from the event log and passes them in, the same contract INTEGRATION.md
 * describes for `PlaceholderWalker`. Mount as a child of `<Engine9Scene>`.
 *
 * Bodies are the `runcycle/` characters: robots are the firefighter PMX with
 * its procedural run cycle and leg IK, victims are Rocketbox mocap people.
 * The MMD loader was removed from three in r172, so a copy from r171 is
 * vendored in `./mmd/`.
 */
export function Character({
  position,
  heading = 0,
  visual,
  utterance,
  dimmed,
  moving = false,
  speed,
  smooth = false,
}: {
  position: [number, number, number];
  heading?: number;
  visual: CharacterVisual;
  utterance?: string | null;
  dimmed?: boolean;
  moving?: boolean;
  /** Ground speed in m/s. When given it replaces the speed measured from `position` changes, which is
   *  jittery if `position` only updates ~20x/s (the timeline replay). */
  speed?: number;
  /** Glide toward `position`/`heading` each frame instead of snapping, for low-rate position updates. */
  smooth?: boolean;
}) {
  const height = visual.height ?? (visual.kind === "robot" ? 1.8 : 1.7);
  const speaking = Boolean(utterance);
  const group = useRef<THREE.Group>(null);
  const placed = useRef(false);
  useFrame((_, delta) => {
    const g = group.current;
    if (!smooth || !g) return;
    const [tx, ty, tz] = position;
    const far = Math.hypot(g.position.x - tx, g.position.y - ty, g.position.z - tz) > 3.5;
    if (!placed.current || far) {
      g.position.set(tx, ty, tz);
      g.rotation.y = heading;
      placed.current = true;
      return;
    }
    g.position.x = THREE.MathUtils.damp(g.position.x, tx, 14, delta);
    g.position.y = THREE.MathUtils.damp(g.position.y, ty, 14, delta);
    g.position.z = THREE.MathUtils.damp(g.position.z, tz, 14, delta);
    const diff = Math.atan2(Math.sin(heading - g.rotation.y), Math.cos(heading - g.rotation.y));
    g.rotation.y += diff * (1 - Math.exp(-9 * delta));
  });
  return (
    <group
      ref={group}
      position={smooth ? undefined : position}
      rotation={smooth ? undefined : [0, heading, 0]}
      name={`char-${visual.label}`}
    >
      {visual.kind === "robot" ? (
        <FirefighterBody height={height} color={visual.color} dimmed={dimmed} moving={moving} position={position} speed={speed} />
      ) : (
        <PersonBody
          file={visual.model ?? "Female_Adult_02"}
          walkClip={visual.walkClip}
          height={height}
          dimmed={dimmed}
          moving={moving}
          position={position}
          speed={speed}
        />
      )}
      {/* Name tag only. Dialogue goes to the fixed caption bar instead of an in-world bubble:
          at this camera distance bubbles wrapped to a few characters per line and overlapped
          each other whenever two agents stood near one another. */}
      <Html position={[0, height + 0.32, 0]} center distanceFactor={9} zIndexRange={[100, 0]} sprite>
        <div style={labelStyle(visual.color, speaking)}>{visual.label}</div>
      </Html>
    </group>
  );
}

// ---------------------------------------------------------------- helpers

/** Horizontal speed (m/s) of `position` between frames, smoothed. */
function useGroundSpeed(position: [number, number, number]) {
  const last = useRef<THREE.Vector3 | null>(null);
  const speed = useRef(0);
  return (delta: number) => {
    const p = new THREE.Vector3(position[0], 0, position[2]);
    if (last.current && delta > 0) {
      const v = p.distanceTo(last.current) / delta;
      // ignore teleports (timeline scrubbing) and damp the rest
      if (v < 15) speed.current = THREE.MathUtils.damp(speed.current, v, 6, delta);
    }
    last.current = p;
    return speed.current;
  };
}

/** Fade every material on `root` in or out for rescued/lost characters. */
function applyDim(root: THREE.Object3D, dimmed: boolean | undefined) {
  const opacity = dimmed ? 0.35 : 1;
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const m of mats) {
      const mat = m as THREE.Material & { userData: { baseOpacity?: number; baseTransparent?: boolean } };
      mat.userData.baseOpacity ??= mat.opacity;
      mat.userData.baseTransparent ??= mat.transparent;
      mat.opacity = mat.userData.baseOpacity * opacity;
      mat.transparent = dimmed ? true : mat.userData.baseTransparent;
    }
  });
}

const _p = new THREE.Vector3();
/** Lowest of `bones`, in `model`'s parent space (before the model's own offset). */
function lowestY(bones: THREE.Object3D[], model: THREE.Object3D): number {
  model.updateMatrixWorld(true);
  const inv = new THREE.Matrix4().copy(model.matrixWorld).invert();
  let min = Infinity;
  for (const b of bones) {
    _p.setFromMatrixPosition(b.matrixWorld).applyMatrix4(inv);
    min = Math.min(min, _p.y);
  }
  return min * model.scale.y + model.position.y;
}

/** Clone every material on `root` so per-character tint/dimming doesn't leak to others. */
function ownMaterials(root: THREE.Object3D) {
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.material = Array.isArray(mesh.material) ? mesh.material.map((m) => m.clone()) : mesh.material.clone();
  });
}

// ---------------------------------------------------------------- robot

const FF_RUN_MPS_AT_1X = groundSpeed(RUN); // MMD units/s, converted in the rig

function FirefighterBody({
  height,
  color,
  dimmed,
  moving,
  position,
  speed,
}: {
  height: number;
  color: string;
  dimmed?: boolean;
  moving: boolean;
  position: [number, number, number];
  speed?: number;
}) {
  const [rig, setRig] = useState<FirefighterRig | null>(null);
  const holder = useRef<THREE.Group>(null);
  const measure = useGroundSpeed(position);

  useEffect(() => {
    let alive = true;
    createFirefighter(FF_RUN_MPS_AT_1X).then((r) => {
      if (!alive) return;
      ownMaterials(r.mesh);
      // light tint so the four robot roles are tellable apart
      const tint = new THREE.Color(color);
      r.mesh.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh) return;
        for (const m of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
          const c = (m as THREE.MeshPhongMaterial).color;
          if (c) c.lerp(tint, 0.18);
        }
      });
      setRig(r);
    });
    return () => {
      alive = false;
    };
  }, [color]);

  useEffect(() => {
    if (rig) applyDim(rig.mesh, dimmed);
  }, [rig, dimmed]);

  useFrame((_, delta) => {
    if (!rig) return;
    const measured = measure(delta);
    const v = speed ?? measured;
    // Play the run cycle at the rate that matches actual ground speed (feet don't slide);
    // when standing, freeze on a mid-stance frame instead of running in place.
    const rate = moving && v > 0.05 ? v / (rig.runSpeed * (height / 1.8)) : 0;
    rig.action.paused = rate === 0;
    rig.helper.update(Math.min(delta, 0.1) * rate);
  });

  if (!rig) return null;
  const s = rig.scale * (height / 1.8);
  return (
    <group ref={holder} scale={s}>
      <primitive object={rig.mesh} />
    </group>
  );
}

// ---------------------------------------------------------------- victim

const FADE = 0.25; // seconds to cross-fade idle <-> walk

function PersonBody({
  file,
  walkClip,
  height,
  dimmed,
  moving,
  position,
  speed,
}: {
  file: string;
  walkClip?: string;
  height: number;
  dimmed?: boolean;
  moving: boolean;
  position: [number, number, number];
  speed?: number;
}) {
  const [rig, setRig] = useState<PersonRig | null>(null);
  const [baseHeight, setBaseHeight] = useState(1.75);
  const measure = useGroundSpeed(position);
  const walkWeight = useRef(0);
  const feet = useRef<THREE.Object3D[]>([]);
  const restFootY = useRef(0);

  useEffect(() => {
    let alive = true;
    createPerson(file, walkClip).then((r) => {
      if (!alive) return;
      ownMaterials(r.model);
      r.model.updateMatrixWorld(true);
      const box = new THREE.Box3().setFromObject(r.model);
      setBaseHeight(box.max.y - box.min.y || 1.75);
      // foot bones + their bind-pose height, for per-frame grounding
      feet.current = [];
      r.model.traverse((o) => {
        if ((o as THREE.Bone).isBone && /_[LR]_(Foot|Toe0)$/.test(o.name)) feet.current.push(o);
      });
      restFootY.current = lowestY(feet.current, r.model);
      r.mixer.setTime(Math.random() * 2); // desync identical clips
      setRig(r);
    });
    return () => {
      alive = false;
    };
  }, [file, walkClip]);

  useEffect(() => {
    if (rig) applyDim(rig.model, dimmed);
  }, [rig, dimmed]);

  useFrame((_, delta) => {
    if (!rig) return;
    const dt = Math.min(delta, 0.1);
    const measured = measure(delta);
    const v = speed ?? measured;
    const scale = height / baseHeight;
    const walking = moving && v > 0.05;
    walkWeight.current = THREE.MathUtils.clamp(walkWeight.current + (walking ? dt : -dt) / FADE, 0, 1);
    rig.walk.weight = walkWeight.current;
    rig.idle.weight = 1 - walkWeight.current;
    // Walk clip speed follows actual ground speed so the steps match the distance covered.
    rig.walk.timeScale = walking ? THREE.MathUtils.clamp(v / (rig.walkSpeed * scale), 0.3, 2.5) : 1;
    rig.mixer.update(dt);
    // Grounding: clips retargeted from a different avatar (the child uses adult clips)
    // can leave the feet above or below the floor. Shift so the lowest foot bone sits at
    // its bind-pose height, as runcycle/main.js does.
    if (feet.current.length) {
      rig.model.position.y = 0;
      rig.model.updateMatrixWorld(true);
      rig.model.position.y = restFootY.current - lowestY(feet.current, rig.model);
    }
  });

  if (!rig) return null;
  return (
    <group scale={height / baseHeight}>
      <primitive object={rig.model} />
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
