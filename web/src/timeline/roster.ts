import type { CharacterVisual, RigKey } from "../scene/characters/visual";

/**
 * Visual identity per `agent_id`, matching `story/characters.md`. The orchestrator is free to use
 * any subset of these ids; the timeline player only renders agents it sees events for.
 *
 * Robots (the four firefighter roles) are the firefighter PMX from `runcycle/` with its run cycle and
 * leg IK (`Character.tsx`). Residents are rigged Quaternius characters (`rig`), chosen because their
 * clip sets include the reactions the story needs (flinch, plead, sit, collapse, celebrate). Each
 * resident also names a Rocketbox `model` for the `Character.tsx` fallback body.
 * `height` is the real-world height in meters the body is scaled to.
 */
export const ROSTER: Record<string, CharacterVisual> = {
  // Firefighter robots
  commander: { label: "Commander", kind: "robot", color: "#ffd166", height: 1.85 },
  "scout-1": { label: "Scout", kind: "robot", color: "#4cc9f0", height: 1.75 },
  "hose-1": { label: "Hose bot", kind: "robot", color: "#4895ef", height: 1.8 },
  "rescue-1": { label: "Rescue bot", kind: "robot", color: "#f94144", height: 1.9 },
  // Residents
  "victim-elderly": { label: "Mrs. Okafor", kind: "victim", color: "#9d4edd", rig: "oldClassyFemale", model: "Female_Adult_01", walkClip: "f_walk_slow_01", height: 1.6 },
  "victim-parent": { label: "Parent", kind: "victim", color: "#43aa8b", rig: "casualMale", model: "Male_Adult_01", walkClip: "m_walk_neutral", height: 1.78 },
  "victim-child": { label: "Child", kind: "victim", color: "#f8961e", rig: "casualBald", model: "Male_Child_01", height: 1.15 },
  "victim-skeptic": { label: "Skeptic", kind: "victim", color: "#577590", rig: "suitMale", model: "Business_Male_01", height: 1.78 },
  "victim-teen": { label: "Teen", kind: "victim", color: "#f3722c", rig: "casualFemale", model: "Female_Adult_03", height: 1.62 },
  "victim-regular": { label: "Neighbor", kind: "victim", color: "#90be6d", rig: "oldClassyMale", model: "Male_Adult_02", height: 1.72 },
  "victim-couple-a": { label: "Couple (A)", kind: "victim", color: "#b5179e", rig: "casualBald", model: "Business_Female_01", height: 1.8 },
  "victim-couple-b": { label: "Couple (B)", kind: "victim", color: "#7209b7", rig: "workerFemale", model: "Male_Adult_03", height: 1.68 },
};

export function visualFor(agentId: string, role: string): CharacterVisual {
  const rig: RigKey = "casualMale";
  return (
    ROSTER[agentId] ?? {
      label: agentId,
      kind: role === "victim" ? "victim" : "robot",
      color: "#cccccc",
      height: 1.75,
      rig,
      model: role === "victim" ? "Female_Adult_02" : undefined,
    }
  );
}
