import type { RoomLayout, RoomKind } from "../types";

/**
 * Practical lighting per room -- without this every interior reads as a
 * dark box lit only by cool ambient/moonlight from outside. Warm color,
 * modest point light per room, roughly where a ceiling fixture would hang.
 */
const LIGHT_BY_KIND: Partial<Record<RoomKind, { color: string; intensity: number; distance: number }>> = {
  living: { color: "#ffc07a", intensity: 5.5, distance: 9 },
  bedroom: { color: "#ffc991", intensity: 4.6, distance: 8.5 },
  kitchen: { color: "#ffe3b4", intensity: 6, distance: 9 },
  hall: { color: "#ffd3a0", intensity: 3.8, distance: 8 },
  landing: { color: "#ffd3a0", intensity: 3.4, distance: 8 },
};

/**
 * Two lights per room: a bright main at ceiling height plus a low fill, so
 * floors and furniture are lit rather than just the ceiling plane. `decay=1`
 * (not the physical 2) deliberately keeps falloff gentle enough that a whole
 * room reads lit from a wide exterior camera.
 */
export function RoomLighting({ room }: { room: RoomLayout }) {
  const spec = LIGHT_BY_KIND[room.kind];
  if (!spec) return null;
  const x = room.x + room.w / 2;
  const z = room.z + room.d / 2;
  return (
    <group name={`light-${room.id}`}>
      <pointLight position={[x, 2.2, z]} color={spec.color} intensity={spec.intensity} distance={spec.distance} decay={1.5} />
      <pointLight position={[x, 0.85, z]} color={spec.color} intensity={spec.intensity * 0.35} distance={spec.distance * 0.8} decay={1.5} />
      <mesh position={[x, 2.36, z]}>
        <sphereGeometry args={[0.07, 8, 8]} />
        <meshBasicMaterial color={spec.color} toneMapped={false} />
      </mesh>
    </group>
  );
}
