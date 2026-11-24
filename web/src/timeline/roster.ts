import type { CharacterVisual } from "../scene/characters/Character";

/**
 * Visual identity per `agent_id`, matching `story/characters.md`. The
 * orchestrator is free to use any subset of these ids; the timeline player
 * only renders agents it sees events for.
 *
 * Bodies come from `runcycle/`: every robot role uses the firefighter PMX
 * (`public/pmx/Firefighter.pmx`), every victim a Microsoft Rocketbox GLB
 * (`public/people/<model>.glb`, built by `models/tools/build_people.sh`).
 * `height` is the real-world height in meters the body is scaled to.
 */
export const ROSTER: Record<string, CharacterVisual> = {
  commander: { label: "Commander", kind: "robot", color: "#ffd166", height: 1.85 },
  "scout-1": { label: "Scout", kind: "robot", color: "#4cc9f0", height: 1.75 },
  "hose-1": { label: "Hose bot", kind: "robot", color: "#4895ef", height: 1.8 },
  "rescue-1": { label: "Rescue bot", kind: "robot", color: "#f94144", height: 1.9 },
  "victim-elderly": { label: "Mrs. Okafor", kind: "victim", color: "#9d4edd", model: "Female_Adult_01", walkClip: "f_walk_slow_01", height: 1.6 },
  "victim-parent": { label: "Parent", kind: "victim", color: "#43aa8b", model: "Male_Adult_01", walkClip: "m_walk_neutral" },
  "victim-child": { label: "Child", kind: "victim", color: "#f8961e", model: "Male_Child_01", height: 1.2 },
  "victim-skeptic": { label: "Skeptic", kind: "victim", color: "#577590", model: "Business_Male_01" },
  "victim-teen": { label: "Teen", kind: "victim", color: "#f3722c", model: "Female_Adult_03", height: 1.62 },
  "victim-regular": { label: "Neighbor", kind: "victim", color: "#90be6d", model: "Male_Adult_02" },
  "victim-couple-a": { label: "Couple (A)", kind: "victim", color: "#b5179e", model: "Business_Female_01" },
  "victim-couple-b": { label: "Couple (B)", kind: "victim", color: "#7209b7", model: "Male_Adult_03" },
};

export function visualFor(agentId: string, role: string): CharacterVisual {
  return (
    ROSTER[agentId] ?? {
      label: agentId,
      kind: role === "victim" ? "victim" : "robot",
      color: "#cccccc",
      model: role === "victim" ? "Female_Adult_02" : undefined,
    }
  );
}
