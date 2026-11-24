import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Engine9Scene } from "../scene/Engine9Scene";
import { RiggedCharacter } from "../scene/characters/RiggedCharacter";
import { activeMomentAtTime, agentFramesAtTime, worldStateAtTime } from "../timeline/replay";
import { visualFor } from "../timeline/roster";
import { startingPosition } from "../timeline/startingPositions";
import type { TimelineEvent } from "../timeline/schema";

/** Seconds the scene opens on: the engine driving in before any agent decision plays. */
export const ENGINE_ENTRY_SECONDS = 3.5;
const ENGINE_ENTRY_START_OFFSET = 16; // meters down the street the engine starts from

function easeOutCubic(x: number): number {
  return 1 - Math.pow(1 - x, 3);
}

/** Renders one instant of a run: the engine's entrance, the building's WorldState, and every agent's frame. */
export function DemoScene({ events, t, paused = false }: { events: TimelineEvent[]; t: number; paused?: boolean }) {
  const entryProgress = Math.min(1, t / ENGINE_ENTRY_SECONDS);
  const engineZOffset = (1 - easeOutCubic(entryProgress)) * ENGINE_ENTRY_START_OFFSET;
  const storyT = Math.max(0, t - ENGINE_ENTRY_SECONDS);

  const worldState = useMemo(() => worldStateAtTime(events, storyT), [events, storyT]);
  const frames = useMemo(() => agentFramesAtTime(events, storyT, startingPosition), [events, storyT]);
  const roleByAgent = useMemo(() => {
    const map: Record<string, string> = {};
    for (const e of events) map[e.agent_id] ??= e.agent_role;
    return map;
  }, [events]);

  // Cut the camera to whoever's currently speaking/deciding -- re-fires only when the active agent changes.
  const activeMoment = useMemo(() => activeMomentAtTime(events, storyT), [events, storyT]);
  // Hold the wide establishing shot through the engine's entrance before cutting to anyone.
  // (A `?cam=` override pins the camera, so automatic cuts are off then.)
  const camPinned = useMemo(() => new URLSearchParams(window.location.search).has("cam"), []);
  const cutsAllowed = t > ENGINE_ENTRY_SECONDS + 1.5 && !camPinned;
  const [closeupCue, setCloseupCue] = useState(0);
  const lastSpeaker = useRef<string | null>(null);
  useEffect(() => {
    if (!cutsAllowed) return;
    const id = activeMoment?.agentId ?? null;
    if (id && id !== lastSpeaker.current) {
      lastSpeaker.current = id;
      setCloseupCue((n) => n + 1);
    }
  }, [activeMoment, cutsAllowed]);
  const closeupTarget = cutsAllowed && activeMoment ? frames[activeMoment.agentId]?.position : undefined;

  return (
    <Engine9Scene
      worldState={worldState}
      engineZOffset={engineZOffset}
      closeupCue={closeupTarget ? closeupCue : undefined}
      closeupTarget={closeupTarget}
    >
      {/* Models load asynchronously; the building and fire render immediately and characters pop in. */}
      <Suspense fallback={null}>
        {Object.entries(frames).map(([agentId, frame]) => {
          if (agentId === "director" || agentId === "human") return null;
          return (
            <RiggedCharacter
              key={agentId}
              visual={visualFor(agentId, roleByAgent[agentId] ?? "")}
              frame={frame}
              paused={paused}
            />
          );
        })}
      </Suspense>
    </Engine9Scene>
  );
}
