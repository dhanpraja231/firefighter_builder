import { FLOOR_HEIGHT } from "../types";
import { palette } from "../palette";

const STEPS = 8;

/**
 * Switchback between this floor and the one above, in the central core.
 * Drawn in the lower floor's local space, where y = 3 meets the next story.
 */
export function Staircase() {
  return (
    <group name="staircase">
      <Flight x={6.25} width={1.55} z0={4.05} z1={7.5} y0={0.02} y1={FLOOR_HEIGHT / 2} />
      <mesh position={[8, FLOOR_HEIGHT / 2 - 0.05, 7.95]} castShadow receiveShadow>
        <boxGeometry args={[3.5, 0.1, 1.15]} />
        <meshLambertMaterial color={palette.tread} />
      </mesh>
      <Flight x={8.2} width={1.55} z0={7.5} z1={3.9} y0={FLOOR_HEIGHT / 2} y1={FLOOR_HEIGHT} />
      <mesh position={[8, FLOOR_HEIGHT / 2 + 0.42, 8.45]}>
        <boxGeometry args={[3.35, 0.06, 0.06]} />
        <meshLambertMaterial color={palette.rail} />
      </mesh>
    </group>
  );
}

function Flight({
  x,
  width,
  z0,
  z1,
  y0,
  y1,
}: {
  x: number;
  width: number;
  z0: number;
  z1: number;
  y0: number;
  y1: number;
}) {
  const rise = (y1 - y0) / STEPS;
  const run = (z1 - z0) / STEPS;
  const tread = Math.abs(run) * 0.94;
  const length = Math.hypot(z1 - z0, y1 - y0);
  const angle = -Math.atan2(y1 - y0, z1 - z0);
  const midY = (y0 + y1) / 2;
  const midZ = (z0 + z1) / 2;

  return (
    <group>
      {Array.from({ length: STEPS }, (_, step) => {
        const z = z0 + run * (step + 0.5);
        const top = y0 + rise * (step + 1);
        return (
          <mesh key={step} position={[x + width / 2, top - 0.04, z]} castShadow receiveShadow>
            <boxGeometry args={[width, 0.08, tread]} />
            <meshLambertMaterial color={palette.tread} />
          </mesh>
        );
      })}
      {[0.1, width - 0.1].map((offset) => (
        <mesh key={offset} position={[x + offset, midY - 0.08, midZ]} rotation={[angle, 0, 0]}>
          <boxGeometry args={[0.08, 0.1, length]} />
          <meshLambertMaterial color={palette.stringer} />
        </mesh>
      ))}
      {[0.08, width - 0.08].map((offset) => (
        <mesh key={`rail-${offset}`} position={[x + offset, midY + 0.72, midZ]} rotation={[angle, 0, 0]}>
          <boxGeometry args={[0.05, 0.05, length]} />
          <meshLambertMaterial color={palette.rail} />
        </mesh>
      ))}
      <Post position={[x + 0.08, y0, z0]} />
      <Post position={[x + width - 0.08, y0, z0]} />
      <Post position={[x + 0.08, y1, z1]} />
      <Post position={[x + width - 0.08, y1, z1]} />
    </group>
  );
}

function Post({ position }: { position: [number, number, number] }) {
  return (
    <mesh position={[position[0], position[1] + 0.4, position[2]]} castShadow>
      <boxGeometry args={[0.06, 0.8, 0.06]} />
      <meshLambertMaterial color={palette.rail} />
    </mesh>
  );
}
