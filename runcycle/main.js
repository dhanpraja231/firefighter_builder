import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { MMDLoader } from 'three/addons/loaders/MMDLoader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { MMDAnimationHelper } from 'three/addons/animation/MMDAnimationHelper.js';
import { createRunClip, groundSpeed, RUN } from './runCycle.js';

// Models outside the Vite public dir, resolved to dev-server URLs.
const victimUrl = (name) => new URL(`../models/victims/${name}.glb`, import.meta.url).href;
const CAT_URL = new URL('../models/animals/Cat.fbx', import.meta.url).href;

// Cast (SPEC.md sections 4 and 5). All firefighter roles share the PMX.
const FIREFIGHTERS = ['scout-1', 'suppression-1', 'rescue-1', 'commander'];
const VICTIMS = [
  { id: 'victim-1 (elderly)', file: 'OldClassy_Female', height: 0.9 },
  { id: 'victim-2 (panicked)', file: 'Casual_Male', height: 0.97 },
  { id: 'victim-3 (injured)', file: 'Worker_Female', height: 0.93 },
  { id: 'victim-4 (stubborn)', file: 'Suit_Male', height: 0.98 },
  { id: 'spare', file: 'OldClassy_Male', height: 0.93 },
  { id: 'spare', file: 'Casual_Female', height: 0.93 },
  { id: 'spare', file: 'Casual_Bald', height: 0.97 },
];

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

  // Victims: second row behind the firefighters, each running with its own clip.
  const victimSpacing = 8;
  await Promise.all(
    VICTIMS.map(async (v, i) => {
      const g = await gltf.loadAsync(victimUrl(v.file));
      const root = new THREE.Group();
      root.add(g.scene);
      fitHeight(g.scene, ffHeight * v.height);
      enableShadows(g.scene);
      root.position.set((i - (VICTIMS.length - 1) / 2) * victimSpacing, 0, -16);
      scene.add(root);
      const mixer = new THREE.AnimationMixer(g.scene);
      const clip = pickClip(g.animations, /^Run$/, /Run/, /Walk/);
      mixer.clipAction(clip).play();
      mixer.setTime(i * 0.17);
      mixers.push(mixer);
      addLabel(root, `${v.id} · ${v.file}`, ffHeight * v.height + 1.5, '#9fd3ff');
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
  window.__cast = { helper, mixers, scene }; // for debugging in the console
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
    ground.position.z = (ground.position.z - speed * dt) % CELL;
  }
  controls.update();
  renderer.render(scene, camera);
  labelRenderer.render(scene, camera);
});
