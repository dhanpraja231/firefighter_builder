import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { MMDLoader } from 'three/addons/loaders/MMDLoader.js';
import { MMDAnimationHelper } from 'three/addons/animation/MMDAnimationHelper.js';
import { createRunClip, groundSpeed, RUN } from './runCycle.js';

const status = document.getElementById('status');

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1d2128);
scene.fog = new THREE.Fog(0x1d2128, 80, 220);

const camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(38, 18, 30);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 11, 0);
controls.enableDamping = true;
controls.update();

scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 2.2);
sun.position.set(20, 40, 25);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -20, right: 20, top: 30, bottom: -5, near: 1, far: 100 });
scene.add(sun);

// Scrolling ground: the model runs in place and the floor moves under it.
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

const helper = new MMDAnimationHelper({ afterglow: 0 });
const clock = new THREE.Clock();
let paused = false;
let timeScale = 1;
let mesh = null;

new MMDLoader().load(
  '/Firefighter.pmx',
  (m) => {
    mesh = m;
    // The model has no morphs; MMDLoader still adds empty morph arrays, which
    // makes three.js compile an invalid morph-target shader. Drop them.
    const ma = mesh.geometry.morphAttributes;
    for (const k of Object.keys(ma)) if (!ma[k].length) delete ma[k];
    if (!ma.position) {
      mesh.morphTargetInfluences = undefined;
      mesh.morphTargetDictionary = undefined;
    }
    mesh.castShadow = true;
    scene.add(mesh);
    const clip = createRunClip(mesh);
    helper.add(mesh, { animation: clip, physics: false });
    status.textContent = 'Space: pause   ↑/↓: speed   drag: orbit';
    window.__run = { mesh, helper, clip }; // for debugging in the console
  },
  (xhr) => {
    if (xhr.total) status.textContent = `Loading model… ${Math.round((xhr.loaded / xhr.total) * 100)}%`;
  },
  (err) => {
    status.textContent = 'Failed to load /Firefighter.pmx — see console';
    console.error(err);
  },
);

window.addEventListener('keydown', (e) => {
  if (e.code === 'Space') paused = !paused;
  if (e.code === 'ArrowUp') timeScale = Math.min(2, timeScale + 0.1);
  if (e.code === 'ArrowDown') timeScale = Math.max(0.1, timeScale - 0.1);
});

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

const speed = groundSpeed(RUN);
renderer.setAnimationLoop(() => {
  const raw = clock.getDelta();
  const dt = paused ? 0 : raw * timeScale;
  if (mesh) {
    helper.update(dt);
    ground.position.z = (ground.position.z - speed * dt) % CELL;
  }
  controls.update();
  renderer.render(scene, camera);
});
