import { FLOOR_ACCENTS, type FloorAccent } from "../palette";
import { BUILDING_WIDTH, type RoomLayout } from "../types";

/**
 * Static furniture per room, keyed off the same `FLOOR_ACCENTS` colors the
 * floor material already uses. Placement only — nothing here reacts to
 * `WorldState` (fire, smoke); furniture burns visually only in the sense
 * that `FireEffect` renders on top of it.
 */
export function Furniture({ room }: { room: RoomLayout }) {
  const accent = FLOOR_ACCENTS[room.floorId];
  switch (room.kind) {
    case "living":
      return <LivingRoom room={room} accent={accent} />;
    case "bedroom":
      return <Bedroom room={room} accent={accent} />;
    case "kitchen":
      return <Kitchen room={room} accent={accent} />;
    default:
      return null;
  }
}

/** Rooms toward the west half back onto the stair core on their east side, and vice versa. */
function coreSideX(room: RoomLayout): number {
  return room.x < BUILDING_WIDTH / 2 ? room.x + room.w - 0.35 : room.x + 0.35;
}

function LivingRoom({ room, accent }: { room: RoomLayout; accent: FloorAccent }) {
  const midX = room.x + room.w / 2;
  const backZ = room.z + room.d - 0.55;
  return (
    <group name={`furniture-${room.id}`}>
      <mesh position={[midX, 0.025, room.z + room.d * 0.55]} receiveShadow>
        <boxGeometry args={[room.w * 0.6, 0.02, room.d * 0.5]} />
        <meshLambertMaterial color={accent.rug} />
      </mesh>
      <mesh position={[midX, 0.21, backZ]} castShadow receiveShadow>
        <boxGeometry args={[room.w * 0.55, 0.42, 0.75]} />
        <meshLambertMaterial color={accent.sofa} />
      </mesh>
      <mesh position={[midX, 0.56, backZ - 0.3]} castShadow>
        <boxGeometry args={[room.w * 0.55, 0.5, 0.16]} />
        <meshLambertMaterial color={accent.sofa} />
      </mesh>
      <mesh position={[midX, 0.2, backZ - 1.25]} castShadow receiveShadow>
        <boxGeometry args={[0.9, 0.07, 0.55]} />
        <meshLambertMaterial color={accent.cabinet} />
      </mesh>
      <mesh position={[coreSideX(room), 0.35, room.z + 0.5]} castShadow>
        <boxGeometry args={[0.4, 0.7, 0.4]} />
        <meshLambertMaterial color={accent.cabinet} />
      </mesh>
    </group>
  );
}

function Kitchen({ room, accent }: { room: RoomLayout; accent: FloorAccent }) {
  const midX = room.x + room.w / 2;
  const counterZ = room.z + room.d - 0.4;
  const counterWidth = room.w * 0.68;
  return (
    <group name={`furniture-${room.id}`}>
      <mesh position={[midX, 0.44, counterZ]} castShadow receiveShadow>
        <boxGeometry args={[counterWidth, 0.88, 0.6]} />
        <meshLambertMaterial color={accent.cabinet} />
      </mesh>
      <mesh position={[midX, 0.9, counterZ]} castShadow>
        <boxGeometry args={[counterWidth + 0.04, 0.04, 0.64]} />
        <meshLambertMaterial color="#2c2a28" />
      </mesh>
      <mesh position={[midX - counterWidth * 0.3, 0.925, counterZ]}>
        <boxGeometry args={[0.6, 0.015, 0.5]} />
        <meshLambertMaterial color="#161514" />
      </mesh>
      <mesh position={[coreSideX(room), 0.85, room.z + 0.5]} castShadow receiveShadow>
        <boxGeometry args={[0.65, 1.7, 0.6]} />
        <meshLambertMaterial color="#cfd6da" />
      </mesh>
      <mesh position={[midX, 0.42, room.z + room.d * 0.3]} castShadow receiveShadow>
        <boxGeometry args={[0.7, 0.05, 0.7]} />
        <meshLambertMaterial color={accent.wood} />
      </mesh>
      {[-0.28, 0.28].map((dx) => (
        <mesh key={dx} position={[midX + dx, 0.2, room.z + room.d * 0.3 + 0.28]} castShadow>
          <cylinderGeometry args={[0.16, 0.16, 0.4, 10]} />
          <meshLambertMaterial color={accent.cabinet} />
        </mesh>
      ))}
    </group>
  );
}

function Bedroom({ room, accent }: { room: RoomLayout; accent: FloorAccent }) {
  const bedX = room.x + room.w * 0.35;
  const bedZ = room.z + room.d - 0.95;
  return (
    <group name={`furniture-${room.id}`}>
      <mesh position={[room.x + room.w / 2, 0.025, room.z + room.d * 0.5]} receiveShadow>
        <boxGeometry args={[room.w * 0.5, 0.02, room.d * 0.4]} />
        <meshLambertMaterial color={accent.rug} />
      </mesh>
      <mesh position={[bedX, 0.26, bedZ]} castShadow receiveShadow>
        <boxGeometry args={[1.4, 0.5, 2.0]} />
        <meshLambertMaterial color={accent.bed} />
      </mesh>
      <mesh position={[bedX, 0.6, bedZ + 0.85]} castShadow>
        <boxGeometry args={[1.4, 0.7, 0.12]} />
        <meshLambertMaterial color={accent.cabinet} />
      </mesh>
      <mesh position={[bedX + 0.95, 0.3, bedZ]} castShadow>
        <boxGeometry args={[0.4, 0.5, 0.4]} />
        <meshLambertMaterial color={accent.cabinet} />
      </mesh>
    </group>
  );
}
