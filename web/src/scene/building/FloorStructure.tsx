import { useEffect, useMemo } from "react";
import * as THREE from "three";
import { FLOOR_ACCENTS, palette } from "../palette";
import { STAIR_CORE } from "../layout";
import { BUILDING_DEPTH, BUILDING_WIDTH, type FloorLayout, type RoomLayout } from "../types";
import { Furniture } from "./Furniture";
import { RoomLighting } from "./RoomLighting";

const SOLID_SLAB = createSlab(false);
const OPEN_SLAB = createSlab(true);

export function FloorStructure({ floor }: { floor: FloorLayout }) {
  const geometry = floor.id === 1 ? SOLID_SLAB : OPEN_SLAB;
  return (
    <group name={`structure-${floor.id}`}>
      <mesh geometry={geometry} receiveShadow castShadow>
        <meshLambertMaterial color={palette.slab} />
      </mesh>
      <Fascia />
      <CutEdge />
      {floor.rooms.map((room) => (
        <RoomFloor key={room.id} room={room} />
      ))}
      {floor.rooms.map((room) => (
        <Furniture key={`furn-${room.id}`} room={room} />
      ))}
      {floor.rooms.map((room) => (
        <RoomLighting key={`light-${room.id}`} room={room} />
      ))}
      <FloorBadge floorId={floor.id} />
      {floor.id === 5 && <Parapet />}
    </group>
  );
}

function RoomFloor({ room }: { room: RoomLayout }) {
  const accent = FLOOR_ACCENTS[room.floorId];
  const color = room.kind === "kitchen" ? accent.tile : room.kind === "hall" || room.kind === "landing" ? "#cfc3b2" : accent.wood;
  const inset = 0.1;
  return (
    <mesh
      name={`room-${room.id}`}
      userData={{ floorId: room.floorId, roomId: room.id, kind: room.kind }}
      position={[room.x + room.w / 2, 0.014, room.z + room.d / 2]}
      receiveShadow
    >
      <boxGeometry args={[Math.max(room.w - inset, 0.2), 0.028, Math.max(room.d - inset, 0.2)]} />
      <meshLambertMaterial color={color} />
    </mesh>
  );
}

function Fascia() {
  const y = -0.11;
  const h = 0.26;
  const t = 0.08;
  return (
    <group>
      <mesh position={[BUILDING_WIDTH / 2, y, -t / 2]} castShadow>
        <boxGeometry args={[BUILDING_WIDTH + t, h, t]} />
        <meshLambertMaterial color={palette.fascia} />
      </mesh>
      <mesh position={[BUILDING_WIDTH + t / 2, y, BUILDING_DEPTH / 2]} castShadow>
        <boxGeometry args={[t, h, BUILDING_DEPTH + t]} />
        <meshLambertMaterial color={palette.fascia} />
      </mesh>
      <mesh position={[BUILDING_WIDTH / 2, y, BUILDING_DEPTH + t / 2]}>
        <boxGeometry args={[BUILDING_WIDTH + t, h, t]} />
        <meshLambertMaterial color={palette.fascia} />
      </mesh>
      <mesh position={[-t / 2, y, BUILDING_DEPTH / 2]}>
        <boxGeometry args={[t, h, BUILDING_DEPTH + t]} />
        <meshLambertMaterial color={palette.fascia} />
      </mesh>
    </group>
  );
}

function CutEdge() {
  return (
    <group>
      <mesh position={[BUILDING_WIDTH / 2, 0.01, 0.02]}>
        <boxGeometry args={[BUILDING_WIDTH, 0.025, 0.045]} />
        <meshBasicMaterial color="#f7f1e8" toneMapped={false} />
      </mesh>
      <mesh position={[BUILDING_WIDTH - 0.02, 0.01, BUILDING_DEPTH / 2]}>
        <boxGeometry args={[0.045, 0.025, BUILDING_DEPTH]} />
        <meshBasicMaterial color="#f7f1e8" toneMapped={false} />
      </mesh>
    </group>
  );
}

function Parapet() {
  return (
    <group>
      <mesh position={[BUILDING_WIDTH / 2, 3.0, BUILDING_DEPTH - 0.12]} castShadow>
        <boxGeometry args={[BUILDING_WIDTH + 0.2, 0.56, 0.22]} />
        <meshLambertMaterial color={palette.brick} flatShading />
      </mesh>
      <mesh position={[0.1, 3.0, BUILDING_DEPTH / 2]} castShadow>
        <boxGeometry args={[0.22, 0.56, BUILDING_DEPTH]} />
        <meshLambertMaterial color={palette.brick} flatShading />
      </mesh>
    </group>
  );
}

function FloorBadge({ floorId }: { floorId: number }) {
  const texture = useMemo(() => createBadge(String(floorId)), [floorId]);
  useEffect(() => () => texture.dispose(), [texture]);
  return (
    <mesh position={[BUILDING_WIDTH - 0.7, 0.62, -0.02]} rotation={[0, Math.PI, 0]}>
      <planeGeometry args={[0.62, 0.62]} />
      <meshBasicMaterial map={texture} transparent toneMapped={false} />
    </mesh>
  );
}

function createBadge(label: string): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Could not draw a floor badge.");
  ctx.clearRect(0, 0, 128, 128);
  ctx.fillStyle = "#2c2826";
  ctx.beginPath();
  ctx.arc(64, 64, 58, 0, Math.PI * 2);
  ctx.fill();
  ctx.lineWidth = 6;
  ctx.strokeStyle = "#f3ecdf";
  ctx.stroke();
  ctx.fillStyle = "#f7f1e8";
  ctx.font = "700 72px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, 64, 68);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function createSlab(withHole: boolean): THREE.BufferGeometry {
  if (!withHole) {
    const geometry = new THREE.BoxGeometry(BUILDING_WIDTH, 0.22, BUILDING_DEPTH);
    geometry.translate(BUILDING_WIDTH / 2, -0.11, BUILDING_DEPTH / 2);
    return geometry;
  }
  const shape = new THREE.Shape();
  shape.moveTo(0, 0);
  shape.lineTo(BUILDING_WIDTH, 0);
  shape.lineTo(BUILDING_WIDTH, BUILDING_DEPTH);
  shape.lineTo(0, BUILDING_DEPTH);
  shape.closePath();
  const hole = new THREE.Path();
  hole.moveTo(STAIR_CORE.x, STAIR_CORE.z);
  hole.lineTo(STAIR_CORE.x + STAIR_CORE.w, STAIR_CORE.z);
  hole.lineTo(STAIR_CORE.x + STAIR_CORE.w, STAIR_CORE.z + STAIR_CORE.d);
  hole.lineTo(STAIR_CORE.x, STAIR_CORE.z + STAIR_CORE.d);
  hole.closePath();
  shape.holes.push(hole);
  const geometry = new THREE.ExtrudeGeometry(shape, { depth: 0.22, bevelEnabled: false });
  geometry.rotateX(Math.PI / 2);
  geometry.computeVertexNormals();
  return geometry;
}
