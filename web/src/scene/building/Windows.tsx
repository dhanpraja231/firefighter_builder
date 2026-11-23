import { palette } from "../palette";
import type { WindowLayout } from "../types";

/**
 * `fires` is roomId -> intensity (0..1, matches `WorldState.fires`); a
 * window glows orange when its room is burning. `broken` is windowId ->
 * whether the glass has been vented, breached, or burned through.
 */
export function Windows({
  windows,
  fires,
  broken,
}: {
  windows: WindowLayout[];
  fires: Record<string, number>;
  broken: Record<string, boolean>;
}) {
  return (
    <group name="windows">
      {windows.map((window) => (
        <Window
          key={window.id}
          window={window}
          heat={fires[window.roomId] ?? 0}
          broken={broken[window.id] ?? false}
        />
      ))}
    </group>
  );
}

function Window({ window, heat, broken }: { window: WindowLayout; heat: number; broken: boolean }) {
  const west = window.facing === "west";
  const glow = heat > 0.15 ? palette.fireGlow : palette.windowGlow;
  const glassSize: [number, number, number] = west ? [0.05, window.h, window.w] : [window.w, window.h, 0.05];
  const glowPosition: [number, number, number] = west
    ? [window.x + 0.22, window.y, window.z]
    : [window.x, window.y, window.z - 0.22];

  return (
    <group name={window.id} userData={{ windowId: window.id, roomId: window.roomId, broken }}>
      {!broken && (
        <mesh position={[window.x, window.y, window.z]}>
          <boxGeometry args={glassSize} />
          <meshLambertMaterial
            color={palette.glass}
            emissive={glow}
            emissiveIntensity={0.65 + heat * 1.5}
            transparent
            opacity={0.78}
          />
        </mesh>
      )}
      <mesh position={glowPosition} rotation={west ? [0, Math.PI / 2, 0] : [0, Math.PI, 0]}>
        <planeGeometry args={[window.w * 0.78, window.h * 0.78]} />
        <meshBasicMaterial
          color={glow}
          transparent
          opacity={(broken ? 0.65 : 0.45) + heat * 0.4}
          toneMapped={false}
        />
      </mesh>
      <Frame window={window} broken={broken} />
    </group>
  );
}

function Frame({ window, broken }: { window: WindowLayout; broken: boolean }) {
  const west = window.facing === "west";
  const bar = 0.07;
  const span = window.w;
  const vertical: [number, number, number] = west ? [0.09, window.h + bar, bar] : [bar, window.h + bar, 0.09];
  const horizontal: [number, number, number] = west ? [0.09, bar, span + bar] : [span + bar, bar, 0.09];
  const half = span / 2;
  const trim = broken ? palette.doorDark : palette.woodTrim;
  return (
    <group>
      <mesh position={west ? [window.x, window.y, window.z - half] : [window.x - half, window.y, window.z]}>
        <boxGeometry args={vertical} />
        <meshLambertMaterial color={trim} />
      </mesh>
      <mesh position={west ? [window.x, window.y, window.z + half] : [window.x + half, window.y, window.z]}>
        <boxGeometry args={vertical} />
        <meshLambertMaterial color={trim} />
      </mesh>
      <mesh position={[window.x, window.y + window.h / 2, window.z]}>
        <boxGeometry args={horizontal} />
        <meshLambertMaterial color={trim} />
      </mesh>
      <mesh position={[window.x, window.y - window.h / 2, window.z]}>
        <boxGeometry args={horizontal} />
        <meshLambertMaterial color={trim} />
      </mesh>
    </group>
  );
}
