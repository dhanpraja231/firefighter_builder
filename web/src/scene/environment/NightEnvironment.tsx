import { useMemo, useRef } from "react";
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
      <NightSky />
      <Stars radius={120} depth={50} count={3200} factor={3.4} fade speed={0.25} />
      <Moon />
      <CitySilhouette />
      <hemisphereLight args={["#6a7fa8", "#1a2a1c", 1.05]} />
      <directionalLight
        position={[-14, 18, 10]}
        intensity={0.55}
        color="#c4d0ea"
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-camera-near={1}
        shadow-camera-far={60}
        shadow-camera-left={-24}
        shadow-camera-right={24}
        shadow-camera-top={24}
        shadow-camera-bottom={-24}
      />
      {/* Soft warm fill from the burning building / city glow */}
      <pointLight position={[8, 4, -8]} color="#ff8a4a" intensity={0.55} distance={55} decay={2} />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[BUILDING_WIDTH / 2 - 30, -0.03, BUILDING_DEPTH / 2]} receiveShadow>
        <planeGeometry args={[GROUND_SIZE, GROUND_SIZE]} />
        <meshStandardMaterial color={palette.grass} roughness={0.95} metalness={0.02} />
      </mesh>
      {/* Narrow lit lawn strip right along the building's open (south/east) sides, so the
          cutaway doesn't just drop into the dark GROUND_SIZE plane. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[BUILDING_WIDTH / 2, -0.02, -1.6]} receiveShadow>
        <planeGeometry args={[BUILDING_WIDTH + 6, 3.2]} />
        <meshStandardMaterial color={palette.grassLit} roughness={0.92} metalness={0.02} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[BUILDING_WIDTH + 2, -0.02, BUILDING_DEPTH / 2]} receiveShadow>
        <planeGeometry args={[4, BUILDING_DEPTH + 6]} />
        <meshStandardMaterial color={palette.grassLit} roughness={0.92} metalness={0.02} />
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

/** Vertical night gradient as an inward-facing sky dome (avoids a flat black clearColor). */
function NightSky() {
  const texture = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 4;
    canvas.height = 512;
    const ctx = canvas.getContext("2d")!;
    const gradient = ctx.createLinearGradient(0, 0, 0, 512);
    gradient.addColorStop(0, "#070d1c");
    gradient.addColorStop(0.35, "#121c34");
    gradient.addColorStop(0.62, "#1e2a44");
    gradient.addColorStop(0.82, "#2c3548");
    gradient.addColorStop(0.93, "#3f3a36");
    gradient.addColorStop(1, "#5c4630");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 4, 512);
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.magFilter = THREE.LinearFilter;
    tex.minFilter = THREE.LinearFilter;
    return tex;
  }, []);

  return (
    <mesh>
      <sphereGeometry args={[160, 48, 24]} />
      <meshBasicMaterial map={texture} side={THREE.BackSide} fog={false} depthWrite={false} />
    </mesh>
  );
}

/** Distant building blocks so the horizon isn't empty void. */
function CitySilhouette() {
  const blocks: Array<[number, number, number, number, number]> = [
    [-48, 5.5, -42, 6, 11],
    [-38, 3.8, -46, 4.5, 7.5],
    [-28, 7.2, -50, 5, 14],
    [-16, 4.2, -48, 7, 8],
    [6, 6.5, -52, 8, 13],
    [22, 3.5, -46, 5, 7],
    [36, 8.0, -50, 6, 16],
    [48, 4.5, -44, 7, 9],
    [-52, 4.0, 18, 5, 8],
    [-46, 6.5, 32, 4, 13],
    [42, 5.5, 28, 6, 11],
  ];
  return (
    <group name="city-silhouette">
      {blocks.map(([x, h, z, w, d], i) => (
        <mesh key={i} position={[x, h / 2, z]} castShadow={false}>
          <boxGeometry args={[w, h, d]} />
          <meshLambertMaterial color="#0c121c" />
        </mesh>
      ))}
      {/* Tiny lit windows on a couple of blocks */}
      {[[-28, 4, -49.2], [36, 5, -49.2], [6, 3.5, -51.2]].map(([x, y, z], i) => (
        <mesh key={`win-${i}`} position={[x, y, z]}>
          <planeGeometry args={[0.35, 0.45]} />
          <meshBasicMaterial color="#ffc078" toneMapped={false} />
        </mesh>
      ))}
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
        <sphereGeometry args={[1.8, 24, 24]} />
        <meshBasicMaterial color={palette.moon} toneMapped={false} />
      </mesh>
      <pointLight color={palette.moon} intensity={0.55} distance={0} decay={0} />
    </group>
  );
}

function Strip({ x0, x1, color, y }: { x0: number; x1: number; color: string; y: number }) {
  const width = Math.abs(x1 - x0);
  const centerX = (x0 + x1) / 2;
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[centerX, y, BUILDING_DEPTH / 2]} receiveShadow>
      <planeGeometry args={[width, BUILDING_DEPTH + 10]} />
      <meshStandardMaterial color={color} roughness={0.88} metalness={0.05} />
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
    light.current.intensity = 1.35 + Math.sin(clock.elapsedTime * 1.3 + x) * 0.06;
  });
  return (
    <group position={[x, 0, z]}>
      <mesh position={[0, 2.1, 0]} castShadow>
        <cylinderGeometry args={[0.045, 0.06, 4.2, 8]} />
        <meshStandardMaterial color={palette.metal} roughness={0.45} metalness={0.65} />
      </mesh>
      <mesh position={[0.35, 4.05, 0]} rotation={[0, 0, Math.PI / 2.6]}>
        <cylinderGeometry args={[0.035, 0.035, 0.8, 6]} />
        <meshStandardMaterial color={palette.metal} roughness={0.45} metalness={0.65} />
      </mesh>
      <mesh position={[0.62, 3.78, 0]}>
        <sphereGeometry args={[0.13, 10, 10]} />
        <meshBasicMaterial color={palette.bulb} toneMapped={false} />
      </mesh>
      <pointLight ref={light} position={[0.62, 3.78, 0]} color={palette.bulb} intensity={1.35} distance={14} decay={2} />
    </group>
  );
}
