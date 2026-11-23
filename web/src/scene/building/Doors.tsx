import { palette } from "../palette";
import type { DoorLayout } from "../types";

/**
 * `openness` is keyed by door id, 0 closed to 1 fully open (matches
 * `WorldState.doors`). A door with no entry is drawn closed.
 */
export function Doors({ doors, openness }: { doors: DoorLayout[]; openness: Record<string, number> }) {
  return (
    <group name="doors">
      {doors.map((door) => (
        <Door key={door.id} door={door} openness={openness[door.id] ?? 0} />
      ))}
    </group>
  );
}

function Door({ door, openness }: { door: DoorLayout; openness: number }) {
  const height = 2.04;
  const thick = 0.055;
  const alongZ = door.axis === "z";
  const side = door.swing >= 0 ? -1 : 1;
  const angle = door.swing * Math.min(1, Math.max(0, openness));
  const leafPosition: [number, number, number] = alongZ
    ? [side * 0.07, height / 2, door.width / 2]
    : [door.width / 2, height / 2, side * 0.07];

  return (
    <group
      name={door.id}
      position={[door.x, 0, door.z]}
      userData={{ doorId: door.id, between: door.between, openness }}
    >
      <DoorFrame door={door} />
      <group rotation={[0, angle, 0]}>
        <mesh position={leafPosition} castShadow>
          <boxGeometry args={alongZ ? [thick, height, door.width * 0.94] : [door.width * 0.94, height, thick]} />
          <meshLambertMaterial color={palette.door} />
        </mesh>
        <mesh position={knobPosition(door, side)}>
          <sphereGeometry args={[0.04, 8, 8]} />
          <meshLambertMaterial color="#ead9b8" />
        </mesh>
      </group>
    </group>
  );
}

function knobPosition(door: DoorLayout, side: number): [number, number, number] {
  if (door.axis === "z") {
    return [side * 0.12, 1.02, door.width * 0.78];
  }
  return [door.width * 0.78, 1.02, side * 0.12];
}

function DoorFrame({ door }: { door: DoorLayout }) {
  const height = 2.16;
  const alongZ = door.axis === "z";
  const jamb: [number, number, number] = alongZ ? [0.1, height, 0.08] : [0.08, height, 0.1];
  const header: [number, number, number] = alongZ ? [0.1, 0.08, door.width + 0.08] : [door.width + 0.08, 0.08, 0.1];
  const end = door.width;
  return (
    <group>
      <mesh position={alongZ ? [0, height / 2, 0] : [0, height / 2, 0]} castShadow>
        <boxGeometry args={jamb} />
        <meshLambertMaterial color={palette.doorDark} />
      </mesh>
      <mesh position={alongZ ? [0, height / 2, end] : [end, height / 2, 0]} castShadow>
        <boxGeometry args={jamb} />
        <meshLambertMaterial color={palette.doorDark} />
      </mesh>
      <mesh position={alongZ ? [0, height, end / 2] : [end / 2, height, 0]}>
        <boxGeometry args={header} />
        <meshLambertMaterial color={palette.doorDark} />
      </mesh>
    </group>
  );
}
