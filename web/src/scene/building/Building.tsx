import type { WorldState } from "../events";
import type { BuildingLayout, FloorLayout } from "../types";
import { Doors } from "./Doors";
import { FloorStructure } from "./FloorStructure";
import { Staircase } from "./Staircase";
import { Walls } from "./Walls";
import { Windows } from "./Windows";

/**
 * All five stories stacked on the shared Y axis, with a switchback stair
 * connecting every consecutive pair of floors through the open stairwell
 * core. Door and window appearance come from `worldState`; nothing here
 * decides fire, smoke, or outcomes.
 */
export function Building({ layout, worldState }: { layout: BuildingLayout; worldState: WorldState }) {
  return (
    <group name="building">
      {layout.floors.map((floor) => (
        <Floor key={floor.id} floor={floor} worldState={worldState} />
      ))}
    </group>
  );
}

function Floor({ floor, worldState }: { floor: FloorLayout; worldState: WorldState }) {
  return (
    <group name={`floor-${floor.id}`} position={[0, floor.y, 0]}>
      <FloorStructure floor={floor} />
      <Walls segments={floor.walls} />
      <Doors doors={floor.doors} openness={worldState.doors} />
      <Windows windows={floor.windows} fires={worldState.fires} broken={worldState.brokenWindows} />
      {floor.id < 5 && <Staircase />}
    </group>
  );
}
