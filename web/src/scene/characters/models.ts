import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { clone as cloneSkinned } from "three/addons/utils/SkeletonUtils.js";
// Vendored from three r171 (removed upstream in r172), see ./mmd/README.md.
import { MMDLoader } from "./mmd/MMDLoader.js";
import { MMDAnimationHelper } from "./mmd/MMDAnimationHelper.js";
import { createRunClip } from "./runCycle.js";

/**
 * Model loading for the character bodies from `runcycle/`:
 *  - every firefighter robot role uses `pmx/Firefighter.pmx`,
 *  - victims use the Microsoft Rocketbox GLBs from `models/people/` (copied to `public/people/`).
 * Both are scaled to meters so they drop straight into the Engine 9 coordinate system.
 */

export const FIREFIGHTER_URL = "/pmx/Firefighter.pmx";
export const personUrl = (file: string) => `/people/${file}.glb`;

/** Real-world height the firefighter PMX is scaled to, meters. */
export const FIREFIGHTER_HEIGHT = 1.8;

// ---------------------------------------------------------------- firefighter

export interface FirefighterRig {
  mesh: THREE.SkinnedMesh;
  helper: InstanceType<typeof MMDAnimationHelper>;
  /** MMD units -> meters */
  scale: number;
  /** run speed of the clip in meters per second at timeScale 1 */
  runSpeed: number;
  action: THREE.AnimationAction;
}

export async function createFirefighter(runSpeedMmd: number): Promise<FirefighterRig> {
  // Each firefighter needs its own skeleton and IK solver, so the file is parsed per
  // instance (the browser cache makes repeat downloads free). MMD meshes can't be
  // cloned with SkeletonUtils because the IK/grant data lives on the geometry.
  const mesh = (await new MMDLoader().loadAsync(FIREFIGHTER_URL)) as THREE.SkinnedMesh;
  // MMDLoader adds empty morph arrays on a model with no morphs, which compiles an
  // invalid morph-target shader. Drop them (same fix as runcycle/main.js).
  const ma = mesh.geometry.morphAttributes as Record<string, unknown[]>;
  for (const k of Object.keys(ma)) if (!ma[k].length) delete ma[k];
  if (!ma.position) {
    mesh.morphTargetInfluences = undefined;
    mesh.morphTargetDictionary = undefined;
  }
  mesh.castShadow = true;
  mesh.frustumCulled = false;

  mesh.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(mesh);
  const scale = FIREFIGHTER_HEIGHT / (box.max.y - box.min.y);

  const helper = new MMDAnimationHelper({ afterglow: 0 });
  const clip = createRunClip(mesh); // must be built on the rest pose
  helper.add(mesh, { animation: clip, physics: false });
  const action = helper.objects.get(mesh)!.mixer.existingAction(clip)!;
  return { mesh, helper, scale, runSpeed: runSpeedMmd * scale, action };
}

// ---------------------------------------------------------------- people

interface PersonSource {
  scene: THREE.Group;
  animations: THREE.AnimationClip[];
  /** forward speed of each clip's root motion, meters per clip-second */
  speeds: Record<string, number>;
}

const personCache = new Map<string, Promise<PersonSource>>();

function loadPerson(file: string): Promise<PersonSource> {
  let p = personCache.get(file);
  if (!p) {
    p = new GLTFLoader().loadAsync(personUrl(file)).then((g) => {
      const speeds: Record<string, number> = {};
      for (const clip of g.animations) speeds[clip.name] = stripRootMotion(clip, g.scene);
      return { scene: g.scene, animations: g.animations, speeds };
    });
    personCache.set(file, p);
  }
  return p;
}

/**
 * Rocketbox clips move the `Bip01` root forward. Remove the linear drift (keeps the
 * bob and sway, loops seamlessly) and return its horizontal speed in meters per
 * clip-second. Same approach as `inPlace()` in runcycle/main.js.
 */
function stripRootMotion(clip: THREE.AnimationClip, scene: THREE.Object3D): number {
  const track = clip.tracks.find((t) => t.name === "Bip01.position");
  const root = scene.getObjectByName("Bip01");
  if (!track || !root) return 0;
  const v = track.values;
  const t = track.times;
  const n = t.length;
  const d = new THREE.Vector3(v[3 * n - 3] - v[0], v[3 * n - 2] - v[1], v[3 * n - 1] - v[2]);
  const span = t[n - 1] - t[0];
  if (span <= 0) return 0;
  for (let i = 0; i < n; i++) {
    const k = (t[i] - t[0]) / span;
    v[3 * i] -= d.x * k;
    v[3 * i + 1] -= d.y * k;
    v[3 * i + 2] -= d.z * k;
  }
  scene.updateMatrixWorld(true);
  d.applyMatrix4(new THREE.Matrix4().extractRotation(root.parent!.matrixWorld));
  d.multiplyScalar(root.parent!.getWorldScale(new THREE.Vector3()).x);
  d.y = 0;
  return d.length() / span;
}

export interface PersonRig {
  model: THREE.Object3D;
  mixer: THREE.AnimationMixer;
  walk: THREE.AnimationAction;
  idle: THREE.AnimationAction;
  /** meters per second the walk clip covers at timeScale 1 */
  walkSpeed: number;
}

export async function createPerson(file: string, walkClip?: string): Promise<PersonRig> {
  const src = await loadPerson(file);
  const model = cloneSkinned(src.scene);
  model.traverse((o) => {
    if ((o as THREE.Mesh).isMesh) {
      o.castShadow = true;
      o.frustumCulled = false; // skinned bounds don't follow the animation
    }
  });
  const mixer = new THREE.AnimationMixer(model);
  const find = (re: RegExp) => src.animations.find((c) => re.test(c.name));
  const walkC =
    (walkClip && src.animations.find((c) => c.name === walkClip)) || find(/_walk_neutral/) || find(/walk/) || src.animations[0];
  const idleC = find(/idle/) ?? walkC;
  const walk = mixer.clipAction(walkC);
  const idle = mixer.clipAction(idleC);
  walk.play();
  idle.play();
  walk.weight = 0;
  idle.weight = 1;
  return { model, mixer, walk, idle, walkSpeed: src.speeds[walkC.name] || 1.3 };
}
