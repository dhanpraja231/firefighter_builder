import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

/**
 * Not a character: a capsule that walks a list of waypoints at a fixed
 * speed, used to verify the nav graph in [[layout.ts]] actually connects
 * where it claims to (e.g. fire engine to floor 3). Teammates' real
 * characters replace this entirely; nothing here is part of the delivered
 * scene.
 */
export function PlaceholderWalker({
  waypoints,
  speed = 1.4,
  color = "#ffd166",
  onArrive,
}: {
  waypoints: Array<[number, number, number]>;
  speed?: number;
  color?: string;
  onArrive?: () => void;
}) {
  const group = useRef<THREE.Group>(null);
  const progress = useRef(0);
  const arrived = useRef(false);
  const points = useMemo(() => waypoints.map((p) => new THREE.Vector3(...p)), [waypoints]);
  const segmentLengths = useMemo(() => {
    const lengths: number[] = [];
    for (let i = 1; i < points.length; i += 1) lengths.push(points[i - 1].distanceTo(points[i]));
    return lengths;
  }, [points]);
  const totalLength = useMemo(() => segmentLengths.reduce((sum, l) => sum + l, 0), [segmentLengths]);

  useFrame((_, delta) => {
    const node = group.current;
    if (!node || points.length < 2 || totalLength <= 0) return;
    progress.current = Math.min(totalLength, progress.current + speed * delta);

    let travelled = progress.current;
    let segment = 0;
    while (segment < segmentLengths.length - 1 && travelled > segmentLengths[segment]) {
      travelled -= segmentLengths[segment];
      segment += 1;
    }
    const start = points[segment];
    const end = points[segment + 1] ?? points[segment];
    const t = segmentLengths[segment] > 0 ? travelled / segmentLengths[segment] : 0;
    node.position.lerpVectors(start, end, t);

    const direction = end.clone().sub(start);
    if (direction.lengthSq() > 1e-6) {
      const yaw = Math.atan2(direction.x, direction.z);
      node.rotation.y = yaw;
    }

    if (!arrived.current && progress.current >= totalLength - 0.001) {
      arrived.current = true;
      onArrive?.();
    }
  });

  return (
    <group ref={group} name="placeholder-walker" position={points[0] ?? [0, 0, 0]}>
      <mesh position={[0, 0.78, 0]} castShadow>
        <capsuleGeometry args={[0.22, 0.9, 4, 8]} />
        <meshLambertMaterial color={color} />
      </mesh>
      <mesh position={[0, 1.42, 0.14]}>
        <sphereGeometry args={[0.1, 10, 10]} />
        <meshLambertMaterial color={color} />
      </mesh>
      <pointLight position={[0, 1.6, 0]} intensity={0.6} distance={2} color={color} />
    </group>
  );
}
