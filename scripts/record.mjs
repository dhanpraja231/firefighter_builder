// Frame-by-frame recording of one run in the 3D scene.
//
//   node scripts/record.mjs run.json out.mp4 [--fps 24] [--speed auto] [--size 1600x900]
//
// Needs the scene dev server on :5173 and Chrome installed. Each frame sets the playback time and
// camera shot through window.__ff (web/src/App.tsx), waits for two animation frames, and captures
// a screenshot, so the video is smooth however slowly WebGL renders. ffmpeg encodes the result.
//
// Shots (STATIC_SHOTS in web/src/scene/Engine9Scene.tsx): 0 Wide while the engine arrives,
// 3 West while the ladder works a west window, 2 Cutaway the rest of the time.

import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const [, , runPath, outPath, ...rest] = process.argv;
const arg = (k, d) => { const i = rest.indexOf(k); return i >= 0 ? rest[i + 1] : d; };
const FPS = Number(arg("--fps", 24));
const [W, H] = arg("--size", "1600x900").split("x").map(Number);
const ENGINE_ENTRY = 3.5;
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const run = JSON.parse(readFileSync(runPath, "utf8"));
const simEnd = Math.max(...run.events.map((e) => e.t_sim));
const duration = ENGINE_ENTRY + simEnd + 2;
const speed = arg("--speed", "auto") === "auto" ? Math.max(1, (simEnd + ENGINE_ENTRY) / 85) : Number(arg("--speed"));

// West-window ladder rescues -> West shot while the ladder is up
const west = [];
let open = null;
for (const e of run.events) {
  const w = e.type === "world_event" ? e.payload?.world : null;
  if (!w || w.type !== "ladder") continue;
  if (w.deployed === 1 && /window-(living-w|bed-w)$/.test(w.targetWindowId ?? "")) open = e.t_sim;
  else if (w.deployed === 0 && open != null) { west.push([open, e.t_sim]); open = null; }
}
if (open != null) west.push([open, open + 24]);
const shotAt = (t) => {
  if (t < ENGINE_ENTRY + 1.0) return 0;
  const s = t - ENGINE_ENTRY;
  return west.some(([a, b]) => s >= a - 1 && s <= b + 1) ? 3 : 2;
};

const port = 9300 + Math.floor(Math.random() * 500);
const profile = `/tmp/ff-rec-${port}`;
const chrome = spawn(CHROME, [
  "--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, `--window-size=${W},${H}`,
  "--hide-scrollbars", "--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist", "--no-first-run", "about:blank",
], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let wsUrl;
for (let i = 0; i < 50 && !wsUrl; i++) {
  try {
    const tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
    wsUrl = tabs.find((t) => t.type === "page")?.webSocketDebuggerUrl;
  } catch { await sleep(200); }
}
const ws = new WebSocket(wsUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 0;
const pending = new Map();
ws.addEventListener("message", (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
});
const send = (method, params = {}) => new Promise((resolve) => { const i = ++id; pending.set(i, resolve); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;

await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: "http://localhost:5173/?shot=1" });
for (let i = 0; i < 100 && !(await evaluate("Boolean(window.__ff)")); i++) await sleep(200);
await evaluate(`window.__ff.load(${JSON.stringify(run)})`);
await sleep(4000); // models and textures

const dir = `${outPath}.frames`;
rmSync(dir, { recursive: true, force: true });
mkdirSync(dir, { recursive: true });
const frames = Math.ceil((duration / speed) * FPS);
const t0 = Date.now();
let lastShot = -1;
for (let f = 0; f < frames; f++) {
  const t = (f / FPS) * speed;
  const shot = shotAt(t);
  await evaluate(`window.__ff.setShot(${shot}); window.__ff.setT(${t.toFixed(3)}); new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))`);
  if (shot !== lastShot) { await evaluate("new Promise(r => setTimeout(r, 120))"); lastShot = shot; }
  const shotRes = await send("Page.captureScreenshot", { format: "jpeg", quality: 88 });
  writeFileSync(join(dir, `f${String(f).padStart(5, "0")}.jpg`), Buffer.from(shotRes.result.data, "base64"));
  if (f % 100 === 0) console.log(`frame ${f}/${frames} t=${t.toFixed(1)}s shot=${shot} (${((Date.now() - t0) / 1000).toFixed(0)}s elapsed)`);
}
ws.close();
chrome.kill();
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-i", join(dir, "f%05d.jpg"),
  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", outPath]);
writeFileSync(`${outPath}.json`, JSON.stringify({ seed: run.seed, run_id: run.run_id, saved: run.memory?.saved, total: run.memory?.total,
  speed, fps: FPS, seconds: frames / FPS, west_ladder_windows: west }, null, 2));
console.log(`wrote ${outPath}: ${frames} frames, ${(frames / FPS).toFixed(1)} s at ${speed.toFixed(2)}x`);
