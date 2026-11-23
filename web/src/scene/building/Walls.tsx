import * as THREE from "three";
import { palette } from "../palette";
import type { WallSegment } from "../types";

const PLASTER = new THREE.MeshLambertMaterial({ color: palette.plaster });
const BRICK = new THREE.MeshLambertMaterial({ color: palette.brick, flatShading: true });
const TRIM = new THREE.MeshLambertMaterial({ color: palette.plasterDeep });
const RAIL = new THREE.MeshLambertMaterial({ color: palette.rail });

export function Walls({ segments }: { segments: WallSegment[] }) {
  return (
    <group name="walls">
      {segments.map((segment) => (
        <Wall key={segment.id} segment={segment} />
      ))}
    </group>
  );
}

function Wall({ segment }: { segment: WallSegment }) {
  const materials = materialsFor(segment.kind);
  return (
    <mesh
      name={segment.id}
      position={[segment.x, segment.h / 2, segment.z]}
      material={materials}
      castShadow
      receiveShadow
    >
      <boxGeometry args={[segment.w, segment.h, segment.d]} />
    </mesh>
  );
}

function materialsFor(kind: WallSegment["kind"]): THREE.Material[] {
  const plaster = PLASTER;
  if (kind === "rail") return [RAIL, RAIL, TRIM, TRIM, RAIL, RAIL];
  if (kind === "exterior-west") return [plaster, BRICK, TRIM, TRIM, plaster, plaster];
  if (kind === "exterior-north") return [plaster, plaster, TRIM, TRIM, BRICK, plaster];
  return [plaster, plaster, TRIM, TRIM, plaster, plaster];
}
