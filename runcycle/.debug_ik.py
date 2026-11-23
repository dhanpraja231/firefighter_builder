# Temporary: render the runcycle page headlessly, report IK error per firefighter, save screenshots.
import json, sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:5179/'

PROBE = """
() => {
  const { helper } = window.__cast;
  const out = [];
  for (const mesh of helper.meshes) {
    const iks = mesh.geometry.userData.MMD.iks;
    const bones = mesh.skeleton.bones;
    const v = (b) => { const p = new mesh.position.constructor(); p.setFromMatrixPosition(b.matrixWorld); return p; };
    out.push({
      x: mesh.position.x,
      iks: iks.map((ik) => ({
        target: bones[ik.target].name,
        effector: bones[ik.effector].name,
        links: ik.links.map((l) => bones[l.index].name + (l.enabled === false ? '(off)' : '')),
        err: +v(bones[ik.target]).distanceTo(v(bones[ik.effector])).toFixed(3),
        footY: +v(bones[ik.effector]).y.toFixed(2),
      })),
    });
  }
  return out;
}
"""

LIMITS = """
() => {
  const mesh = window.__cast.helper.meshes[0];
  const b = mesh.skeleton.bones;
  return mesh.geometry.userData.MMD.iks.map((ik) => ({
    target: b[ik.target].name, iteration: ik.iteration, maxAngle: ik.maxAngle,
    links: ik.links.map((l) => ({ bone: b[l.index].name, limitation: l.limitation && l.limitation.toArray(),
      min: l.rotationMin && l.rotationMin.toArray().map((x) => +x.toFixed(3)),
      max: l.rotationMax && l.rotationMax.toArray().map((x) => +x.toFixed(3)) })),
  }));
}
"""

# Per leg, in mesh-local space (+Z forward, +Y up): how far the knee sits in front of
# the hip-ankle line (should be > 0), the knee's local euler, and the thigh's euler.
KNEES = """
() => {
  const out = [];
  for (const mesh of window.__cast.helper.meshes) {
    const b = (n) => mesh.skeleton.bones.find((x) => x.name === n);
    const P = (bone) => { const v = new mesh.position.constructor(); v.setFromMatrixPosition(bone.matrixWorld); return mesh.worldToLocal(v); };
    const row = {};
    for (const s of ['左', '右']) {
      const hip = P(b(s + '足')), knee = P(b(s + 'ひざ')), ankle = P(b(s + '足首'));
      const t = knee.clone().sub(hip).dot(ankle.clone().sub(hip).normalize());
      const onLine = hip.clone().add(ankle.clone().sub(hip).normalize().multiplyScalar(t));
      const off = knee.clone().sub(onLine);
      const e = b(s + 'ひざ').rotation, th = b(s + '足').rotation;
      row[s] = { kneeFwd: +off.z.toFixed(2), kneeSide: +off.x.toFixed(2),
        knee: [e.x, e.y, e.z].map((x) => +(x * 57.3).toFixed(0)),
        thigh: [th.x, th.y, th.z].map((x) => +(x * 57.3).toFixed(0)) };
    }
    out.push(row);
  }
  return out;
}
"""

with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True, args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    page = b.new_page(viewport={'width': 1400, 'height': 800})
    logs = []
    page.on('console', lambda m: logs.append(f'{m.type}: {m.text}'))
    page.on('pageerror', lambda e: logs.append(f'pageerror: {e}'))
    page.goto(URL)
    page.wait_for_function('window.__cast !== undefined', timeout=120000)
    page.wait_for_timeout(1500)
    print(json.dumps(page.evaluate(LIMITS), ensure_ascii=False))
    for i in range(int(sys.argv[2]) if len(sys.argv) > 2 else 6):
        print(json.dumps(page.evaluate(KNEES), ensure_ascii=False))
        page.wait_for_timeout(97)
    print('\n'.join(l for l in logs if 'error' in l.lower() or 'warn' in l.lower())[:3000])
    b.close()
