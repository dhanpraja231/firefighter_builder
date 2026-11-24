import { useMemo } from "react";
import { Engine9Scene } from "../scene/Engine9Scene";
import { Character } from "../scene/characters/Character";
import { agentFramesAtTime, worldStateAtTime } from "../timeline/replay";
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
export function DemoScene({ events, t, shot = 0 }: { events: TimelineEvent[]; t: number; shot?: number }) {
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

  // The camera holds one of three static shots (STATIC_SHOTS), switched from the story panel.

  return (
    <Engine9Scene
      worldState={worldState}
      engineZOffset={engineZOffset}
      shot={shot}
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
