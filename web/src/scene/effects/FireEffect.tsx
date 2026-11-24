import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { Flames } from "./Flames";
import { Embers, Smoke } from "./RisingPoints";

export interface FireEffectProps {
  /** 0 hides the effect. 1 is a fully developed blaze. */
  intensity: number;
  position: [number, number, number];
}

/**
 * Reusable blaze: flames, smoke, embers, and a flickering light.
 * Everything scales from `intensity`, which the parent owns.
 */
export function FireEffect({ intensity, position }: FireEffectProps) {
  const clamped = THREE.MathUtils.clamp(intensity, 0, 1);
  if (clamped <= 0.01) return null;
  return (
    <group position={position} name="fire">
      <Scorch intensity={clamped} />
      <Flames intensity={clamped} />
      <Smoke intensity={clamped} />
      <Embers intensity={clamped} />
      <FireLight intensity={clamped} />
    </group>
  );
}

function Scorch({ intensity }: { intensity: number }) {
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
        <circleGeometry args={[1.15, 18]} />
        <meshLambertMaterial color="#3a241c" />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]} renderOrder={1}>
        <circleGeometry args={[0.55 + intensity * 0.45, 18]} />
        <meshBasicMaterial
          color="#ff4e16"
          transparent
          opacity={0.28 + intensity * 0.25}
          toneMapped={false}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

function FireLight({ intensity }: { intensity: number }) {
  const light = useRef<THREE.PointLight>(null);
  useFrame(({ clock }) => {
    const current = light.current;
    if (!current) return;
    const t = clock.elapsedTime;
    const flicker = 0.78 + Math.sin(t * 11) * 0.12 + Math.sin(t * 23) * 0.08 + Math.sin(t * 5.5) * 0.06;
    current.intensity = (2 + intensity * 13) * flicker;
  });
  return <pointLight ref={light} position={[0, 0.9, 0]} color="#ff6a2a" distance={7 + intensity * 10} decay={2} />;
}
