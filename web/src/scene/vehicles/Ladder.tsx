import { palette } from "../palette";

const MAX_LENGTH = 16;
const RAIL_GAP = 0.42;
const RUNG_COUNT = 16;

/**
 * Telescoping aerial ladder hinged at `origin`, aimed at `target`. `deployed`
 * (0..1) scales how far it extends toward the target; rotation is computed
 * here purely from geometry, same as a real turntable ladder. The caller
 * (worldState.ladder) owns deployed and the target, not this component.
 */
export function Ladder({
  origin,
  target,
  deployed,
}: {
  origin: [number, number, number];
  target: [number, number, number] | null;
  deployed: number;
}) {
  const clamped = Math.min(1, Math.max(0, deployed));
  if (!target || clamped <= 0.01) {
    return (
      <group name="ladder" position={origin}>
        <TurntableBase />
      </group>
    );
  }

  const dx = target[0] - origin[0];
  const dy = target[1] - origin[1];
  const dz = target[2] - origin[2];
  const horizontal = Math.hypot(dx, dz);
  const distance = Math.hypot(horizontal, dy);
  const yaw = Math.atan2(dx, dz);
  const pitch = Math.atan2(dy, horizontal);
  const length = Math.min(MAX_LENGTH, distance) * clamped;

  return (
    <group name="ladder" position={origin}>
      <TurntableBase rotation={yaw} />
      <group rotation={[0, yaw, 0]}>
        <group rotation={[-pitch, 0, 0]}>
          <RailAndRungs length={Math.max(length, 0.01)} />
        </group>
      </group>
    </group>
  );
}

function TurntableBase({ rotation = 0 }: { rotation?: number }) {
  return (
    <mesh rotation={[0, rotation, 0]}>
      <cylinderGeometry args={[0.55, 0.6, 0.22, 16]} />
      <meshLambertMaterial color="#2b2b2b" />
    </mesh>
  );
}

function RailAndRungs({ length }: { length: number }) {
  const rungs = Array.from({ length: RUNG_COUNT }, (_, i) => ((i + 0.5) / RUNG_COUNT) * length);
  return (
    <group>
      {[-RAIL_GAP / 2, RAIL_GAP / 2].map((x) => (
        <mesh key={x} position={[x, 0, length / 2]} castShadow>
          <boxGeometry args={[0.07, 0.1, length]} />
          <meshLambertMaterial color={palette.metal} />
        </mesh>
      ))}
      {rungs.map((z) => (
        <mesh key={z} position={[0, 0, z]}>
          <boxGeometry args={[RAIL_GAP, 0.05, 0.045]} />
          <meshLambertMaterial color={palette.metal} />
        </mesh>
      ))}
    </group>
  );
}
