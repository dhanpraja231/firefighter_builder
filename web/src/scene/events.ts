/**
 * The scene is a pure function of `WorldState`. Nothing in `scene/` mutates
 * this on its own: the Python simulation (or a replay/live timeline player in
 * the host app) owns every decision and feeds state in through
 * `Engine9SceneProps.worldState`.
 *
 * `applyWorldEvent` is a convenience reducer for folding one `WorldEvent` at
 * a time into a `WorldState`, e.g. while replaying a timeline of
 * `world_event` rows from the event log described in INTEGRATION.md.
 */

export interface LadderState {
  /** 0 stowed, 1 fully extended to `targetWindowId`. */
  deployed: number;
  targetWindowId: string | null;
}

export interface HoseState {
  active: boolean;
  targetWindowId: string | null;
}

export interface WorldState {
  /** roomId -> intensity, 0 hides the fire, 1 is a fully developed blaze. */
  fires: Record<string, number>;
  /** roomId -> intensity, independent of `fires` so smoke can outlast flame or drift from a room that isn't burning. */
  smoke: Record<string, number>;
  /** doorId -> openness, 0 closed, 1 fully open. */
  doors: Record<string, number>;
  /** windowId -> whether the glass has been broken (vented, breached, or burned through). */
  brokenWindows: Record<string, boolean>;
  ladder: LadderState;
  hose: HoseState;
  /** Fire engine light bar on/off. */
  engineLights: boolean;
}

export function createDefaultWorldState(): WorldState {
  return {
    fires: {},
    smoke: {},
    doors: {},
    brokenWindows: {},
    ladder: { deployed: 0, targetWindowId: null },
    hose: { active: false, targetWindowId: null },
    engineLights: true,
  };
}

export type WorldEvent =
  | { type: "fire"; roomId: string; intensity: number }
  | { type: "smoke"; roomId: string; intensity: number }
  | { type: "door"; doorId: string; openness: number }
  | { type: "window"; windowId: string; broken: boolean }
  | { type: "ladder"; deployed?: number; targetWindowId?: string | null }
  | { type: "hose"; active?: boolean; targetWindowId?: string | null }
  | { type: "engine_lights"; on: boolean };

/**
 * Folds one event into a new `WorldState` (never mutates the input).
 * This is the shape that belongs in `payload.world` on a `world_event` row
 * in the Python event log (see INTEGRATION.md, "Event schema").
 */
export function applyWorldEvent(state: WorldState, event: WorldEvent): WorldState {
  switch (event.type) {
    case "fire":
      return { ...state, fires: { ...state.fires, [event.roomId]: clamp01(event.intensity) } };
    case "smoke":
      return { ...state, smoke: { ...state.smoke, [event.roomId]: clamp01(event.intensity) } };
    case "door":
      return { ...state, doors: { ...state.doors, [event.doorId]: clamp01(event.openness) } };
    case "window":
      return { ...state, brokenWindows: { ...state.brokenWindows, [event.windowId]: event.broken } };
    case "ladder":
      return {
        ...state,
        ladder: {
          deployed: event.deployed === undefined ? state.ladder.deployed : clamp01(event.deployed),
          targetWindowId: event.targetWindowId === undefined ? state.ladder.targetWindowId : event.targetWindowId,
        },
      };
    case "hose":
      return {
        ...state,
        hose: {
          active: event.active === undefined ? state.hose.active : event.active,
          targetWindowId: event.targetWindowId === undefined ? state.hose.targetWindowId : event.targetWindowId,
        },
      };
    case "engine_lights":
      return { ...state, engineLights: event.on };
    default:
      return state;
  }
}

export function applyWorldEvents(state: WorldState, events: WorldEvent[]): WorldState {
  return events.reduce(applyWorldEvent, state);
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}
