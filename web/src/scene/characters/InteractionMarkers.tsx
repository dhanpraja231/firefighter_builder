import { Html } from "@react-three/drei";
import type { CharacterRole, InteractionPoint } from "../types";

const ROLE_COLORS: Record<CharacterRole, string> = {
  coordinator: "#ffd166",
  rescuer: "#4cc9f0",
  hose_operator: "#4895ef",
  ladder_operator: "#f8961e",
  elder: "#9d4edd",
  adult: "#43aa8b",
  child: "#f94144",
};

/**
 * Debug-only gizmos: a colored disc and label at every [[InteractionPoint]].
 * Toggle off once teammates' real characters are mounted at these spots.
 */
export function InteractionMarkers({ points }: { points: InteractionPoint[] }) {
  return (
    <group name="interaction-markers">
      {points.map((point) => (
        <group key={point.id} position={point.position} rotation={[0, point.heading, 0]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
            <ringGeometry args={[0.32, 0.42, 24]} />
            <meshBasicMaterial color={ROLE_COLORS[point.role]} toneMapped={false} />
          </mesh>
          <mesh position={[0, 0.9, 0]}>
            <coneGeometry args={[0.1, 0.3, 8]} />
            <meshBasicMaterial color={ROLE_COLORS[point.role]} toneMapped={false} />
          </mesh>
          <Html position={[0, 1.3, 0]} center distanceFactor={9} occlude>
            <div
              style={{
                padding: "2px 6px",
                borderRadius: 4,
                background: "rgba(10,12,20,0.75)",
                color: ROLE_COLORS[point.role],
                fontSize: 11,
                fontFamily: "monospace",
                whiteSpace: "nowrap",
              }}
            >
              {point.role}
            </div>
          </Html>
        </group>
      ))}
    </group>
  );
}
