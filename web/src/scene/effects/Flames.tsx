import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { flameFragment, flameVertex } from "./shaders";

const TONGUES = [
  { position: [0, 0.62, 0] as [number, number, number], scale: [0.42, 1.35, 0.42] as [number, number, number], phase: 0.2 },
  { position: [-0.22, 0.44, 0.08] as [number, number, number], scale: [0.28, 0.95, 0.28] as [number, number, number], phase: 1.4 },
  { position: [0.24, 0.5, -0.06] as [number, number, number], scale: [0.3, 1.05, 0.3] as [number, number, number], phase: 2.5 },
  { position: [0.06, 0.34, 0.2] as [number, number, number], scale: [0.2, 0.68, 0.2] as [number, number, number], phase: 3.6 },
  { position: [-0.12, 0.28, -0.18] as [number, number, number], scale: [0.22, 0.72, 0.22] as [number, number, number], phase: 4.8 },
  { position: [0.32, 0.36, 0.12] as [number, number, number], scale: [0.16, 0.55, 0.16] as [number, number, number], phase: 5.7 },
  { position: [-0.3, 0.38, 0.02] as [number, number, number], scale: [0.18, 0.62, 0.18] as [number, number, number], phase: 6.9 },
];

export function Flames({ intensity }: { intensity: number }) {
  const spread = 0.7 + intensity * 0.85;
  const height = 0.55 + intensity * 1.1;
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
      <coneGeometry args={[0.5, 1, 8, 1, true]} />
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
