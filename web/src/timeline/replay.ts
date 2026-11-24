import { applyWorldEvent, createDefaultWorldState, type WorldState } from "../scene/events";
import { planRoute, sampleRoute, type Vec3 } from "./route";
import type { TimelineEvent } from "./schema";

/** What a character's body is doing. Each maps to a clip in the rigged models (see RiggedCharacter). */
export type AnimName =
  | "idle"
  | "walk"
  | "run"
  | "carry"
  | "flinch"
  | "collapse"
  | "celebrate"
  | "pickup"
  | "sit"
  | "plead"
  | "argue";

const ANIM_NAMES: ReadonlySet<string> = new Set<AnimName>([
  "idle", "walk", "run", "carry", "flinch", "collapse", "celebrate", "pickup", "sit", "plead", "argue",
]);

/** Seconds a one-shot reaction stays on screen before the character returns to its base pose. */
const ONE_SHOT_SECONDS: Partial<Record<AnimName, number>> = {
  flinch: 0.8,
  pickup: 1.3,
  celebrate: 2.0,
  plead: 2.4,
  argue: 2.4,
};

/** Idle characters turn toward the establishing-shot camera (south-west) so their faces and gestures read on screen. */
export const IDLE_HEADING = Math.atan2(-32, -37);

/** Faster than this (m/s) a walk becomes a run. */
const RUN_SPEED = 2.4;

export interface AgentFrame {
  position: [number, number, number];
  heading: number;
  utterance: string | null;
  status: string | null;
  /** True while interpolating between two `move` events -- drives the walk-cycle animation. */
  moving: boolean;
  anim: AnimName;
  /** Changes whenever a (one-shot) animation should restart, e.g. `flinch#42`. */
  animKey: string;
  /** Ground speed in m/s while moving, so the clip's playback rate matches the distance covered. */
  speed: number;
  speaking: boolean;
}

/** A room's fire/smoke ramps toward its next sampled value over at most this many seconds. */
const RAMP_SECONDS = 6;

/**
 * Folds every `world_event` row up to `t` into a `WorldState` (INTEGRATION.md section 4), then smooths
 * fire and smoke: each room's intensity glides from one sampled value toward the next instead of
 * jumping, so the blaze visibly grows, spreads into a new room, and dies back under the hose.
 */
export function worldStateAtTime(events: TimelineEvent[], t: number): WorldState {
  const folded = events
    .filter((e) => e.type === "world_event" && e.t_sim <= t && e.payload.world)
    .reduce((state, e) => applyWorldEvent(state, e.payload.world), createDefaultWorldState());
  return {
    ...folded,
    fires: rampedIntensities(events, t, "fire"),
    smoke: rampedIntensities(events, t, "smoke"),
  };
}

function rampedIntensities(events: TimelineEvent[], t: number, kind: "fire" | "smoke"): Record<string, number> {
  const samples = new Map<string, Array<{ t: number; v: number }>>();
  for (const e of events) {
    const w = e.type === "world_event" ? e.payload.world : null;
    if (!w || w.type !== kind || typeof w.roomId !== "string") continue;
    const list = samples.get(w.roomId) ?? [];
    list.push({ t: e.t_sim, v: Math.min(1, Math.max(0, Number(w.intensity) || 0)) });
    samples.set(w.roomId, list);
  }
  const out: Record<string, number> = {};
  for (const [roomId, list] of samples) {
    let i = -1;
    for (let k = 0; k < list.length; k++) {
      if (list[k].t <= t) i = k;
      else break;
    }
    if (i < 0) continue; // not ignited yet
    const cur = list[i];
    const next = list[i + 1];
    if (!next) {
      out[roomId] = cur.v;
      continue;
    }
    const span = Math.min(next.t - cur.t, RAMP_SECONDS);
    const f = span > 0 ? Math.min(1, (t - cur.t) / span) : 1;
    out[roomId] = cur.v + (next.v - cur.v) * f;
  }
  return out;
}

function asVec(p: { x: number; y: number; z: number }): Vec3 {
  return [p.x, p.y, p.z];
}

function animHint(e: TimelineEvent): AnimName | null {
  const hint = e.payload?.anim;
  return typeof hint === "string" && ANIM_NAMES.has(hint) ? (hint as AnimName) : null;
}

/**
 * Current position (routed through the building's doors and stairs between the surrounding `move`
 * events), facing, animation, last utterance (if recent), and last known status for every agent that
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
    const lastIdx = lastIndexAtOrBefore(moves, t);
    const last = lastIdx >= 0 ? moves[lastIdx] : undefined;
    const upcoming = moves[lastIdx + 1];

    let position: Vec3;
    let heading = IDLE_HEADING;
    let moving = false;
    let speed = 0;

    if (last && upcoming) {
      const route = planRoute(asVec(last.payload.position), asVec(upcoming.payload.position));
      const span = upcoming.t_sim - last.t_sim;
      const frac = span > 0 ? (t - last.t_sim) / span : 1;
      const sample = sampleRoute(route, frac);
      position = sample.position;
      moving = route.total > 0.05;
      speed = span > 0 ? route.total / span : 0;
      if (moving) heading = sample.heading;
    } else if (last) {
      position = asVec(last.payload.position);
    } else {
      position = defaultPosition(agentId);
    }

    const speaks = agentEvents.filter((e) => e.type === "speak" && e.t_sim <= t);
    const lastSpeak = speaks[speaks.length - 1];
    const utterance = lastSpeak && t - lastSpeak.t_sim < 5 ? (lastSpeak.payload.utterance ?? null) : null;

    const statuses = agentEvents.filter((e) => e.type === "status" && e.t_sim <= t);
    const lastStatus = statuses[statuses.length - 1];
    const status = lastStatus?.payload.victim_status ?? null;

    const { anim, animKey } = pickAnim(agentEvents, t, { moving, speed, upcoming, status, lastStatus });

    frames[agentId] = {
      position,
      heading,
      utterance,
      status,
      moving,
      anim,
      animKey,
      speed,
      speaking: utterance !== null,
    };
  }
  return frames;
}

function pickAnim(
  agentEvents: TimelineEvent[],
  t: number,
  ctx: {
    moving: boolean;
    speed: number;
    upcoming: TimelineEvent | undefined;
    status: string | null;
    lastStatus: TimelineEvent | undefined;
  },
): { anim: AnimName; animKey: string } {
  // A lost victim stays down for the rest of the film.
  if (ctx.status === "lost" && ctx.lastStatus) return { anim: "collapse", animKey: `collapse#${ctx.lastStatus.seq}` };

  // Most recent one-shot reaction (explicit hint, or implied by a status change) that is still playing.
  type Shot = { anim: AnimName; seq: number; at: number };
  let shot: Shot | null = null;
  const consider = (anim: AnimName, e: TimelineEvent) => {
    const window = ONE_SHOT_SECONDS[anim];
    if (window === undefined) return;
    const age = t - e.t_sim;
    if (age >= 0 && age < window && (!shot || e.t_sim >= shot.at)) shot = { anim, seq: e.seq, at: e.t_sim };
  };
  for (const e of agentEvents) {
    if (e.t_sim > t) break;
    const hint = animHint(e);
    if (hint) consider(hint, e);
    if (e.type === "status") {
      const s = e.payload.victim_status;
      if (s === "found") consider("plead", e);
      if (s === "rescued") consider("celebrate", e);
    }
  }
  const active = shot as Shot | null;
  if (active) return { anim: active.anim, animKey: `${active.anim}#${active.seq}` };

  // Held pose: a character told to sit stays seated until it moves or gets a new hint.
  let held: AnimName | null = null;
  for (const e of agentEvents) {
    if (e.t_sim > t) break;
    const hint = animHint(e);
    if (hint) held = hint;
    else if (e.type === "move") held = null;
  }
  if (held === "sit" && !ctx.moving) return { anim: "sit", animKey: "sit" };

  if (ctx.moving) {
    const hint = ctx.upcoming ? animHint(ctx.upcoming) : null;
    if (hint === "carry") return { anim: "carry", animKey: ctx.speed > RUN_SPEED ? "carry-fast" : "carry" };
    if (hint === "run" || (hint !== "walk" && ctx.speed > RUN_SPEED)) return { anim: "run", animKey: "run" };
    return { anim: "walk", animKey: "walk" };
  }
  return { anim: "idle", animKey: "idle" };
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

/** Most rows the panel keeps; older decisions scroll off like a live feed. */
const DECISION_LOG_ROWS = 40;

/**
 * Rows for the decision-log panel, oldest first, up to time `t`. The engine emits a steady stream of
 * fire/smoke intensity updates; those animate the scene but are noise in a log, so only world events
 * that carry a reason (a new ignition, a twist) are listed.
 */
export function decisionLogAtTime(events: TimelineEvent[], t: number): DecisionLogRow[] {
  return events
    .filter((e) => e.t_sim <= t)
    .filter((e) => e.type !== "world_event" || Boolean(e.reasoning))
    .filter((e) => e.type === "decide" || e.type === "act" || e.type === "request_approval" || e.type === "approval" || e.type === "world_event")
    .slice(-DECISION_LOG_ROWS)
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

/** Index of the last element with `t_sim <= t`, or -1. Events are ordered by time. */
function lastIndexAtOrBefore(items: TimelineEvent[], t: number): number {
  let idx = -1;
  for (let i = 0; i < items.length; i++) {
    if (items[i].t_sim <= t) idx = i;
    else break;
  }
  return idx;
}

function groupBy<T>(items: T[], key: (item: T) => string): Record<string, T[]> {
  const out: Record<string, T[]> = {};
  for (const item of items) {
    (out[key(item)] ??= []).push(item);
  }
  return out;
}
