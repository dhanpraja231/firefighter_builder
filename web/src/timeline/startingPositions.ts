/**
 * Default position before an agent's first `move` event, mirroring the room
 * placements in `agents/orchestrator.py` (ROOM_XZ / FLOOR_Y). Victims that
 * never get a `move` event (most of them -- they just stand in their room
 * until rescued) still need somewhere to render.
 */
export const STARTING_POSITION: Record<string, [number, number, number]> = {
  commander: [-8.0, 0, 3.5],
  "scout-1": [-5.4, 0, 6],
  "hose-1": [-1.21, 0, 1.4],
  "rescue-1": [-5.4, 0, 6],
  "victim-teen": [3, 0, 3.075],
  "victim-elderly": [3, 3, 9.075],
  "victim-couple-a": [13, 3, 9.075],
  "victim-couple-b": [13, 3, 9.075],
  "victim-skeptic": [3, 6, 9.075],
  "victim-parent": [13, 9, 9.075],
  "victim-child": [13, 9, 9.075],
  "victim-regular": [3, 12, 3.075],
};

export function startingPosition(agentId: string): [number, number, number] {
  return STARTING_POSITION[agentId] ?? [-5.4, 0, 6];
}
