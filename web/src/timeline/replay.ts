import { applyWorldEvent, createDefaultWorldState, type WorldState } from "../scene/events";
import type { TimelineEvent } from "./schema";

export interface AgentFrame {
  position: [number, number, number];
  heading: number;
  utterance: string | null;
  status: string | null;
  /** True while interpolating between two `move` events -- drives the walk-cycle animation. */
  moving: boolean;
}

/** Folds every `world_event` row up to `t` into a `WorldState`. Mirrors INTEGRATION.md section 4. */
export function worldStateAtTime(events: TimelineEvent[], t: number): WorldState {
  return events
    .filter((e) => e.type === "world_event" && e.t_sim <= t && e.payload.world)
    .reduce((state, e) => applyWorldEvent(state, e.payload.world), createDefaultWorldState());
}

/**
 * Current position (interpolated between the surrounding `move` events),
 * last utterance (if recent), and last known status for every agent that
 * has produced at least one event by time `t`.
 */
export function agentFramesAtTime(
  events: TimelineEvent[],
  t: number,
  defaultPosition: (agentId: string) => [number, number, number],
): Record<string, AgentFrame> {
  const byAgent = groupBy(events, (e) => e.agent_id);
  const frames: Record<string, AgentFrame> = {};

  for (const [agentId, agentEvents] of Object.entries(byAgent)) {
    const moves = agentEvents.filter((e) => e.type === "move" && e.payload.position);
    const past = moves.filter((e) => e.t_sim <= t);
    const upcoming = moves.find((e) => e.t_sim > t);
    const last = past[past.length - 1];

    let position: [number, number, number];
    let heading = 0;
    if (last && upcoming) {
      const a = last.payload.position;
      const b = upcoming.payload.position;
      const span = upcoming.t_sim - last.t_sim;
      const frac = span > 0 ? (t - last.t_sim) / span : 1;
      position = [lerp(a.x, b.x, frac), lerp(a.y, b.y, frac), lerp(a.z, b.z, frac)];
      const dx = b.x - a.x;
      const dz = b.z - a.z;
      if (dx * dx + dz * dz > 1e-6) heading = Math.atan2(dx, dz);
    } else if (last) {
      position = [last.payload.position.x, last.payload.position.y, last.payload.position.z];
    } else {
      position = defaultPosition(agentId);
    }

    const speaks = agentEvents.filter((e) => e.type === "speak" && e.t_sim <= t);
    const lastSpeak = speaks[speaks.length - 1];
    const utterance = lastSpeak && t - lastSpeak.t_sim < 5 ? (lastSpeak.payload.utterance ?? null) : null;

    const statuses = agentEvents.filter((e) => e.type === "status" && e.t_sim <= t);
    const status = statuses[statuses.length - 1]?.payload.victim_status ?? null;

    frames[agentId] = { position, heading, utterance, status, moving: Boolean(last && upcoming) };
  }
  return frames;
}

export interface ActiveMoment {
  agentId: string;
  role: string;
  /** What's on screen right now, for the caption bar -- a speech line if one is recent, else the latest action/reasoning. */
  line: string;
  kind: "speak" | "action";
}

/**
 * The single most recent noteworthy thing happening at time `t`, across all
 * agents -- drives both the caption bar and which character the camera cuts
 * to. Prefers a recent `speak` (closeup on whoever's talking); falls back to
 * the latest `act`/`decide`/`world_event` reasoning so the caption bar never
 * goes blank between lines of dialogue.
 */
export function activeMomentAtTime(events: TimelineEvent[], t: number): ActiveMoment | null {
  const past = events.filter((e) => e.t_sim <= t).sort((a, b) => a.t_sim - b.t_sim);
  if (past.length === 0) return null;

  for (let i = past.length - 1; i >= 0; i--) {
    const e = past[i];
    if (e.type === "speak" && t - e.t_sim < 5) {
      return { agentId: e.agent_id, role: e.agent_role, line: e.payload.utterance, kind: "speak" };
    }
  }
  for (let i = past.length - 1; i >= 0; i--) {
    const e = past[i];
    if (e.reasoning && (e.type === "act" || e.type === "decide" || e.type === "world_event" || e.type === "request_approval")) {
      return { agentId: e.agent_id, role: e.agent_role, line: e.reasoning, kind: "action" };
    }
  }
  return null;
}

export interface DecisionLogRow {
  seq: number;
  t_sim: number;
  agentId: string;
  role: string;
  type: TimelineEvent["type"];
  summary: string;
  reasoning: string | null;
}

/** Rows for the decision-log panel, oldest first, up to time `t`. */
export function decisionLogAtTime(events: TimelineEvent[], t: number): DecisionLogRow[] {
  return events
    .filter((e) => e.t_sim <= t)
    .filter((e) => e.type === "decide" || e.type === "act" || e.type === "request_approval" || e.type === "approval" || e.type === "world_event")
    .map((e) => ({
      seq: e.seq,
      t_sim: e.t_sim,
      agentId: e.agent_id,
      role: e.agent_role,
      type: e.type,
      summary: summarize(e),
      reasoning: e.reasoning ?? null,
    }));
}

function summarize(e: TimelineEvent): string {
  if (e.type === "world_event") return e.payload.world?.type ? `world: ${e.payload.world.type}` : "world event";
  if (e.type === "approval") return `approval: ${e.payload.action}`;
  if (e.type === "request_approval") return `requests approval: ${e.payload.action} -> ${e.payload.target ?? ""}`;
  return `${e.payload.action ?? e.type}${e.payload.target ? ` -> ${e.payload.target}` : ""}`;
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function groupBy<T>(items: T[], key: (item: T) => string): Record<string, T[]> {
  const out: Record<string, T[]> = {};
  for (const item of items) {
    (out[key(item)] ??= []).push(item);
  }
  return out;
}
