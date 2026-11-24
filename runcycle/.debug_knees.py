from playwright.sync_api import sync_playwright

# Same hinge test as models/tools/probe_knee.py, in the live three.js scene: the knee
# bend axis (thigh x calf) must keep one sign relative to the L-R hip axis.
# Runs with the render loop paused, stepping mixer + grounding (+ foot lock if lock=true).
JS = """
async (lock) => {
  const { updateFootLock } = await import('/footIK.js');
  const { groundSpeed, RUN } = await import('/runCycle.js');
  const speed = groundSpeed(RUN);
  return window.__cast.grounded.map((g) => {
    const V = () => new g.root.position.constructor();
    const W = (b) => V().setFromMatrixPosition(b.matrixWorld);
    const [Lg, Rg] = g.rig.legs;
    const res = { L: [0, 0], R: [0, 0] };
    const dt = 1 / 120;
    for (let i = 0; i < 360; i++) {
      g.mixer.update(dt);
      g.model.position.y = 0; g.root.updateMatrixWorld(true);
      let lo = Infinity; for (const b of g.feet) lo = Math.min(lo, g.root.worldToLocal(W(b)).y);
      g.model.position.y = g.restFootY - lo;
      if (lock) updateFootLock(g.rig, dt, speed);
      g.root.updateMatrixWorld(true);
      const lr = W(Lg.thigh).sub(W(Rg.thigh));
      [['L', Lg], ['R', Rg]].forEach(([s, l]) => {
        const h = W(l.thigh), k = W(l.calf), a = W(l.foot);
        const u = k.clone().sub(h).normalize(), w = a.clone().sub(k).normalize();
        if (u.angleTo(w) < 0.15) return;
        res[s][u.cross(w).dot(lr) > 0 ? 0 : 1]++;
      });
    }
    return { label: g.root.children[1]?.element?.textContent, lock, L: `+${res.L[0]} -${res.L[1]}`, R: `+${res.R[0]} -${res.R[1]}` };
  });
}
"""

with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True,
                          args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    pg = b.new_page()
    pg.goto('http://localhost:5179/')
    pg.wait_for_function('window.__cast !== undefined', timeout=120000)
    pg.keyboard.press('Space')
    for lock in (False, True):
        for r in pg.evaluate(JS, lock):
            print(r)
    b.close()
