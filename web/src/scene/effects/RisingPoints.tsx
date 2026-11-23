import { useEffect, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { radialTexture } from "./particleTexture";
import { pointFragment, pointVertex } from "./shaders";

interface Particle {
  life: number;
  maxLife: number;
  speed: number;
  radius: number;
  phase: number;
}

export function Smoke({ intensity }: { intensity: number }) {
  return (
    <RisingPoints
      intensity={intensity}
      count={80}
      size={26}
      rise={5.4}
      color="#9aa3b0"
      blending={THREE.NormalBlending}
      opacity={0.28}
      drift={0.7}
    />
  );
}

export function Embers({ intensity }: { intensity: number }) {
  return (
    <RisingPoints
      intensity={intensity}
      count={42}
      size={7}
      rise={3.4}
      color="#ffb15a"
      blending={THREE.AdditiveBlending}
      opacity={0.85}
      drift={0.35}
    />
  );
}

function RisingPoints({
  intensity,
  count,
  size,
  rise,
  color,
  blending,
  opacity,
  drift,
}: {
  intensity: number;
  count: number;
  size: number;
  rise: number;
  color: string;
  blending: THREE.Blending;
  opacity: number;
  drift: number;
}) {
  const positions = useMemo(() => new Float32Array(count * 3), [count]);
  const alphas = useMemo(() => new Float32Array(count), [count]);
  const positionAttr = useMemo(() => new THREE.BufferAttribute(positions, 3), [positions]);
  const alphaAttr = useMemo(() => new THREE.BufferAttribute(alphas, 1), [alphas]);
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", positionAttr);
    geo.setAttribute("aAlpha", alphaAttr);
    return geo;
  }, [positionAttr, alphaAttr]);

  const seeds = useMemo<Particle[]>(
    () =>
      Array.from({ length: count }, () => ({
        life: Math.random(),
        maxLife: 2.4 + Math.random() * 2.4,
        speed: 0.45 + Math.random() * 0.7,
        radius: Math.random() * 0.28,
        phase: Math.random() * Math.PI * 2,
      })),
    [count],
  );

  const map = useMemo(() => radialTexture(), []);
  const uniforms = useMemo(
    () => ({
      uMap: { value: map },
      uSize: { value: size },
      uColor: { value: new THREE.Color(color) },
    }),
    [map, size, color],
  );

  useEffect(() => {
    return () => {
      geometry.dispose();
      map.dispose();
    };
  }, [geometry, map]);

  useFrame((_, delta) => {
    const step = Math.min(delta, 0.05);
    for (let i = 0; i < count; i += 1) {
      const seed = seeds[i];
      seed.life += step * (0.55 + intensity * 0.8);
      if (seed.life > seed.maxLife) {
        seed.life = 0;
        seed.phase = Math.random() * Math.PI * 2;
        seed.radius = Math.random() * 0.28;
      }
      const t = seed.life / seed.maxLife;
      const swirl = Math.sin(seed.phase + seed.life * 1.6) * drift * t;
      positions[i * 3] = Math.cos(seed.phase) * seed.radius + swirl;
      positions[i * 3 + 1] = t * rise * seed.speed;
      positions[i * 3 + 2] = Math.sin(seed.phase) * seed.radius + Math.cos(seed.phase * 1.3 + seed.life) * drift * t;
      alphas[i] = Math.sin(Math.min(t, 1) * Math.PI) * opacity * intensity;
    }
    positionAttr.needsUpdate = true;
    alphaAttr.needsUpdate = true;
  });

  return (
    <points geometry={geometry} frustumCulled={false} renderOrder={3}>
      <shaderMaterial
        uniforms={uniforms}
        vertexShader={pointVertex}
        fragmentShader={pointFragment}
        transparent
        depthWrite={false}
        blending={blending}
        toneMapped={false}
      />
    </points>
  );
}
