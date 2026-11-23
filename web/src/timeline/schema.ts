/** Mirrors SPEC.md section 1.1. One row as the orchestrator (or a replay file) produces it. */
export type EventType =
  | "move"
  | "speak"
  | "decide"
  | "act"
  | "request_approval"
  | "approval"
  | "world_event"
  | "status";

export interface TimelineEvent {
  seq: number;
  t_sim: number;
  agent_id: string;
  agent_role: string;
  type: EventType;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload: Record<string, any>;
  reasoning?: string | null;
  confidence?: number | null;
  model?: string | null;
}
