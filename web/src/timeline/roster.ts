import type { CharacterVisual } from "../scene/characters/Character";

/**
 * Visual identity per `agent_id`, matching `story/characters.md`. The
 * orchestrator is free to use any subset of these ids; the timeline player
 * only renders agents it sees events for.
 */
export const ROSTER: Record<string, CharacterVisual> = {
  commander: { label: "Commander", kind: "robot", color: "#ffd166", height: 1.25 },
  "scout-1": { label: "Scout", kind: "robot", color: "#4cc9f0", height: 1.0 },
  "hose-1": { label: "Hose bot", kind: "robot", color: "#4895ef", height: 1.3 },
  "rescue-1": { label: "Rescue bot", kind: "robot", color: "#f94144", height: 1.35 },
  "victim-elderly": { label: "Mrs. Okafor", kind: "victim", color: "#9d4edd", height: 1.55 },
  "victim-parent": { label: "Parent", kind: "victim", color: "#43aa8b", height: 1.68 },
  "victim-child": { label: "Child", kind: "victim", color: "#f8961e", height: 1.1 },
  "victim-skeptic": { label: "Skeptic", kind: "victim", color: "#577590", height: 1.7 },
  "victim-teen": { label: "Teen", kind: "victim", color: "#f3722c", height: 1.65 },
  "victim-regular": { label: "Neighbor", kind: "victim", color: "#90be6d", height: 1.68 },
  "victim-couple-a": { label: "Couple (A)", kind: "victim", color: "#b5179e", height: 1.65 },
  "victim-couple-b": { label: "Couple (B)", kind: "victim", color: "#7209b7", height: 1.65 },
};

export function visualFor(agentId: string, role: string): CharacterVisual {
  return (
    ROSTER[agentId] ?? {
      label: agentId,
      kind: role === "victim" ? "victim" : "robot",
      color: "#cccccc",
    }
  );
}
