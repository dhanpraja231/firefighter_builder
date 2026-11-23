import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { flameFragment, flameVertex } from "./shaders";

const TONGUES = [
  { position: [0, 0.58, 0] as [number, number, number], scale: [0.36, 1.2, 0.36] as [number, number, number], phase: 0.2 },
  { position: [-0.18, 0.4, 0.06] as [number, number, number], scale: [0.24, 0.82, 0.24] as [number, number, number], phase: 1.4 },
  { position: [0.2, 0.46, -0.05] as [number, number, number], scale: [0.26, 0.94, 0.26] as [number, number, number], phase: 2.5 },
  { position: [0.04, 0.3, 0.16] as [number, number, number], scale: [0.18, 0.58, 0.18] as [number, number, number], phase: 3.6 },
];

export function Flames({ intensity }: { intensity: number }) {
  const spread = 0.55 + intensity * 0.6;
  const height = 0.45 + intensity * 0.85;
  return (
    <group scale={[spread, height, spread]}>
      {TONGUES.map((tongue) => (
        <Tongue key={tongue.phase} {...tongue} intensity={intensity} />
      ))}
    </group>
  );
}

function Tongue({
  position,
  scale,
  phase,
  intensity,
}: {
  position: [number, number, number];
  scale: [number, number, number];
  phase: number;
  intensity: number;
}) {
  const material = useRef<THREE.ShaderMaterial>(null);
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uIntensity: { value: 1 },
      uPhase: { value: phase },
    }),
    [phase],
  );

  useFrame(({ clock }) => {
    uniforms.uTime.value = clock.elapsedTime;
    uniforms.uIntensity.value = intensity;
  });

  return (
    <mesh position={position} scale={scale} renderOrder={2}>
      <coneGeometry args={[0.5, 1, 7, 1, true]} />
      <shaderMaterial
        ref={material}
        uniforms={uniforms}
        vertexShader={flameVertex}
        fragmentShader={flameFragment}
        transparent
        depthWrite={false}
        toneMapped={false}
        side={THREE.DoubleSide}
        blending={THREE.AdditiveBlending}
      />
    </mesh>
  );
}
