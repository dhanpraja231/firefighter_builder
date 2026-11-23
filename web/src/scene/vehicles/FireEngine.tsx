import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { palette } from "../palette";
import type { EngineLayout } from "../types";

const WHEEL_RADIUS = 0.42;
const CHASSIS_Y = WHEEL_RADIUS;
const BODY_HEIGHT = 1.7;
const CAB_HEIGHT = 1.55;
const CAB_LENGTH = 1.9;

/** Roof-mounted turntable position, in world space, where the ladder hinges. */
export function ladderTurntablePosition(engine: EngineLayout): [number, number, number] {
  const [x, y, z] = engine.position;
  return [x, y + CHASSIS_Y + BODY_HEIGHT, z + engine.length * 0.08];
}

export function FireEngine({
  engine,
  lightsOn,
  zOffset = 0,
}: {
  engine: EngineLayout;
  lightsOn: boolean;
  /** Added to the parked z position -- nonzero while the engine is still driving in. */
  zOffset?: number;
}) {
  const [x, y, z] = engine.position;
  const bodyLength = engine.length - CAB_LENGTH - 0.1;

  return (
    <group name="fire-engine" position={[x, y, z + zOffset]} rotation={[0, engine.rotation, 0]}>
      <Chassis length={engine.length} width={engine.width} />
      <mesh position={[0, CHASSIS_Y + BODY_HEIGHT / 2, -(engine.length - bodyLength) / 2 + 0.05]} castShadow>
        <boxGeometry args={[engine.width, BODY_HEIGHT, bodyLength]} />
        <meshLambertMaterial color={palette.engine} />
      </mesh>
      <mesh position={[0, CHASSIS_Y + BODY_HEIGHT * 0.78, -(engine.length - bodyLength) / 2 + 0.05]}>
        <boxGeometry args={[engine.width + 0.04, 0.16, bodyLength]} />
        <meshLambertMaterial color={palette.engineDark} />
      </mesh>
      <HoseBed width={engine.width} z={-(engine.length - bodyLength) / 2 + 0.05} />

      <Cab length={CAB_LENGTH} width={engine.width} z={engine.length / 2 - CAB_LENGTH / 2} />

      <Wheels length={engine.length} width={engine.width} />
      <LightBar width={engine.width} z={engine.length / 2 - CAB_LENGTH * 0.2} on={lightsOn} />
    </group>
  );
}

function Chassis({ length, width }: { length: number; width: number }) {
  return (
    <mesh position={[0, CHASSIS_Y * 0.5, 0]} receiveShadow>
      <boxGeometry args={[width - 0.1, CHASSIS_Y, length - 0.4]} />
      <meshLambertMaterial color="#1c1c1c" />
    </mesh>
  );
}

function Cab({ length, width, z }: { length: number; width: number; z: number }) {
  return (
    <group position={[0, 0, z]}>
      <mesh position={[0, CHASSIS_Y + CAB_HEIGHT / 2, 0]} castShadow>
        <boxGeometry args={[width, CAB_HEIGHT, length]} />
        <meshLambertMaterial color={palette.cab} />
      </mesh>
      <mesh position={[0, CHASSIS_Y + CAB_HEIGHT * 0.78, length / 2 - 0.08]}>
        <boxGeometry args={[width - 0.14, CAB_HEIGHT * 0.45, 0.06]} />
        <meshLambertMaterial color={palette.glass} />
      </mesh>
      {[-1, 1].map((side) => (
        <mesh key={side} position={[(side * width) / 2 + side * 0.02, CHASSIS_Y + 0.42, length / 2 + 0.02]}>
          <circleGeometry args={[0.16, 12]} />
          <meshBasicMaterial color={palette.bulb} toneMapped={false} />
        </mesh>
      ))}
    </group>
  );
}

function HoseBed({ width, z }: { width: number; z: number }) {
  return (
    <mesh position={[0, CHASSIS_Y + BODY_HEIGHT + 0.08, z]}>
      <boxGeometry args={[width - 0.3, 0.16, 1.6]} />
      <meshLambertMaterial color={palette.engineDark} />
    </mesh>
  );
}

function Wheels({ length, width }: { length: number; width: number }) {
  const axles = [-(length / 2) + 0.9, 0, length / 2 - 0.9];
  return (
    <group>
      {axles.map((z) =>
        [-1, 1].map((side) => (
          <mesh
            key={`${z}-${side}`}
            position={[(side * width) / 2, WHEEL_RADIUS, z]}
            rotation={[0, 0, Math.PI / 2]}
            castShadow
          >
            <cylinderGeometry args={[WHEEL_RADIUS, WHEEL_RADIUS, 0.32, 16]} />
            <meshLambertMaterial color="#141414" />
          </mesh>
        )),
      )}
    </group>
  );
}

function LightBar({ width, z, on }: { width: number; z: number; on: boolean }) {
  const red = useRef<THREE.Group>(null);
  const white = useRef<THREE.Group>(null);
  const redLight = useRef<THREE.PointLight>(null);
  const whiteLight = useRef<THREE.PointLight>(null);

  useFrame(({ clock }) => {
    const phase = Math.floor(clock.elapsedTime * 4) % 2 === 0;
    const redOn = on && phase;
    const whiteOn = on && !phase;
    if (red.current) red.current.visible = redOn;
    if (white.current) white.current.visible = whiteOn;
    if (redLight.current) redLight.current.intensity = redOn ? 3.2 : 0;
    if (whiteLight.current) whiteLight.current.intensity = whiteOn ? 2.4 : 0;
  });

  const y = CHASSIS_Y + BODY_HEIGHT + 0.22;
  return (
    <group position={[0, y, z]}>
      <mesh>
        <boxGeometry args={[width * 0.72, 0.16, 0.26]} />
        <meshLambertMaterial color="#111111" />
      </mesh>
      <group ref={red}>
        {[-1, 1].map((side) => (
          <mesh key={side} position={[(side * width * 0.72) / 4, 0.1, 0]}>
            <boxGeometry args={[width * 0.3, 0.08, 0.2]} />
            <meshBasicMaterial color={palette.engine} toneMapped={false} />
          </mesh>
        ))}
      </group>
      <group ref={white}>
        {[-1, 1].map((side) => (
          <mesh key={side} position={[(side * width * 0.72) / 4, 0.1, 0]}>
            <boxGeometry args={[width * 0.3, 0.08, 0.2]} />
            <meshBasicMaterial color={palette.bulb} toneMapped={false} />
          </mesh>
        ))}
      </group>
      <pointLight ref={redLight} position={[0, 0.3, 0]} color={palette.engine} distance={9} decay={2} />
      <pointLight ref={whiteLight} position={[0, 0.3, 0]} color={palette.bulb} distance={9} decay={2} />
    </group>
  );
}
