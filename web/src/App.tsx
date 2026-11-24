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
import { activeMomentAtTime, decisionLogAtTime } from "./timeline/replay";
import { visualFor } from "./timeline/roster";
import type { TimelineEvent } from "./timeline/schema";

const DEMO_FIRE_ROOM = "2-kitchen";
const DEMO_SMOKE_ROOM = "2-hall";
const DEMO_WINDOW = "3-window-living-w";
const DEMO_DOOR = "1-door-living-hall";
const ORCHESTRATOR_URL = "http://127.0.0.1:8787";

interface RunMemory {
  runs: number;
  child_losses: number;
  cautious_briefing: boolean;
  bolt_prob: number;
  found_prob: number;
  saved?: number;
  total?: number;
  lessons_used?: number;
  lessons_written?: number;
}

interface RunResponse {
  seed: number;
  run_number: number;
  memory: RunMemory;
  events: TimelineEvent[];
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

/** Advances `t` while mounted. Keyed by the caller on (seed, run_number) so a new run always starts a fresh clock. */
function PlaybackClock({
  initial,
  duration,
  onTick,
  onEnd,
}: {
  initial: number;
  duration: number;
  onTick: (t: number) => void;
  onEnd: () => void;
}) {
  const t = useRef(initial);
  const acc = useRef(0);
  useFrame((_, delta) => {
    t.current += delta;
    acc.current += delta;
    if (t.current >= duration) {
      onTick(duration);
      onEnd();
      return;
    }
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
  const [run, setRun] = useState<RunResponse | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const duration = useMemo(
    () => (run && run.events.length ? ENGINE_ENTRY_SECONDS + Math.max(...run.events.map((e) => e.t_sim)) : 0),
    [run],
  );
  const decisionRows = useMemo(() => (run ? decisionLogAtTime(run.events, t) : []), [run, t]);
  const activeMoment = useMemo(
    () => (run ? activeMomentAtTime(run.events, Math.max(0, t - ENGINE_ENTRY_SECONDS)) : null),
    [run, t],
  );

  const playRun = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${ORCHESTRATOR_URL}/run`);
      if (!res.ok) throw new Error(`orchestrator returned ${res.status}`);
      const data: RunResponse = await res.json();
      setRun(data);
      setT(0);
      setPlaying(true);
    } catch (err) {
      setError(
        `${err instanceof Error ? err.message : "Unknown error"} -- start the orchestrator: python3 agents/server.py`,
      );
    } finally {
      setLoading(false);
    }
  };

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
            <DemoScene events={run?.events ?? []} t={t} />
            {playing && run && (
              <PlaybackClock
                key={`${run.seed}-${run.run_number}`}
                initial={t}
                duration={duration}
                onTick={setT}
                onEnd={() => setPlaying(false)}
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
        {/* Free orbit only when not playing a story run; during playback the camera director drives the shots. */}
        <OrbitControls enabled={!(mode === "story" && playing)} target={[2, 5.5, 5]} maxPolarAngle={Math.PI * 0.49} />
      </Canvas>

      <ModeToggle mode={mode} setMode={setMode} />

      {mode === "story" ? (
        <RunPanel
          run={run}
          t={t}
          duration={duration}
          playing={playing}
          loading={loading}
          error={error}
          setPlaying={setPlaying}
          setT={setT}
          onPlay={playRun}
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
  error,
  setPlaying,
  setT,
  onPlay,
}: {
  run: RunResponse | null;
  t: number;
  duration: number;
  playing: boolean;
  loading: boolean;
  error: string | null;
  setPlaying: (v: boolean) => void;
  setT: (v: number) => void;
  onPlay: () => void;
}) {
  return (
    <div style={panelStyle}>
      <div style={{ marginBottom: 8, opacity: 0.8 }}>Engine 9 — story run</div>
      <button
        onClick={onPlay}
        disabled={loading}
        style={{
          display: "block",
          width: "100%",
          padding: "8px 10px",
          fontSize: 12,
          fontFamily: "monospace",
          background: loading ? "#2a2e3a" : "#2a4a3a",
          color: "#e7eefc",
          border: "1px solid #39415a",
          borderRadius: 4,
          cursor: loading ? "default" : "pointer",
        }}
      >
        {loading ? "Agents deciding..." : run ? "▶ Run another attempt" : "▶ Play"}
      </button>

      {error && <div style={{ color: "#f94144", fontSize: 10, marginTop: 6, lineHeight: 1.4 }}>{error}</div>}

      {run && (
        <>
          <div style={{ marginTop: 10, fontSize: 11, opacity: 0.85 }}>
            Attempt #{run.run_number} · seed {run.seed}
          </div>
          <div style={{ fontSize: 10, opacity: 0.65, marginTop: 2, lineHeight: 1.4 }}>
            {run.memory.total != null
              ? `${run.memory.saved}/${run.memory.total} saved · used ${run.memory.lessons_used ?? 0} lesson${
                  run.memory.lessons_used === 1 ? "" : "s"
                } from earlier runs · wrote ${run.memory.lessons_written ?? 0} new`
              : "No lessons learned yet -- this is the first attempt."}
          </div>

          <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
            <SmallButton label={playing ? "Pause" : "Resume"} onClick={() => setPlaying(!playing)} />
            <SmallButton
              label="Replay"
              onClick={() => {
                setT(0);
                setPlaying(true);
              }}
            />
          </div>
          <input
            type="range"
            min={0}
            max={duration}
            step={0.1}
            value={Math.min(t, duration)}
            onChange={(e) => {
              setT(Number(e.target.value));
              setPlaying(false);
            }}
            style={{ width: "100%", marginTop: 8 }}
          />
          <div style={{ fontSize: 10, opacity: 0.6 }}>
            {t.toFixed(1)}s / {duration.toFixed(1)}s
          </div>
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
          fires: fireOn
            ? {}
            : { [DEMO_FIRE_ROOM]: 0.55 },
          smoke: fireOn
            ? {}
            : { [DEMO_SMOKE_ROOM]: 0.35, [DEMO_FIRE_ROOM]: 0.25 },
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
