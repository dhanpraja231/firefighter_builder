import { useEffect, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { palette } from "../palette";
import { radialTexture } from "./particleTexture";
import { pointFragment, pointVertex } from "./shaders";

const COUNT = 90;

interface Droplet {
  t: number;
  speed: number;
  jitterX: number;
  jitterY: number;
}

/**
 * Hose nozzle at `origin`, a ground-hugging supply line back to `supply`,
 * and (when `active`) a particle water arc toward `target`. All geometry;
 * `active`/`target` come from `WorldState.hose`.
 */
export function WaterStream({
  origin,
  supply,
  target,
  active,
}: {
  origin: [number, number, number];
  supply: [number, number, number];
  target: [number, number, number] | null;
  active: boolean;
}) {
  return (
    <group name="hose">
      <Nozzle origin={origin} target={target} />
      <SupplyLine origin={origin} supply={supply} />
      {active && target && <Jet origin={origin} target={target} />}
    </group>
  );
}

function Nozzle({ origin, target }: { origin: [number, number, number]; target: [number, number, number] | null }) {
  const yaw = target ? Math.atan2(target[0] - origin[0], target[2] - origin[2]) : 0;
  return (
    <group position={origin} rotation={[0, yaw, 0]}>
      <mesh position={[0, 0.1, 0]} castShadow>
        <cylinderGeometry args={[0.055, 0.04, 0.42, 10]} />
        <meshLambertMaterial color="#2c2c2c" />
      </mesh>
    </group>
  );
}

function SupplyLine({ origin, supply }: { origin: [number, number, number]; supply: [number, number, number] }) {
  const geometry = useMemo(() => {
    const mid: [number, number, number] = [
      (origin[0] + supply[0]) / 2 + 0.6,
      0.05,
      (origin[2] + supply[2]) / 2,
    ];
    const curve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(...supply),
      new THREE.Vector3(mid[0], mid[1], mid[2]),
      new THREE.Vector3(origin[0], 0.08, origin[2]),
    ]);
    return new THREE.TubeGeometry(curve, 24, 0.055, 6, false);
  }, [origin, supply]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh geometry={geometry} castShadow>
      <meshLambertMaterial color="#3a2f28" />
    </mesh>
  );
}

function Jet({ origin, target }: { origin: [number, number, number]; target: [number, number, number] }) {
  const positions = useMemo(() => new Float32Array(COUNT * 3), []);
  const alphas = useMemo(() => new Float32Array(COUNT), []);
  const positionAttr = useMemo(() => new THREE.BufferAttribute(positions, 3), [positions]);
  const alphaAttr = useMemo(() => new THREE.BufferAttribute(alphas, 1), [alphas]);
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", positionAttr);
    geo.setAttribute("aAlpha", alphaAttr);
    return geo;
  }, [positionAttr, alphaAttr]);

  const droplets = useMemo<Droplet[]>(
    () =>
      Array.from({ length: COUNT }, (_, i) => ({
        t: i / COUNT,
        speed: 1.1 + Math.random() * 0.5,
        jitterX: (Math.random() - 0.5) * 0.18,
        jitterY: (Math.random() - 0.5) * 0.1,
      })),
    [],
  );

  const map = useMemo(() => radialTexture(), []);
  const uniforms = useMemo(
    () => ({
      uMap: { value: map },
      uSize: { value: 9 },
      uColor: { value: new THREE.Color(palette.glass).lerp(new THREE.Color("#dceaf5"), 0.7) },
    }),
    [map],
  );
  useEffect(() => () => {
    geometry.dispose();
    map.dispose();
  }, [geometry, map]);

  const dx = target[0] - origin[0];
  const dy = target[1] - origin[1];
  const dz = target[2] - origin[2];
  const horizontal = Math.hypot(dx, dz);
  const peak = Math.max(0.5, horizontal * 0.22);

  useFrame((_, delta) => {
    const step = Math.min(delta, 0.05);
    for (let i = 0; i < COUNT; i += 1) {
      const d = droplets[i];
      d.t += step * d.speed * 0.6;
      if (d.t > 1) d.t -= 1;
      const t = d.t;
      const arc = 4 * peak * t * (1 - t);
      positions[i * 3] = origin[0] + dx * t + d.jitterX * t;
      positions[i * 3 + 1] = origin[1] + dy * t + arc;
      positions[i * 3 + 2] = origin[2] + dz * t + d.jitterY * t;
      alphas[i] = Math.sin(Math.min(t * 1.4, 1) * Math.PI) * 0.8;
    }
    positionAttr.needsUpdate = true;
    alphaAttr.needsUpdate = true;
  });

  return (
    <points geometry={geometry} frustumCulled={false}>
      <shaderMaterial
        uniforms={uniforms}
        vertexShader={pointVertex}
        fragmentShader={pointFragment}
        transparent
        depthWrite={false}
        blending={THREE.NormalBlending}
        toneMapped={false}
      />
    </points>
  );
}
