import * as THREE from 'three';

// Procedural run cycle for the Firefighter PMX (standard MMD bone names).
//
// Three.js MMD conventions (after MMDLoader's left->right handed conversion):
//   model faces +Z, up is +Y, the model's left side is +X.
//   every bone has an identity rest rotation, so rotations are expressed
//   in the model's axes at rest.
// Legs are driven through the foot IK bones; arms and torso are FK.

export const RUN = {
  period: 0.72,        // seconds per full cycle (two steps)
  stance: 0.36,        // fraction of the cycle each foot is on the ground
  strideHalf: 3.6,     // MMD units the foot travels fore/aft of its rest spot (1 unit = 8 cm)
  footLift: 3.8,       // peak foot height in swing
  hipDrop: 1.0,        // how much the center sits down to bend the knees
  bob: 0.45,           // vertical bounce amplitude
  lean: THREE.MathUtils.degToRad(11),
  twist: THREE.MathUtils.degToRad(9),
  armSwing: THREE.MathUtils.degToRad(42),
  armTuck: THREE.MathUtils.degToRad(14),   // target upper-arm angle away from the body
  elbowBend: THREE.MathUtils.degToRad(85),
  samples: 60,
};

// ground speed during stance, so planted feet don't slide
export function groundSpeed(p = RUN) {
  return (2 * p.strideHalf) / (p.stance * p.period);
}

const smooth = (t) => t * t * (3 - 2 * t);
const TAU = Math.PI * 2;

// Foot offset (relative to the IK bone's rest position) and pitch for phase 0..1.
// Phase 0 = foot touches down in front.
function foot(phase, p) {
  const ph = ((phase % 1) + 1) % 1;
  if (ph < p.stance) {
    const u = ph / p.stance;
    const z = p.strideHalf * (1 - 2 * u);
    // roll onto the toes in the last third of stance
    const roll = u > 0.65 ? smooth((u - 0.65) / 0.35) * 0.55 : 0;
    // land slightly heel-first, then flatten
    const land = u < 0.15 ? -0.18 * (1 - smooth(u / 0.15)) : 0;
    return { y: 0, z, pitch: roll + land };
  }
  const u = (ph - p.stance) / (1 - p.stance);
  // heel kicks up and back early, then the foot reaches forward for the next contact
  const y = p.footLift * Math.sin(Math.PI * Math.pow(u, 0.75));
  const z = -p.strideHalf + 2 * p.strideHalf * smooth(Math.min(1, u * 1.08));
  // toes pointed after push-off, flatten / slightly flex before landing
  const pitch = 0.55 * (1 - smooth(Math.min(1, u * 1.6))) - 0.18 * smooth(Math.max(0, (u - 0.6) / 0.4));
  return { y, z, pitch };
}

function boneByName(mesh, name) {
  const b = mesh.skeleton.bones.find((x) => x.name === name);
  if (!b) throw new Error(`bone not found: ${name}`);
  return b;
}

function worldRest(mesh, name) {
  const b = boneByName(mesh, name);
  const v = new THREE.Vector3();
  b.getWorldPosition(v);
  return mesh.worldToLocal(v);
}

// Elbow hinge: axis perpendicular to the upper arm, oriented so a positive bend
// moves the forearm forward (+Z).
function elbowAxis(dir) {
  const axis = new THREE.Vector3().crossVectors(dir, new THREE.Vector3(0, 0, 1)).normalize();
  const test = dir.clone().applyAxisAngle(axis, 0.3);
  if (test.z < 0) axis.negate();
  return axis;
}

/** Build a looping AnimationClip for the given MMD mesh (must be in rest pose). */
export function createRunClip(mesh, p = RUN) {
  mesh.updateMatrixWorld(true);
  const n = p.samples;
  const times = new Float32Array(n + 1);
  for (let i = 0; i <= n; i++) times[i] = (i / n) * p.period;

  const quatTracks = {};
  const posTracks = {};
  const q = (name) => (quatTracks[name] ??= new Float32Array((n + 1) * 4));
  const v = (name) => (posTracks[name] ??= new Float32Array((n + 1) * 3));

  const rest = (name) => boneByName(mesh, name).position.clone();

  // arm geometry from the rest pose
  const arms = {};
  for (const [s, sx] of [['左', 1], ['右', -1]]) {
    const sh = worldRest(mesh, s + '腕');
    const el = worldRest(mesh, s + 'ひじ');
    const wr = worldRest(mesh, s + '手首');
    const upper = el.clone().sub(sh).normalize();
    const restAngle = Math.atan2(Math.abs(upper.x), -upper.y); // angle from straight down
    // rotate about Z to bring the arm toward the body (left arm: negative Z)
    const tuck = -sx * (restAngle - p.armTuck);
    const fore = wr.clone().sub(el).normalize();
    arms[s] = { sx, tuck, axis: elbowAxis(fore) };
  }

  const tmpQ = new THREE.Quaternion();
  const tmpE = new THREE.Euler();
  const put = (arr, i, quat) => quat.toArray(arr, i * 4);

  for (let i = 0; i <= n; i++) {
    const t = i / n;               // cycle phase 0..1 (left foot lands at 0)
    const c = Math.cos(TAU * t);   // +1 when the left leg is forward

    // feet (IK)
    for (const [s, off] of [['左', 0], ['右', 0.5]]) {
      const f = foot(t + off, p);
      const r = rest(s + '足ＩＫ');
      const footLen = 2.4;
      v(s + '足ＩＫ').set([r.x, r.y + f.y + footLen * Math.sin(Math.max(0, f.pitch)) * 0.8, r.z + f.z], i * 3);
      put(q(s + '足ＩＫ'), i, tmpQ.setFromEuler(tmpE.set(f.pitch, 0, 0)));
    }

    // center: sits down, lowest at mid-stance of each foot, highest in flight
    const midStance = p.stance / 2;
    const bounce = -Math.cos(2 * TAU * (t - midStance));
    const rc = rest('センター');
    v('センター').set([rc.x, rc.y - p.hipDrop + p.bob * bounce, rc.z + 0.6], i * 3);

    // torso: forward lean, shoulders counter-rotate against the hips
    put(q('上半身'), i, tmpQ.setFromEuler(tmpE.set(p.lean + 0.03 * bounce, p.twist * c, 0, 'XYZ')));
    put(q('下半身'), i, tmpQ.setFromEuler(tmpE.set(0, -p.twist * 0.8 * c, 0, 'XYZ')));
    put(q('首'), i, tmpQ.setFromEuler(tmpE.set(-p.lean * 0.5, -p.twist * 0.6 * c, 0, 'XYZ')));
    put(q('頭'), i, tmpQ.setFromEuler(tmpE.set(-p.lean * 0.3 - 0.03 * bounce, -p.twist * 0.3 * c, 0, 'XYZ')));

    // arms swing opposite to the legs: right arm forward when the left leg is forward
    for (const s of ['左', '右']) {
      const a = arms[s];
      const fwd = s === '右' ? c : -c;  // +1 = arm forward
      const swing = -p.armSwing * fwd + THREE.MathUtils.degToRad(8); // forward swing is -X
      put(q(s + '腕'), i, tmpQ.setFromEuler(tmpE.set(swing, 0, a.tuck, 'XYZ')));
      const bend = p.elbowBend + THREE.MathUtils.degToRad(15) * fwd;
      put(q(s + 'ひじ'), i, tmpQ.setFromAxisAngle(a.axis, bend));
      put(q(s + '肩'), i, tmpQ.setFromEuler(tmpE.set(0, 0, -a.sx * 0.05 * fwd)));
    }
  }

  // IK chain bones get identity keys so the solver starts from rest every frame
  for (const s of ['左', '右']) {
    for (const b of ['足', 'ひざ', '足首']) {
      const arr = q(s + b);
      for (let i = 0; i <= n; i++) arr.set([0, 0, 0, 1], i * 4);
    }
  }

  const tracks = [];
  for (const [name, values] of Object.entries(quatTracks)) {
    tracks.push(new THREE.QuaternionKeyframeTrack(`.bones[${name}].quaternion`, times, values));
  }
  for (const [name, values] of Object.entries(posTracks)) {
    tracks.push(new THREE.VectorKeyframeTrack(`.bones[${name}].position`, times, values));
  }
  return new THREE.AnimationClip('run', p.period, tracks);
}
