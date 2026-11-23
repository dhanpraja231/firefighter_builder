import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";

export type CharacterKind = "robot" | "victim";

export interface CharacterVisual {
  label: string;
  kind: CharacterKind;
  /** Accent color: robot chassis panel, or victim's clothing. */
  color: string;
  height?: number;
}

/**
 * One agent's on-screen body. Purely presentational: the caller (a timeline
 * player) computes `position`/`heading`/`moving`/`utterance` every frame
 * from the event log and passes them in, the same contract INTEGRATION.md
 * describes for `PlaceholderWalker`. Mount as a child of `<Engine9Scene>`.
 *
 * No external model: articulated procedural limbs with a sine-driven walk
 * cycle. A real rigged asset (the `character` branch's MMD firefighter) was
 * tried first -- its loader only supports three@0.84.x against our 0.180.0,
 * a six-major-version gap npm itself refused to resolve, so it was dropped
 * rather than risk breaking a working scene on an unverifiable loader.
 */
export function Character({
  position,
  heading = 0,
  visual,
  utterance,
  dimmed,
  moving = false,
}: {
  position: [number, number, number];
  heading?: number;
  visual: CharacterVisual;
  utterance?: string | null;
  dimmed?: boolean;
  moving?: boolean;
}) {
  const height = visual.height ?? (visual.kind === "robot" ? 1.2 : 1.6);
  const opacity = dimmed ? 0.35 : 1;
  const speaking = Boolean(utterance);
  return (
    <group position={position} rotation={[0, heading, 0]} name={`char-${visual.label}`}>
      {visual.kind === "robot" ? (
        <RobotBody color={visual.color} height={height} opacity={opacity} moving={moving} />
      ) : (
        <VictimBody color={visual.color} height={height} opacity={opacity} moving={moving} />
      )}
      {/* Name tag only. Dialogue goes to the fixed caption bar instead of an in-world bubble:
          at this camera distance bubbles wrapped to a few characters per line and overlapped
          each other whenever two agents stood near one another. */}
      <Html position={[0, height + 0.32, 0]} center distanceFactor={9} zIndexRange={[100, 0]} sprite>
        <div style={labelStyle(visual.color, speaking)}>{visual.label}</div>
      </Html>
    </group>
  );
}

function RobotBody({ color, height, opacity, moving }: { color: string; height: number; opacity: number; moving: boolean }) {
  const bodyH = height * 0.62;
  const headH = height * 0.24;
  const bob = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    const g = bob.current;
    if (!g) return;
    const target = moving ? Math.abs(Math.sin(clock.elapsedTime * 7)) * 0.06 : 0;
    g.position.y = THREE.MathUtils.damp(g.position.y, target, 8, 0.016);
    g.rotation.z = moving ? Math.sin(clock.elapsedTime * 7) * 0.04 : THREE.MathUtils.damp(g.rotation.z, 0, 8, 0.016);
  });
  return (
    <group ref={bob}>
      <mesh position={[0, bodyH / 2, 0]} castShadow>
        <boxGeometry args={[0.46, bodyH, 0.34]} />
        <meshLambertMaterial color="#aab2bd" transparent opacity={opacity} />
      </mesh>
      <mesh position={[0, bodyH / 2, 0.175]} castShadow>
        <boxGeometry args={[0.3, bodyH * 0.6, 0.02]} />
        <meshLambertMaterial color={color} transparent opacity={opacity} />
      </mesh>
      <mesh position={[0, bodyH + headH / 2, 0]} castShadow>
        <boxGeometry args={[0.3, headH, 0.28]} />
        <meshLambertMaterial color="#7d8591" transparent opacity={opacity} />
      </mesh>
      <mesh position={[0, bodyH + headH / 2, 0.15]}>
        <boxGeometry args={[0.2, 0.06, 0.02]} />
        <meshBasicMaterial color={color} toneMapped={false} transparent opacity={opacity} />
      </mesh>
      {[-0.14, 0.14].map((x) => (
        <mesh key={x} position={[x, bodyH * 0.12, 0]} castShadow>
          <boxGeometry args={[0.08, bodyH * 0.3, 0.1]} />
          <meshLambertMaterial color="#5c636e" transparent opacity={opacity} />
        </mesh>
      ))}
      <pointLight position={[0, bodyH + headH, 0]} intensity={0.5} distance={2.2} color={color} />
    </group>
  );
}

const LEG_SWING = 0.55;
const ARM_SWING = 0.4;
const WALK_SPEED = 7;

function VictimBody({ color, height, opacity, moving }: { color: string; height: number; opacity: number; moving: boolean }) {
  const legLen = height * 0.46;
  const torsoLen = height * 0.34;
  const headR = height * 0.085;
  const hipY = legLen;
  const shoulderY = hipY + torsoLen * 0.92;

  const legL = useRef<THREE.Group>(null);
  const legR = useRef<THREE.Group>(null);
  const armL = useRef<THREE.Group>(null);
  const armR = useRef<THREE.Group>(null);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime * WALK_SPEED;
    const legSwing = moving ? Math.sin(t) * LEG_SWING : 0;
    const armSwing = moving ? Math.sin(t + Math.PI) * ARM_SWING : 0;
    for (const [ref, v] of [
      [legL, legSwing],
      [legR, -legSwing],
      [armL, armSwing],
      [armR, -armSwing],
    ] as const) {
      if (ref.current) ref.current.rotation.x = THREE.MathUtils.damp(ref.current.rotation.x, v, 10, 0.016);
    }
  });

  const limb = (len: number, radius: number) => (
    <mesh position={[0, -len / 2, 0]} castShadow>
      <capsuleGeometry args={[radius, len * 0.65, 4, 8]} />
      <meshLambertMaterial color={color} transparent opacity={opacity} />
    </mesh>
  );

  return (
    <group>
      {/* legs, pivoting at the hip */}
      {[
        [legL, -0.1],
        [legR, 0.1],
      ].map(([ref, x], i) => (
        <group key={i} ref={ref as React.RefObject<THREE.Group>} position={[x as number, hipY, 0]}>
          {limb(legLen * 0.95, 0.09)}
        </group>
      ))}
      {/* torso */}
      <mesh position={[0, hipY + torsoLen / 2, 0]} castShadow>
        <capsuleGeometry args={[0.19, torsoLen * 0.6, 4, 8]} />
        <meshLambertMaterial color={color} transparent opacity={opacity} />
      </mesh>
      {/* arms, pivoting at the shoulder */}
      {[
        [armL, -0.26],
        [armR, 0.26],
      ].map(([ref, x], i) => (
        <group key={i} ref={ref as React.RefObject<THREE.Group>} position={[x as number, shoulderY, 0]}>
          {limb(torsoLen * 0.85, 0.06)}
        </group>
      ))}
      {/* head */}
      <mesh position={[0, shoulderY + headR * 1.3, 0]} castShadow>
        <sphereGeometry args={[headR, 12, 12]} />
        <meshLambertMaterial color="#e3b48c" transparent opacity={opacity} />
      </mesh>
    </group>
  );
}

/** `speaking` highlights whoever the caption bar is currently quoting. */
function labelStyle(color: string, speaking: boolean): React.CSSProperties {
  return {
    padding: "2px 8px",
    borderRadius: 4,
    background: speaking ? color : "rgba(5,6,10,0.92)",
    border: `1px solid ${color}`,
    color: speaking ? "#05060a" : color,
    fontSize: 12,
    fontWeight: 700,
    fontFamily: "monospace",
    whiteSpace: "nowrap",
    boxShadow: speaking ? `0 0 12px ${color}` : "none",
  };
}
