import type { CharacterVisual } from "../scene/characters/visual";

/**
 * Visual identity per `agent_id`, matching `story/characters.md`. The orchestrator is free to use
 * any subset of these ids; the timeline player only renders agents it sees events for.
 *
 * Bodies are the rigged Quaternius characters from the `character` branch (`models/victims/`).
 * The four firefighters wear a hard hat in their accent color; victims differ by model, shirt color
 * and height (the child is a smaller body).
 */
export const ROSTER: Record<string, CharacterVisual> = {
  // Firefighters
  commander: { label: "Commander", kind: "robot", color: "#ffd166", height: 1.8, model: "suitMale", helmet: true },
  "scout-1": { label: "Scout", kind: "robot", color: "#4cc9f0", height: 1.65, model: "casualFemale", helmet: true },
  "hose-1": { label: "Hose bot", kind: "robot", color: "#4895ef", height: 1.8, model: "casualMale", helmet: true },
  "rescue-1": { label: "Rescue bot", kind: "robot", color: "#f94144", height: 1.75, model: "workerFemale", helmet: true },
  // Victims
  "victim-elderly": { label: "Mrs. Okafor", kind: "victim", color: "#9d4edd", height: 1.55, model: "oldClassyFemale" },
  "victim-parent": { label: "Parent", kind: "victim", color: "#43aa8b", height: 1.75, model: "casualMale" },
  "victim-child": { label: "Child", kind: "victim", color: "#f8961e", height: 1.1, model: "casualBald" },
  "victim-skeptic": { label: "Skeptic", kind: "victim", color: "#577590", height: 1.78, model: "suitMale" },
  "victim-teen": { label: "Teen", kind: "victim", color: "#f3722c", height: 1.62, model: "casualFemale" },
  "victim-regular": { label: "Neighbor", kind: "victim", color: "#90be6d", height: 1.7, model: "oldClassyMale" },
  "victim-couple-a": { label: "Couple (A)", kind: "victim", color: "#b5179e", height: 1.78, model: "casualBald" },
  "victim-couple-b": { label: "Couple (B)", kind: "victim", color: "#7209b7", height: 1.66, model: "workerFemale" },
};

export function visualFor(agentId: string, role: string): CharacterVisual {
  return (
    ROSTER[agentId] ?? {
      label: agentId,
      kind: role === "victim" ? "victim" : "robot",
      color: "#cccccc",
      height: 1.7,
      model: role === "victim" ? "casualMale" : "workerFemale",
      helmet: role !== "victim",
    }
  );
}
