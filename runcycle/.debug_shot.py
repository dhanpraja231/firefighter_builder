from playwright.sync_api import sync_playwright

# Side-view screenshots of one person at a few points in the stride.
SETUP = """
() => {
  const c = window.__cast;
  const g = c.grounded.find((x) => /victim-2/.test(x.root.children[1]?.element?.textContent));
  window.__g = g;
  return g.root.position.toArray();
}
"""

with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True,
                          args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    pg = b.new_page(viewport={'width': 900, 'height': 900})
    pg.goto('http://localhost:5179/')
    pg.wait_for_function('window.__cast !== undefined', timeout=120000)
    pos = pg.evaluate(SETUP)
    print('person at', pos)
    # look from +X (the person's left side), camera is found via the scene's renderer loop: use OrbitControls target
    pg.evaluate("""(pos) => {
      const cam = window.__cast.camera, ctl = window.__cast.controls;
      ctl.target.set(pos[0], 9, pos[2]);
      cam.position.set(pos[0] + 45, 10, pos[2]);
      cam.fov = 30; cam.updateProjectionMatrix(); ctl.update();
    }""", pos)
    for i in range(4):
        pg.wait_for_timeout(180)
        pg.screenshot(path=f'.shot_{i}.png')
    b.close()
