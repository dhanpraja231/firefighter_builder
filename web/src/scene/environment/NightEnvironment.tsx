import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Stars } from "@react-three/drei";
import * as THREE from "three";
import { palette } from "../palette";
import { BUILDING_DEPTH, BUILDING_WIDTH, type ExteriorLayout } from "../types";

const GROUND_SIZE = 90;

export function NightEnvironment({ exterior }: { exterior: ExteriorLayout }) {
  const westEdge = -exterior.setback;
  const sidewalkInner = westEdge;
  const sidewalkOuter = westEdge - exterior.sidewalkWidth;
  const streetOuter = sidewalkOuter - exterior.streetWidth;

  return (
    <group name="environment">
      <Stars radius={70} depth={40} count={2600} factor={3.2} fade speed={0.3} />
      <Moon />
      <hemisphereLight args={[palette.sky, "#1a2230", 0.85]} />
      <directionalLight
        position={[-14, 18, 10]}
        intensity={0.4}
        color="#aebbdc"
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-camera-near={1}
        shadow-camera-far={60}
        shadow-camera-left={-24}
        shadow-camera-right={24}
        shadow-camera-top={24}
        shadow-camera-bottom={-24}
      />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[BUILDING_WIDTH / 2 - 30, -0.03, BUILDING_DEPTH / 2]} receiveShadow>
        <planeGeometry args={[GROUND_SIZE, GROUND_SIZE]} />
        <meshLambertMaterial color="#223821" />
      </mesh>
      {/* Narrow lit lawn strip right along the building's open (south/east) sides, so the
          cutaway doesn't just drop into the dark GROUND_SIZE plane. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[BUILDING_WIDTH / 2, -0.02, -1.6]} receiveShadow>
        <planeGeometry args={[BUILDING_WIDTH + 6, 3.2]} />
        <meshLambertMaterial color="#2c4a29" />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[BUILDING_WIDTH + 2, -0.02, BUILDING_DEPTH / 2]} receiveShadow>
        <planeGeometry args={[4, BUILDING_DEPTH + 6]} />
        <meshLambertMaterial color="#2c4a29" />
      </mesh>
      <Shrubs />

      <Strip x0={sidewalkOuter} x1={sidewalkInner} color={palette.sidewalk} y={0.01} />
      <Strip x0={sidewalkOuter - 0.08} x1={sidewalkOuter} color={palette.curb} y={0.08} />
      <Strip x0={streetOuter} x1={sidewalkOuter} color={palette.street} y={0} />
      <LaneMarkings x={(streetOuter + sidewalkOuter) / 2} />

      <StreetLight z={1.2} x={sidewalkOuter - 0.4} />
      <StreetLight z={BUILDING_DEPTH / 2} x={sidewalkOuter - 0.4} />
      <StreetLight z={BUILDING_DEPTH - 1.2} x={sidewalkOuter - 0.4} />
    </group>
  );
}

const SHRUB_SPOTS: Array<[number, number]> = [
  [1.2, -0.8],
  [BUILDING_WIDTH - 1.2, -0.8],
  [BUILDING_WIDTH + 1.4, 2.5],
  [BUILDING_WIDTH + 1.4, BUILDING_DEPTH - 2.5],
];

function Shrubs() {
  return (
    <group name="shrubs">
      {SHRUB_SPOTS.map(([x, z], i) => (
        <group key={i} position={[x, 0, z]}>
          <mesh position={[0, 0.22, 0]} castShadow>
            <sphereGeometry args={[0.3, 8, 8]} />
            <meshLambertMaterial color="#35542f" flatShading />
          </mesh>
          <mesh position={[0.18, 0.15, 0.1]} castShadow>
            <sphereGeometry args={[0.2, 8, 8]} />
            <meshLambertMaterial color="#3e5f36" flatShading />
          </mesh>
        </group>
      ))}
    </group>
  );
}

function Moon() {
  return (
    <group position={[-24, 26, -18]}>
      <mesh>
        <sphereGeometry args={[1.6, 24, 24]} />
        <meshBasicMaterial color={palette.moon} toneMapped={false} />
      </mesh>
      <pointLight color={palette.moon} intensity={0.4} distance={0} decay={0} />
    </group>
  );
}

function Strip({ x0, x1, color, y }: { x0: number; x1: number; color: string; y: number }) {
  const width = Math.abs(x1 - x0);
  const centerX = (x0 + x1) / 2;
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[centerX, y, BUILDING_DEPTH / 2]} receiveShadow>
      <planeGeometry args={[width, BUILDING_DEPTH + 10]} />
      <meshLambertMaterial color={color} />
    </mesh>
  );
}

function LaneMarkings({ x }: { x: number }) {
  const dashes = Array.from({ length: 6 }, (_, i) => -2 + i * 2.6);
  return (
    <group>
      {dashes.map((z) => (
        <mesh key={z} rotation={[-Math.PI / 2, 0, 0]} position={[x, 0.012, z + BUILDING_DEPTH / 2]}>
          <planeGeometry args={[0.12, 1.1]} />
          <meshBasicMaterial color={palette.lane} toneMapped={false} />
        </mesh>
      ))}
    </group>
  );
}

function StreetLight({ x, z }: { x: number; z: number }) {
  const light = useRef<THREE.PointLight>(null);
  useFrame(({ clock }) => {
    if (!light.current) return;
    light.current.intensity = 1.1 + Math.sin(clock.elapsedTime * 1.3 + x) * 0.05;
  });
  return (
    <group position={[x, 0, z]}>
      <mesh position={[0, 2.1, 0]} castShadow>
        <cylinderGeometry args={[0.045, 0.06, 4.2, 8]} />
        <meshLambertMaterial color={palette.metal} />
      </mesh>
      <mesh position={[0.35, 4.05, 0]} rotation={[0, 0, Math.PI / 2.6]}>
        <cylinderGeometry args={[0.035, 0.035, 0.8, 6]} />
        <meshLambertMaterial color={palette.metal} />
      </mesh>
      <mesh position={[0.62, 3.78, 0]}>
        <sphereGeometry args={[0.13, 10, 10]} />
        <meshBasicMaterial color={palette.bulb} toneMapped={false} />
      </mesh>
      <pointLight ref={light} position={[0.62, 3.78, 0]} color={palette.bulb} intensity={1.1} distance={6.5} decay={2} />
    </group>
  );
}
