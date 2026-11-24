import { useEffect, useMemo, useRef, useState } from "react";
import { Engine9Scene } from "../scene/Engine9Scene";
import { Character } from "../scene/characters/Character";
import { activeMomentAtTime, agentFramesAtTime, worldStateAtTime } from "../timeline/replay";
import { visualFor } from "../timeline/roster";
import { startingPosition } from "../timeline/startingPositions";
import type { TimelineEvent } from "../timeline/schema";

/** Seconds the scene opens on: the engine driving in before any agent decision plays. */
export const ENGINE_ENTRY_SECONDS = 3.5;
const ENGINE_ENTRY_START_OFFSET = 16; // meters down the street the engine starts from
const MIN_SHOT_SECONDS = 4; // hold each closeup at least this long

function easeOutCubic(x: number): number {
  return 1 - Math.pow(1 - x, 3);
}

/** Renders one instant of a run: the engine's entrance, the building's WorldState, and every agent's frame. */
export function DemoScene({ events, t }: { events: TimelineEvent[]; t: number }) {
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

  // Cut the camera to whoever's currently speaking/deciding. Only agents with a body in the scene
  // (they have move events) can be framed, and each shot is held at least MIN_SHOT_SECONDS so the
  // camera doesn't jump on every event. Between cuts the camera follows that agent as they move.
  const activeMoment = useMemo(() => activeMomentAtTime(events, storyT), [events, storyT]);
  const embodied = useMemo(() => new Set(events.filter((e) => e.type === "move").map((e) => e.agent_id)), [events]);
  // Hold the wide establishing shot through the engine's entrance before cutting to anyone.
  const cutsAllowed = t > ENGINE_ENTRY_SECONDS + 1.5;
  const [closeupCue, setCloseupCue] = useState(0);
  const [shotAgent, setShotAgent] = useState<string | null>(null);
  const lastCutAt = useRef(-Infinity);
  useEffect(() => {
    if (!cutsAllowed) return;
    const id = activeMoment?.agentId ?? null;
    if (!id || id === shotAgent || !embodied.has(id) || id === "director" || id === "human") return;
    if (t - lastCutAt.current < MIN_SHOT_SECONDS) return;
    lastCutAt.current = t;
    setShotAgent(id);
    setCloseupCue((n) => n + 1);
  }, [activeMoment, cutsAllowed, embodied, shotAgent, t]);
  useEffect(() => {
    // a new run or a replay from the start goes back to the wide shot
    if (t < 0.5) { setShotAgent(null); lastCutAt.current = -Infinity; }
  }, [t, events]);
  const closeupTarget = cutsAllowed && shotAgent ? frames[shotAgent]?.position : undefined;

  return (
    <Engine9Scene
      worldState={worldState}
      engineZOffset={engineZOffset}
      closeupCue={closeupTarget ? closeupCue : undefined}
      closeupTarget={closeupTarget}
    >
      {Object.entries(frames).map(([agentId, frame]) => {
        if (agentId === "director" || agentId === "human") return null;
        const status = frame.status;
        return (
          <Character
            key={agentId}
            position={frame.position}
            heading={frame.heading}
            visual={visualFor(agentId, roleByAgent[agentId] ?? "")}
            utterance={frame.utterance}
            dimmed={status === "rescued" || status === "lost"}
            moving={frame.moving}
          />
        );
      })}
    </Engine9Scene>
  );
}
