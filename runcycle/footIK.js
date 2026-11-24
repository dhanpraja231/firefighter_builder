import * as THREE from 'three';

// Foot-lock IK for the Rocketbox (Biped) people running on the scrolling floor.
//
// The mocap clips are played in place, so without help a planted foot slides at
// whatever speed the clip happens to have. Each frame, after the mixer has posed the
// skeleton, this pins the ankle of a planted foot to the floor (which moves at
// -floorSpeed along the root's Z) and solves thigh/calf with analytic two-bone IK so
// the leg reaches it. The foot keeps its animated world rotation. When the foot lifts
// the target blends back to the animation.

const BLEND_OUT = 0.08; // seconds to blend from the lock back to the animation
const MAX_PULL = 0.12; // max lock-vs-animation offset, as a fraction of leg length
const MAX_REACH = 0.97; // never straighten the leg beyond this fraction of its length

const _a = new THREE.Vector3();
const _b = new THREE.Vector3();
const _c = new THREE.Vector3();
const _t = new THREE.Vector3();
const _ac = new THREE.Vector3();
const _ab = new THREE.Vector3();
const _at = new THREE.Vector3();
const _ba = new THREE.Vector3();
const _bc = new THREE.Vector3();
const _axis0 = new THREE.Vector3();
const _axis1 = new THREE.Vector3();
const _qa = new THREE.Quaternion();
const _qb = new THREE.Quaternion();
const _qf = new THREE.Quaternion();
const _qp = new THREE.Quaternion();
const _r = new THREE.Quaternion();
const _v = new THREE.Vector3();

const clamp1 = (x) => Math.min(1, Math.max(-1, x));

function worldPos(bone, out) {
  return out.setFromMatrixPosition(bone.matrixWorld);
}

// Rotate `bone` by a world-space rotation `q` (keeps it attached to its parent).
function rotateWorld(bone, q) {
  bone.parent.getWorldQuaternion(_qp);
  bone.getWorldQuaternion(_r);
  _r.premultiply(q); // new world rotation
  bone.quaternion.copy(_qp.invert().multiply(_r));
  bone.updateMatrixWorld(true);
}

// Two-bone IK: rotate thigh (A) and calf (B) so the foot (C) lands on `target`
// (world space). `pole` is a world-space direction the knee should point toward
// when the leg is nearly straight.
function solveTwoBone(thigh, calf, foot, target, pole) {
  worldPos(thigh, _a);
  worldPos(calf, _b);
  worldPos(foot, _c);
  const lab = _b.distanceTo(_a);
  const lcb = _c.distanceTo(_b);
  const lat = THREE.MathUtils.clamp(target.distanceTo(_a), 1e-4, (lab + lcb) * MAX_REACH);

  _ac.subVectors(_c, _a).normalize();
  _ab.subVectors(_b, _a).normalize();
  _ba.subVectors(_a, _b).normalize();
  _bc.subVectors(_c, _b).normalize();
  _at.subVectors(target, _a).normalize();

  const acab0 = Math.acos(clamp1(_ac.dot(_ab)));
  const babc0 = Math.acos(clamp1(_ba.dot(_bc)));
  const acat0 = Math.acos(clamp1(_ac.dot(_at)));
  const acab1 = Math.acos(clamp1((lcb * lcb - lab * lab - lat * lat) / (-2 * lab * lat)));
  const babc1 = Math.acos(clamp1((lat * lat - lab * lab - lcb * lcb) / (-2 * lab * lcb)));

  // bend plane from the current pose; fall back to the pole when the leg is straight
  _axis0.crossVectors(_ac, _ab);
  if (_axis0.lengthSq() < 1e-6) _axis0.crossVectors(_ac, pole);
  _axis0.normalize();
  _axis1.crossVectors(_ac, _at);
  const hasSwing = _axis1.lengthSq() > 1e-10;
  _axis1.normalize();

  // knee: open or close the joint to get the right hip-to-ankle distance
  _qb.setFromAxisAngle(_axis0, babc1 - babc0);
  rotateWorld(calf, _qb);
  // hip: correct the angle between thigh and hip->ankle, then swing onto the target
  _qa.setFromAxisAngle(_axis0, acab1 - acab0);
  if (hasSwing) _qa.premultiply(_r.setFromAxisAngle(_axis1, acat0));
  rotateWorld(thigh, _qa);
}

/**
 * Create the foot-lock rig for one Rocketbox model.
 * @param {THREE.Object3D} root   group the model sits in; the floor moves along its -Z
 * @param {THREE.Object3D} model  the loaded glTF scene
 */
export function createFootLock(root, model) {
  const get = (n) => model.getObjectByName(n);
  const legs = ['L', 'R'].map((s) => ({
    thigh: get(`Bip01_${s}_Thigh`),
    calf: get(`Bip01_${s}_Calf`),
    foot: get(`Bip01_${s}_Foot`),
    toe: get(`Bip01_${s}_Toe0`),
    locked: false,
    weight: 0, // 1 = fully pinned, 0 = pure animation
    lock: new THREE.Vector3(), // pinned toe position, root space
    lo: 0, // lowest toe height over the clip, root space
    hi: 0,
  }));
  if (legs.some((l) => !l.thigh || !l.calf || !l.foot || !l.toe)) return null;
  root.updateMatrixWorld(true);
  for (const l of legs) {
    const h = root.worldToLocal(worldPos(l.thigh, new THREE.Vector3()));
    const k = root.worldToLocal(worldPos(l.calf, new THREE.Vector3()));
    const a = root.worldToLocal(worldPos(l.foot, new THREE.Vector3()));
    l.legLength = h.distanceTo(k) + k.distanceTo(a);
  }
  return { root, model, legs, calibrated: false };
}

/**
 * Measure, over one loop of `clip`, each toe's height range and how fast a planted
 * toe moves backwards (root units per clip-second). Call with the model in its
 * final pose setup (scale, rotation) and the clip already made in-place.
 */
export function calibrate(rig, mixer, clip) {
  const n = 240;
  const dt = clip.duration / n;
  const samples = rig.legs.map(() => []);
  for (let i = 0; i <= n; i++) {
    mixer.setTime(i * dt);
    rig.root.updateMatrixWorld(true);
    rig.legs.forEach((l, k) => samples[k].push(rig.root.worldToLocal(worldPos(l.foot, new THREE.Vector3()))));
  }
  let dist = 0;
  let time = 0;
  rig.legs.forEach((l, k) => {
    const s = samples[k];
    l.lo = Math.min(...s.map((p) => p.y));
    l.hi = Math.max(...s.map((p) => p.y));
    const band = l.lo + 0.2 * (l.hi - l.lo);
    for (let i = 1; i < s.length; i++) {
      if (s[i].y < band && s[i - 1].y < band) {
        dist += s[i - 1].z - s[i].z;
        time += dt;
      }
    }
  });
  mixer.setTime(0);
  rig.calibrated = true;
  return time > 0 ? dist / time : 0;
}

/**
 * Apply foot locking for this frame. Call after mixer.update() and any vertical
 * grounding offset. `floorSpeed` is in root units per second along -Z.
 */
export function updateFootLock(rig, dt, floorSpeed) {
  const { root } = rig;
  root.updateMatrixWorld(true);
  const pole = _v.set(0, 0, 1).transformDirection(root.matrixWorld);

  for (const l of rig.legs) {
    const anim = root.worldToLocal(worldPos(l.foot, new THREE.Vector3()));
    const contact = anim.y < l.lo + 0.2 * (l.hi - l.lo);

    if (contact && !l.locked) {
      l.locked = true;
      l.lock.copy(anim);
      l.weight = 1;
    } else if (!contact && l.locked) {
      l.locked = false;
    }
    l.lock.z -= floorSpeed * dt; // the pinned point rides along with the floor
    if (l.locked) {
      l.lock.y = anim.y; // keep the animation's heel lift and grounding
      // Never pull the foot far from where the animation has it: past this the leg
      // would have to straighten (or the knee flip) to reach. Release early instead.
      if (Math.abs(l.lock.z - anim.z) > MAX_PULL * l.legLength) {
        l.locked = false;
      }
    }
    else l.weight = Math.max(0, l.weight - dt / BLEND_OUT);
    if (l.weight <= 0) continue;

    _t.lerpVectors(anim, l.lock, l.weight);
    root.localToWorld(_t);

    l.foot.getWorldQuaternion(_qf); // animated foot orientation
    solveTwoBone(l.thigh, l.calf, l.foot, _t, pole);
    // restore the foot's world rotation
    l.foot.parent.getWorldQuaternion(_qp);
    l.foot.quaternion.copy(_qp.invert().multiply(_qf));
    l.foot.updateMatrixWorld(true);
  }
}
