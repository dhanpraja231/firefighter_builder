import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { MMDLoader } from 'three/addons/loaders/MMDLoader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { MMDAnimationHelper } from 'three/addons/animation/MMDAnimationHelper.js';
import { createRunClip, groundSpeed, RUN } from './runCycle.js';
import { createFootLock, calibrate, updateFootLock } from './footIK.js';

// Models outside the Vite public dir, resolved to dev-server URLs.
const personUrl = (name) => new URL(`../models/people/${name}.glb`, import.meta.url).href;
const CAT_URL = new URL('../models/animals/Cat.fbx', import.meta.url).href;

// Cast (SPEC.md sections 4 and 5). All firefighter roles share the PMX.
// Victims are Microsoft Rocketbox avatars (real-world proportions, meters) built by
// models/tools/build_people.sh; `clip` is one of the clips baked into each GLB.
const FIREFIGHTERS = ['scout-1', 'suppression-1', 'rescue-1', 'commander'];
const VICTIMS = [
  { id: 'victim-1 (elderly)', file: 'Female_Adult_01', clip: 'f_run_neutral' },
  { id: 'victim-2 (panicked)', file: 'Male_Adult_01', clip: 'm_run_fast_01' },
  { id: 'victim-3 (injured)', file: 'Female_Adult_02', clip: 'f_run_injured' },
  { id: 'victim-4 (stubborn)', file: 'Business_Male_01', clip: 'm_run_slow_01' },
  { id: 'spare', file: 'Male_Adult_02', clip: 'm_run_neutral' },
  { id: 'spare', file: 'Business_Female_01', clip: 'f_run_neutral' },
];
// Assumed real height of the firefighter model, used to convert meters to MMD units.
const FIREFIGHTER_METERS = 1.8;

// Rocketbox clips carry root motion: the root bone drifts forward over the clip.
// Subtract that linear drift from the root position track (keeps the bob and sway,
// makes the loop seamless) and return the drift in world space per clip-second.
// `model` must already be scaled and in the scene graph.
function inPlace(clip, model) {
  // The root motion lives on the "Bip01" armature node (not a Bone in three.js).
  const rootBone = model.getObjectByName('Bip01');
  const track = rootBone && clip.tracks.find((t) => t.name === 'Bip01.position');
  if (!track) return new THREE.Vector3();
  const v = track.values;
  const t = track.times;
  const n = t.length;
  const d = new THREE.Vector3(v[3 * n - 3] - v[0], v[3 * n - 2] - v[1], v[3 * n - 1] - v[2]);
  const span = t[n - 1] - t[0];
  for (let i = 0; i < n; i++) {
    const k = (t[i] - t[0]) / span;
    v[3 * i] -= d.x * k;
    v[3 * i + 1] -= d.y * k;
    v[3 * i + 2] -= d.z * k;
  }
  // bone-local drift -> world drift (parent is the armature node with scale/rotation)
  model.updateMatrixWorld(true);
  const world = d.applyMatrix4(new THREE.Matrix4().extractRotation(rootBone.parent.matrixWorld));
  world.multiplyScalar(rootBone.parent.getWorldScale(new THREE.Vector3()).x);
  world.y = 0;
  return world.divideScalar(span);
}

// Lowest point of a set of bones, in the model root's space.
const _p = new THREE.Vector3();
function lowestY(bones, root) {
  let min = Infinity;
  for (const b of bones) {
    _p.setFromMatrixPosition(b.matrixWorld);
    root.worldToLocal(_p);
    if (_p.y < min) min = _p.y;
  }
  return min;
}

// Foot grounding for the mocap people: after the mixer poses the skeleton, shift the
// whole model vertically so the lowest foot bone sits at its bind-pose height. This
// stops feet sinking into or floating above the floor when clip and avatar differ.
const grounded = [];

const status = document.getElementById('status');

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

const labelRenderer = new CSS2DRenderer();
labelRenderer.setSize(window.innerWidth, window.innerHeight);
labelRenderer.domElement.style.cssText = 'position:fixed;top:0;left:0;pointer-events:none';
document.body.appendChild(labelRenderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1d2128);
scene.fog = new THREE.Fog(0x1d2128, 120, 300);

const camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(70, 32, 60);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 9, -4);
controls.enableDamping = true;
controls.update();

scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 2.2);
sun.position.set(20, 40, 25);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -45, right: 45, top: 45, bottom: -30, near: 1, far: 120 });
scene.add(sun);

// Scrolling ground: everyone runs in place and the floor moves under them.
const CELL = 5;
const ground = new THREE.Group();
const floor = new THREE.Mesh(
  new THREE.PlaneGeometry(400, 400),
  new THREE.MeshStandardMaterial({ color: 0x2c323c, roughness: 0.95 }),
);
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
ground.add(floor);
const grid = new THREE.GridHelper(400, 400 / CELL, 0x5a6575, 0x3a424e);
grid.position.y = 0.01;
ground.add(grid);
scene.add(ground);

function addLabel(obj, text, height, color) {
  const div = document.createElement('div');
  div.textContent = text;
  div.style.cssText = `font:11px monospace;color:${color};background:rgba(0,0,0,.55);padding:1px 5px;border-radius:3px`;
  const label = new CSS2DObject(div);
  label.position.set(0, height, 0);
  obj.add(label);
}

function enableShadows(root) {
  root.traverse((o) => {
    if (o.isMesh) o.castShadow = true;
  });
}

// Uniformly scale `root` so its bounding-box height is `target`, feet on y = 0.
function fitHeight(root, target) {
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  const s = target / (box.max.y - box.min.y);
  root.scale.multiplyScalar(s);
  root.position.y -= box.min.y * s;
}

// Prefer the first clip whose name matches, otherwise the first clip.
function pickClip(clips, ...patterns) {
  for (const re of patterns) {
    const c = clips.find((x) => re.test(x.name));
    if (c) return c;
  }
  return clips[0];
}

const helper = new MMDAnimationHelper({ afterglow: 0 });
const mixers = [];
const clock = new THREE.Clock();
let paused = false;
let timeScale = 1;
let ready = false;

async function loadFirefighter(loader) {
  const mesh = await loader.loadAsync('/Firefighter.pmx');
  // The model has no morphs; MMDLoader still adds empty morph arrays, which
  // makes three.js compile an invalid morph-target shader. Drop them.
  const ma = mesh.geometry.morphAttributes;
  for (const k of Object.keys(ma)) if (!ma[k].length) delete ma[k];
  if (!ma.position) {
    mesh.morphTargetInfluences = undefined;
    mesh.morphTargetDictionary = undefined;
  }
  mesh.castShadow = true;
  return mesh;
}

async function main() {
  const mmd = new MMDLoader();
  const gltf = new GLTFLoader();
  const fbx = new FBXLoader();
  let done = 0;
  const total = FIREFIGHTERS.length + VICTIMS.length + 1;
  const tick = () => (status.textContent = `Loading models… ${++done}/${total}`);

  // Firefighters: front row. Load sequentially so the clip is built on a rest-pose mesh.
  let ffHeight = 20;
  const spacing = 11;
  for (const [i, id] of FIREFIGHTERS.entries()) {
    const mesh = await loadFirefighter(mmd);
    mesh.position.x = (i - (FIREFIGHTERS.length - 1) / 2) * spacing;
    scene.add(mesh);
    mesh.updateMatrixWorld(true);
    if (i === 0) {
      const box = new THREE.Box3().setFromObject(mesh);
      ffHeight = box.max.y - box.min.y;
    }
    helper.add(mesh, { animation: createRunClip(mesh), physics: false });
    // stagger the cycle so the four don't run in perfect lockstep
    helper.objects.get(mesh).mixer.setTime((i * 0.23 * RUN.period) % RUN.period);
    addLabel(mesh, id, ffHeight + 1.5, '#ffb347');
    tick();
  }

  // Victims: second row behind the firefighters. Models are in meters, so one uniform
  // scale keeps their real heights relative to the firefighter.
  const unitsPerMeter = ffHeight / FIREFIGHTER_METERS;
  const groundUnitsPerSec = groundSpeed(RUN);
  const victimSpacing = 9;
  await Promise.all(
    VICTIMS.map(async (v, i) => {
      const g = await gltf.loadAsync(personUrl(v.file));
      const model = g.scene;
      model.scale.setScalar(unitsPerMeter);
      enableShadows(model);
      model.traverse((o) => {
        if (o.isMesh) o.frustumCulled = false; // skinned bounds don't follow the animation
      });
      const root = new THREE.Group();
      root.add(model);
      root.position.set((i - (VICTIMS.length - 1) / 2) * victimSpacing, 0, -16);
      scene.add(root);

      // bind-pose foot height, before any animation is applied
      const feet = [];
      model.traverse((o) => {
        if (o.isBone && /(^|_)[LR]_Toe0$|(^|_)[LR]_Foot$/.test(o.name)) feet.push(o);
      });
      root.updateMatrixWorld(true);
      const restFootY = lowestY(feet, root);

      const clip = g.animations.find((c) => c.name === v.clip) ?? pickClip(g.animations, /run/i, /walk/i);
      const drift = inPlace(clip, model); // world units per clip-second
      // face the direction the clip was travelling in, mapped onto +Z (the firefighters' forward)
      model.rotation.y = -Math.atan2(drift.x, drift.z);
      const mixer = new THREE.AnimationMixer(model);
      mixer.clipAction(clip).play();
      // Play the clip at the rate where its planted foot already moves at floor speed,
      // so the foot lock below only has small corrections to make.
      const rig = createFootLock(root, model);
      const stance = rig ? calibrate(rig, mixer, clip) : 0;
      const speed = stance > 1e-3 ? stance : drift.length();
      mixer.timeScale = speed > 1e-3 ? groundUnitsPerSec / speed : 1;
      mixer.setTime(i * 0.13);
      mixers.push(mixer);
      grounded.push({ root, model, feet, restFootY, rig, mixer });

      const height = new THREE.Box3().setFromObject(model).max.y;
      addLabel(root, `${v.id} · ${v.file}`, height + 1.5, '#9fd3ff');
      tick();
    }),
  );

  // Cat: runs out in front of the group.
  const cat = await fbx.loadAsync(CAT_URL);
  const catRoot = new THREE.Group();
  catRoot.add(cat);
  fitHeight(cat, ffHeight * 0.18);
  enableShadows(cat);
  catRoot.position.set(0, 0, 14);
  scene.add(catRoot);
  console.log('Cat clips:', cat.animations.map((c) => c.name));
  if (cat.animations.length) {
    const mixer = new THREE.AnimationMixer(cat);
    mixer.clipAction(pickClip(cat.animations, /run/i, /gallop/i, /walk/i)).play();
    mixers.push(mixer);
  }
  addLabel(catRoot, 'cat', ffHeight * 0.18 + 1, '#c8f7c5');
  tick();

  ready = true;
  status.textContent = 'Space: pause   ↑/↓: speed   drag: orbit';
  window.__cast = { helper, mixers, scene, grounded, camera, controls }; // for debugging in the console
}

main().catch((err) => {
  status.textContent = 'Failed to load models — see console';
  console.error(err);
});

window.addEventListener('keydown', (e) => {
  if (e.code === 'Space') paused = !paused;
  if (e.code === 'ArrowUp') timeScale = Math.min(2, timeScale + 0.1);
  if (e.code === 'ArrowDown') timeScale = Math.max(0.1, timeScale - 0.1);
});

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  labelRenderer.setSize(window.innerWidth, window.innerHeight);
});

const speed = groundSpeed(RUN);
renderer.setAnimationLoop(() => {
  const raw = clock.getDelta();
  const dt = paused ? 0 : raw * timeScale;
  if (ready) {
    helper.update(dt);
    for (const m of mixers) m.update(dt);
    for (const g of grounded) {
      g.model.position.y = 0;
      g.root.updateMatrixWorld(true);
      g.model.position.y = g.restFootY - lowestY(g.feet, g.root);
      if (g.rig && dt > 0) updateFootLock(g.rig, dt, speed);
    }
    ground.position.z = (ground.position.z - speed * dt) % CELL;
  }
  controls.update();
  renderer.render(scene, camera);
  labelRenderer.render(scene, camera);
});
