import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { Engine9Scene } from "./scene/Engine9Scene";
import { createDefaultWorldState, type WorldState } from "./scene/events";
import { buildExteriorLayout, buildNavGraph, createBuildingLayout } from "./scene/layout";
import { findPath, pathLength, pathWaypoints } from "./scene/nav";
import { PlaceholderWalker } from "./scene/characters/PlaceholderWalker";
import { DemoScene, ENGINE_ENTRY_SECONDS } from "./demo/DemoScene";
import { DecisionLogPanel } from "./demo/DecisionLogPanel";
import { CaptionBar } from "./demo/CaptionBar";
import { EndingCard } from "./demo/EndingCard";
import { activeMomentAtTime, decisionLogAtTime } from "./timeline/replay";
import { visualFor } from "./timeline/roster";
import type { TimelineEvent } from "./timeline/schema";

const DEMO_FIRE_ROOM = "2-kitchen";
const DEMO_SMOKE_ROOM = "2-hall";
const DEMO_WINDOW = "3-window-living-w";
const DEMO_DOOR = "1-door-living-hall";
// `?server=http://127.0.0.1:8788` points the viewer at another story server (testing); `?speed=` is passed to /stream.
const PAGE_QUERY = new URLSearchParams(window.location.search);
const ORCHESTRATOR_URL = PAGE_QUERY.get("server") ?? "http://127.0.0.1:8787";
const STREAM_QUERY = PAGE_QUERY.get("speed") ? `?speed=${encodeURIComponent(PAGE_QUERY.get("speed")!)}` : "";

interface RunMemory {
  runs: number;
  child_losses: number;
  cautious_briefing: boolean;
  bolt_prob: number;
  found_prob: number;
}

interface RunResponse {
  seed: number;
  run_number: number;
  memory: RunMemory;
  events: TimelineEvent[];
  /** How the agents' story ended (computed by the engine from the final state). */
  ending?: string;
  /** Which policy drove the agents: "llm" or "heuristic". */
  policy?: string;
}

const NO_MEMORY: RunMemory = { runs: 0, child_losses: 0, cautious_briefing: false, bolt_prob: 0, found_prob: 0 };

/** Track 1 asks for a 1-3 minute short. */
const FILM_MIN_SECONDS = 60;
const FILM_MAX_SECONDS = 180;

function formatClock(seconds: number): string {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function demoWorldState(): WorldState {
  const state = createDefaultWorldState();
  state.fires[DEMO_FIRE_ROOM] = 0.55;
  state.smoke[DEMO_SMOKE_ROOM] = 0.45;
  state.doors[DEMO_DOOR] = 0.85;
  state.doors["2-door-kitchen-hall"] = 0.7;
  state.doors["2-door-living-hall"] = 0.6;
  state.doors["2-door-living-bed"] = 0.5;
  state.doors["2-door-kitchen-bed"] = 0.4;
  state.ladder = { deployed: 0.85, targetWindowId: DEMO_WINDOW };
  state.hose = { active: false, targetWindowId: DEMO_WINDOW };
  return state;
}

function SceneBackground() {
  const scene = useThree((state) => state.scene);
  const camera = useThree((state) => state.camera);
  const controls = useThree((state) => state.controls);
  useEffect(() => {
    // Match the night-sky dome horizon so gaps around the sphere aren't a black void.
    scene.background = new THREE.Color("#152038");
    // Exposed for debugging the camera framing from the console.
    (window as unknown as { __scene: unknown }).__scene = { scene, camera, controls };
    // `?cam=px,py,pz,tx,ty,tz` fixes the camera (position, look-at) for framing shots and screenshots.
    const cam = new URLSearchParams(window.location.search).get("cam")?.split(",").map(Number);
    if (cam && cam.length === 6 && cam.every(Number.isFinite)) {
      camera.position.set(cam[0], cam[1], cam[2]);
      const orbit = controls as unknown as { target: THREE.Vector3; update: () => void } | null;
      if (orbit) {
        orbit.target.set(cam[3], cam[4], cam[5]);
        orbit.update();
      } else {
        camera.lookAt(cam[3], cam[4], cam[5]);
      }
    }
  }, [scene, camera, controls]);
  return null;
}

/** Client-side preview of room-to-room fire growth for the dev harness. */
function FireSpreadTicker({
  active,
  onTick,
}: {
  active: boolean;
  onTick: (updater: (state: WorldState) => WorldState) => void;
}) {
  const acc = useRef(0);
  useFrame((_, delta) => {
    if (!active) return;
    acc.current += delta;
    if (acc.current < 0.9) return;
    acc.current = 0;
    onTick((state) => spreadHarnessFire(state));
  });
  return null;
}

const HARNESS_FIRE_ADJ: Record<string, string[]> = {
  "2-kitchen": ["2-hall", "2-bedroom-e"],
  "2-hall": ["2-kitchen", "2-living", "1-hall", "3-hall"],
  "2-living": ["2-hall", "2-bedroom-w"],
  "2-bedroom-w": ["2-living", "2-landing"],
  "2-bedroom-e": ["2-kitchen", "2-landing"],
  "2-landing": ["2-bedroom-w", "2-bedroom-e"],
  "1-hall": ["2-hall"],
  "3-hall": ["2-hall", "3-kitchen", "3-living"],
  "3-kitchen": ["3-hall"],
  "3-living": ["3-hall"],
};

function spreadHarnessFire(state: WorldState): WorldState {
  const fires = { ...state.fires };
  const smoke = { ...state.smoke };
  let changed = false;
  for (const [roomId, intensity] of Object.entries(fires)) {
    if (intensity < 0.08) continue;
    if (intensity < 0.95) {
      fires[roomId] = Math.min(1, intensity + 0.04);
      changed = true;
    }
    smoke[roomId] = Math.max(smoke[roomId] ?? 0, Math.min(1, intensity * 0.85 + 0.1));
    if (intensity < 0.35) continue;
    for (const neighbor of HARNESS_FIRE_ADJ[roomId] ?? []) {
      const next = fires[neighbor] ?? 0;
      if (next < intensity * 0.55) {
        fires[neighbor] = Math.min(1, next + 0.08);
        smoke[neighbor] = Math.max(smoke[neighbor] ?? 0, Math.min(1, (smoke[neighbor] ?? 0) + 0.12));
        changed = true;
      }
    }
  }
  return changed ? { ...state, fires, smoke } : state;
}


/**
 * Real-time story clock: `t` advances at wall-clock speed and can never run ahead of the newest
 * event the agents have produced. If playback catches up with a slow decision it waits ("thinking")
 * instead of skipping. Keyed by the caller per story so a new story always starts a fresh clock.
 */
function PlaybackClock({
  initial,
  limit,
  endAt,
  onTick,
  onWaiting,
  onEnd,
}: {
  initial: number;
  /** Latest page time playback may reach while the story is still being generated. */
  limit: () => number;
  /** Page time the story ends at, or null while events are still arriving. */
  endAt: number | null;
  onTick: (t: number) => void;
  onWaiting: (waiting: boolean) => void;
  onEnd: () => void;
}) {
  const t = useRef(initial);
  const acc = useRef(0);
  const waiting = useRef(false);
  useFrame((_, delta) => {
    const next = t.current + delta;
    const blocked = endAt === null && next > limit();
    t.current = blocked ? Math.max(t.current, limit()) : next;
    if (blocked !== waiting.current) {
      waiting.current = blocked;
      onWaiting(blocked);
    }
    if (endAt !== null && t.current >= endAt) {
      onTick(endAt);
      onEnd();
      return;
    }
    acc.current += delta;
    if (acc.current > 0.05) {
      acc.current = 0;
      onTick(t.current);
    }
  });
  return null;
}

export default function App() {
  const [mode, setMode] = useState<"story" | "harness">("story");

  // -- dev harness state (unchanged) --
  const [worldState, setWorldState] = useState<WorldState>(demoWorldState);
  const [showDebug, setShowDebug] = useState(true);
  const [cameraCue, setCameraCue] = useState(0);
  const [walkToken, setWalkToken] = useState<number | null>(null);
  const [walkInfo, setWalkInfo] = useState<string>("");

  const layout = useMemo(() => createBuildingLayout(), []);
  const exterior = useMemo(() => buildExteriorLayout(), []);
  const navGraph = useMemo(() => buildNavGraph(layout, exterior), [layout, exterior]);

  const walkWaypoints = useMemo(() => {
    if (walkToken === null) return null;
    const path = findPath(navGraph, "exterior-engine", "3-hall");
    if (!path) return null;
    setWalkInfo(`${path.length} nodes, ${pathLength(navGraph, path).toFixed(1)} m: ${path.join(" -> ")}`);
    return pathWaypoints(navGraph, path);
  }, [navGraph, walkToken]);

  // -- story run state --
  // `?debug` brings back the scrubber and pause controls for development; the default viewer is live-only.
  const debug = useMemo(() => new URLSearchParams(window.location.search).has("debug"), []);
  const [run, setRun] = useState<RunResponse | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [live, setLive] = useState(false); // the server is still sending events
  const [thinking, setThinking] = useState(false); // playback caught up and is waiting for the agents' next decision
  const [finished, setFinished] = useState(false);
  const [storyId, setStoryId] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const source = useRef<EventSource | null>(null);
  /** Story time (seconds) of the newest event received; playback never runs past it. */
  const latest = useRef(0);

  useEffect(() => () => source.current?.close(), []);

  // `?run=/runs/seed-1.json&t=20&play=1` loads a saved run (and jumps to a moment) without the
  // orchestrator server -- used for tests and screenshots, not the normal viewer.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const url = q.get("run");
    if (!url) return;
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`could not load ${url} (${res.status})`);
        return res.json() as Promise<RunResponse>;
      })
      .then((data) => {
        latest.current = Math.max(0, ...data.events.map((e) => e.t_sim));
        setRun(data);
        setStoryId((n) => n + 1);
        setT(Number(q.get("t") ?? 0));
        setPlaying(q.get("play") === "1");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Unknown error"));
  }, []);

  /** Older servers only offer /run (the whole story at once); it still plays in real time, just generated up front. */
  const fallbackStory = async () => {
    try {
      const res = await fetch(`${ORCHESTRATOR_URL}/run`);
      if (!res.ok) throw new Error(`orchestrator returned ${res.status}`);
      const data: RunResponse = await res.json();
      latest.current = Math.max(0, ...data.events.map((e) => e.t_sim));
      setRun(data);
      setLive(false);
    } catch (err) {
      setPlaying(false);
      setLive(false);
      setRun(null);
      setError(`${err instanceof Error ? err.message : "Unknown error"} -- start the story server: python agents/server.py`);
    } finally {
      setLoading(false);
    }
  };

  /** Starts a brand-new story. Events stream in as the agents decide them and play at the pace they happen. */
  const startStory = () => {
    source.current?.close();
    setError(null);
    setFinished(false);
    setThinking(false);
    setLoading(true);
    latest.current = 0;
    setRun({ seed: 0, run_number: 0, memory: NO_MEMORY, events: [] });
    setT(0);
    setStoryId((n) => n + 1);
    setPlaying(true);
    setLive(true);

    const es = new EventSource(`${ORCHESTRATOR_URL}/stream${STREAM_QUERY}`);
    source.current = es;
    let opened = false;
    es.addEventListener("start", (m) => {
      opened = true;
      setLoading(false);
      const info = JSON.parse((m as MessageEvent).data);
      setRun((r) => (r ? { ...r, seed: info.seed ?? r.seed, policy: info.policy ?? r.policy } : r));
    });
    es.onmessage = (m) => {
      opened = true;
      setLoading(false);
      const event = JSON.parse(m.data) as TimelineEvent;
      latest.current = Math.max(latest.current, event.t_sim);
      setRun((r) => (r ? { ...r, events: [...r.events, event] } : r));
    };
    es.addEventListener("end", (m) => {
      const info = JSON.parse((m as MessageEvent).data);
      es.close();
      source.current = null;
      setLive(false);
      setRun((r) =>
        r
          ? {
              ...r,
              ending: info.ending,
              policy: info.policy ?? r.policy,
              run_number: info.run_number ?? r.run_number,
              memory: info.memory ?? r.memory,
            }
          : r,
      );
    });
    es.onerror = () => {
      es.close();
      source.current = null;
      if (opened) {
        setLive(false);
        setError("Lost the connection to the story server.");
      } else {
        void fallbackStory();
      }
    };
  };

  const recordFilm = async () => {
    setError(null);
    try {
      // Records this tab (3D scene + decision log + captions). The browser asks which tab to share.
      const stream = await (navigator.mediaDevices as MediaDevices & {
        getDisplayMedia(options: unknown): Promise<MediaStream>;
      }).getDisplayMedia({ video: { frameRate: 30 }, audio: false, preferCurrentTab: true });
      const rec = new MediaRecorder(stream, { mimeType: "video/webm;codecs=vp9" });
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const link = document.createElement("a");
        link.href = URL.createObjectURL(new Blob(chunks, { type: "video/webm" }));
        link.download = `engine9-seed-${run?.seed ?? "story"}.webm`;
        link.click();
        setRecording(false);
      };
      recorder.current = rec;
      rec.start();
      setRecording(true);
      startStory(); // the recording covers one whole live story, start to finish
    } catch (err) {
      setError(`Recording failed: ${err instanceof Error ? err.message : "cancelled"}`);
    }
  };

  // Known only once the story has finished generating; null while it is still live.
  const storyEnd = useMemo(
    () => (!live && run && run.events.length ? ENGINE_ENTRY_SECONDS + Math.max(...run.events.map((e) => e.t_sim)) : null),
    [live, run],
  );
  const decisionRows = useMemo(() => (run ? decisionLogAtTime(run.events, t) : []), [run, t]);
  const activeMoment = useMemo(
    () => (run ? activeMomentAtTime(run.events, Math.max(0, t - ENGINE_ENTRY_SECONDS)) : null),
    [run, t],
  );

  return (
    <div style={{ width: "100vw", height: "100vh", background: "#152038" }}>
      {/* ACESFilmic rolls highlights off instead of clipping them to white, which matters with
          bright practical lights in every room; exposure is raised so interiors still read warm. */}
      <Canvas
        shadows
        camera={{ position: [-24, 15, -31], fov: 45, near: 0.1, far: 200 }}
        gl={{ toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.2 }}
      >
        <SceneBackground />
        {mode === "story" ? (
          <>
            <DemoScene events={run?.events ?? []} t={t} paused={!playing} />
            {playing && run && (
              <PlaybackClock
                key={storyId}
                initial={t}
                limit={() => ENGINE_ENTRY_SECONDS + latest.current}
                endAt={storyEnd}
                onTick={setT}
                onWaiting={setThinking}
                onEnd={() => {
                  setPlaying(false);
                  setFinished(true);
                  // Hold the last frame a moment so the ending lands, then finish the recording.
                  if (recorder.current?.state === "recording") window.setTimeout(() => recorder.current?.stop(), 4000);
                }}
              />
            )}
          </>
        ) : (
          <Engine9Scene worldState={worldState} cameraCue={cameraCue} showDebugMarkers={showDebug}>
            <FireSpreadTicker
              active={(worldState.fires[DEMO_FIRE_ROOM] ?? 0) > 0.01}
              onTick={setWorldState}
            />
            {walkWaypoints && (
              <PlaceholderWalker
                key={walkToken}
                waypoints={walkWaypoints}
                onArrive={() => setWalkInfo((info) => `${info}  [arrived]`)}
              />
            )}
          </Engine9Scene>
        )}
        <OrbitControls makeDefault target={[2, 5.5, 5]} maxPolarAngle={Math.PI * 0.49} />
      </Canvas>

      <ModeToggle mode={mode} setMode={setMode} />

      {mode === "story" ? (
        <RunPanel
          run={run}
          t={t}
          duration={storyEnd ?? 0}
          playing={playing}
          loading={loading}
          live={live}
          thinking={thinking}
          finished={finished}
          debug={debug}
          error={error}
          setPlaying={setPlaying}
          setT={setT}
          onStart={startStory}
          recording={recording}
          onRecord={recordFilm}
        />
      ) : (
        <HarnessPanel
          worldState={worldState}
          setWorldState={setWorldState}
          showDebug={showDebug}
          setShowDebug={setShowDebug}
          onEstablishingShot={() => setCameraCue((n) => n + 1)}
          onWalk={() => setWalkToken((n) => (n ?? 0) + 1)}
          walkInfo={walkInfo}
        />
      )}

      {mode === "story" && run && <DecisionLogPanel rows={decisionRows} />}
      {mode === "story" && run && finished && <EndingCard ending={run.ending} events={run.events} onAgain={startStory} />}
      {mode === "story" && run && activeMoment && (
        <CaptionBar
          speaker={visualFor(activeMoment.agentId, activeMoment.role).label}
          color={visualFor(activeMoment.agentId, activeMoment.role).color}
          line={activeMoment.line}
          kind={activeMoment.kind}
        />
      )}
    </div>
  );
}

const panelStyle: React.CSSProperties = {
  position: "fixed",
  top: 12,
  left: 12,
  width: 260,
  padding: 12,
  background: "rgba(8,10,16,0.82)",
  border: "1px solid #2a2e3a",
  borderRadius: 8,
  color: "#e7eefc",
  fontFamily: "monospace",
  fontSize: 12,
};

function ModeToggle({ mode, setMode }: { mode: "story" | "harness"; setMode: (m: "story" | "harness") => void }) {
  return (
    <button
      onClick={() => setMode(mode === "story" ? "harness" : "story")}
      style={{
        position: "fixed",
        bottom: 12,
        left: 12,
        padding: "6px 10px",
        fontSize: 11,
        fontFamily: "monospace",
        background: "#1a1d26",
        color: "#e7eefc",
        border: "1px solid #39415a",
        borderRadius: 4,
        cursor: "pointer",
      }}
    >
      {mode === "story" ? "Switch to dev harness" : "Switch to story run"}
    </button>
  );
}

function RunPanel({
  run,
  t,
  duration,
  playing,
  loading,
  live,
  thinking,
  finished,
  debug,
  error,
  setPlaying,
  setT,
  onStart,
  recording,
  onRecord,
}: {
  run: RunResponse | null;
  t: number;
  duration: number;
  playing: boolean;
  loading: boolean;
  live: boolean;
  thinking: boolean;
  finished: boolean;
  debug: boolean;
  error: string | null;
  setPlaying: (v: boolean) => void;
  setT: (v: number) => void;
  onStart: () => void;
  recording: boolean;
  onRecord: () => void;
}) {
  const running = (playing || live || loading) && !finished;
  return (
    <div style={panelStyle}>
      <div style={{ marginBottom: 8, opacity: 0.8 }}>Engine 9 — live story</div>
      {!running && (
        <button
          onClick={onStart}
          style={{
            display: "block",
            width: "100%",
            padding: "8px 10px",
            fontSize: 12,
            fontFamily: "monospace",
            background: "#2a4a3a",
            color: "#e7eefc",
            border: "1px solid #39415a",
            borderRadius: 4,
            cursor: "pointer",
          }}
        >
          {run ? "▶ Watch a different story" : "▶ Start a story"}
        </button>
      )}

      {error && <div style={{ color: "#f94144", fontSize: 10, marginTop: 6, lineHeight: 1.4 }}>{error}</div>}

      {run && (
        <>
          <div style={{ marginTop: running ? 0 : 10, fontSize: 12, color: running ? "#f94144" : "#90be6d" }}>
            {loading ? "● Agents are taking their places..." : running ? `● LIVE ${formatClock(t)}` : `■ Finished ${formatClock(t)}`}
            {running && thinking ? "  (agents deciding...)" : ""}
          </div>
          {run.seed > 0 && (
            <div style={{ marginTop: 6, fontSize: 11, opacity: 0.85 }}>
              Story #{run.run_number || "?"} · seed {run.seed}
              {run.policy ? ` · ${run.policy} agents` : ""}
            </div>
          )}
          {run.memory.cautious_briefing && (
            <div style={{ fontSize: 10, opacity: 0.65, marginTop: 2, lineHeight: 1.4 }}>
              The rescue robot remembers earlier stories ({run.memory.child_losses} child loss
              {run.memory.child_losses === 1 ? "" : "es"} so far).
            </div>
          )}
          {finished && run.ending && (
            <div style={{ fontSize: 11, marginTop: 6, color: "#ffd166" }}>Ending: {run.ending.replace(/_/g, " ")}</div>
          )}
          {finished && (
            <div
              style={{
                fontSize: 10,
                marginTop: 2,
                color: duration >= FILM_MIN_SECONDS && duration <= FILM_MAX_SECONDS ? "#90be6d" : "#f8961e",
              }}
            >
              Film length {formatClock(duration)}
              {duration < FILM_MIN_SECONDS || duration > FILM_MAX_SECONDS ? " (target 1:00 to 3:00)" : ""}
            </div>
          )}
        </>
      )}

      {!running && (
        <div style={{ marginTop: 8 }}>
          <SmallButton
            label={recording ? "● Recording... (stops at the end)" : "● Record a story (.webm)"}
            onClick={() => !recording && onRecord()}
          />
        </div>
      )}

      {debug && run && (
        <>
          <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
            <SmallButton label={playing ? "Pause" : "Resume"} onClick={() => setPlaying(!playing)} />
            <SmallButton
              label="Restart"
              onClick={() => {
                setT(0);
                setPlaying(true);
              }}
            />
          </div>
          <input
            type="range"
            min={0}
            max={Math.max(duration, t)}
            step={0.1}
            value={Math.min(t, Math.max(duration, t))}
            onChange={(e) => {
              setT(Number(e.target.value));
              setPlaying(false);
            }}
            style={{ width: "100%", marginTop: 8 }}
          />
          <div style={{ fontSize: 10, opacity: 0.6 }}>debug: scrubber (hidden in the normal viewer)</div>
        </>
      )}
    </div>
  );
}

function SmallButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        flex: 1,
        padding: "5px 8px",
        fontSize: 11,
        fontFamily: "monospace",
        background: "#1a1d26",
        color: "#e7eefc",
        border: "1px solid #39415a",
        borderRadius: 4,
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
}

function HarnessPanel({
  worldState,
  setWorldState,
  showDebug,
  setShowDebug,
  onEstablishingShot,
  onWalk,
  walkInfo,
}: {
  worldState: WorldState;
  setWorldState: (updater: (state: WorldState) => WorldState) => void;
  showDebug: boolean;
  setShowDebug: (value: boolean) => void;
  onEstablishingShot: () => void;
  onWalk: () => void;
  walkInfo: string;
}) {
  const fireOn = (worldState.fires[DEMO_FIRE_ROOM] ?? 0) > 0.01;
  const doorOpen = (worldState.doors[DEMO_DOOR] ?? 0) > 0.3;
  const ladderDeployed = worldState.ladder.deployed > 0.5;
  const hoseActive = worldState.hose.active;

  const button = (label: string, onClick: () => void, active?: boolean) => (
    <button
      onClick={onClick}
      style={{
        display: "block",
        width: "100%",
        marginBottom: 6,
        padding: "6px 8px",
        fontSize: 12,
        fontFamily: "monospace",
        background: active ? "#2a3a52" : "#1a1d26",
        color: "#e7eefc",
        border: "1px solid #39415a",
        borderRadius: 4,
        cursor: "pointer",
        textAlign: "left",
      }}
    >
      {label}
    </button>
  );

  return (
    <div style={panelStyle}>
      <div style={{ marginBottom: 8, opacity: 0.8 }}>Engine 9 — dev harness</div>

      {button(`Fire floor 2: ${fireOn ? "ON (spreading)" : "off"}`, () =>
        setWorldState((state) => ({
          ...state,
          fires: (fireOn ? {} : { [DEMO_FIRE_ROOM]: 0.55 }) as Record<string, number>,
          smoke: (fireOn ? {} : { [DEMO_SMOKE_ROOM]: 0.35, [DEMO_FIRE_ROOM]: 0.25 }) as Record<string, number>,
        })),
        fireOn,
      )}

      {button(`Door (floor 1 living): ${doorOpen ? "open" : "closed"}`, () =>
        setWorldState((state) => ({
          ...state,
          doors: { ...state.doors, [DEMO_DOOR]: doorOpen ? 0 : 0.85 },
        })),
        doorOpen,
      )}

      {button(`Ladder to ${DEMO_WINDOW}: ${ladderDeployed ? "extended" : "stowed"}`, () =>
        setWorldState((state) => ({
          ...state,
          ladder: { deployed: ladderDeployed ? 0 : 0.95, targetWindowId: DEMO_WINDOW },
        })),
        ladderDeployed,
      )}

      {button(`Hose spray: ${hoseActive ? "ON" : "off"}`, () =>
        setWorldState((state) => ({
          ...state,
          hose: { active: !hoseActive, targetWindowId: DEMO_WINDOW },
        })),
        hoseActive,
      )}

      {button(`Engine lights: ${worldState.engineLights ? "ON" : "off"}`, () =>
        setWorldState((state) => ({ ...state, engineLights: !state.engineLights })),
        worldState.engineLights,
      )}

      {button(`Debug markers: ${showDebug ? "shown" : "hidden"}`, () => setShowDebug(!showDebug), showDebug)}

      {button("Establishing shot", onEstablishingShot)}

      <div style={{ height: 1, background: "#2a2e3a", margin: "8px 0" }} />

      {button("Walk placeholder: engine -> floor 3", onWalk)}
      {walkInfo && (
        <div style={{ marginTop: 6, fontSize: 10, lineHeight: 1.4, opacity: 0.85, wordBreak: "break-all" }}>
          {walkInfo}
        </div>
      )}
    </div>
  );
}
