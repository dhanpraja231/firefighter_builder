import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { Building } from "./building/Building";
import { InteractionMarkers } from "./characters/InteractionMarkers";
import { FireEffect } from "./effects/FireEffect";
import { Smoke } from "./effects/RisingPoints";
import { WaterStream } from "./effects/WaterStream";
import { NightEnvironment } from "./environment/NightEnvironment";
import {
  buildExteriorLayout,
  buildInteractionPoints,
  buildNavGraph,
  createBuildingLayout,
  fireAnchor,
  findRoom,
  roomCenter,
  windowWorldPosition,
} from "./layout";
import { palette } from "./palette";
import { type Engine9SceneProps } from "./types";
import { FireEngine, ladderTurntablePosition } from "./vehicles/FireEngine";
import { Ladder } from "./vehicles/Ladder";

/**
 * Default view: straight into the open face of the building. The south and east sides have no
 * exterior wall (the cutaway), so from the south the viewer sees all five floors, the stairs and
 * everyone inside at once, with the street and the fire engine at the left edge. The camera must stay
 * at negative z to look into the rooms rather than at the closed west/north facade.
 */
export const ESTABLISHING_SHOT = {
  position: new THREE.Vector3(-1, 8, -21.5),
  target: new THREE.Vector3(6, 6.8, 6),
};

/**
 * The full Engine 9 environment: building, fire engine, ladder, hose, and
 * night exterior. Pure presentation driven by `worldState` — see
 * INTEGRATION.md for the coordinate system, node ids, and event schema this
 * component expects from the Python sim and from teammates' characters.
 */
export function Engine9Scene({
  worldState,
  cameraCue,
  showDebugMarkers,
  engineZOffset = 0,
  closeupCue,
  closeupTarget,
  children,
}: Engine9SceneProps) {
  const layout = useMemo(() => createBuildingLayout(), []);
  const exterior = useMemo(() => buildExteriorLayout(), []);
  const interactionPoints = useMemo(() => buildInteractionPoints(layout, exterior), [layout, exterior]);
  useMemo(() => buildNavGraph(layout, exterior), [layout, exterior]);

  const ladderOrigin = useMemo(() => ladderTurntablePosition(exterior.engine), [exterior]);
  const ladderTarget = useMemo(() => {
    const id = worldState.ladder.targetWindowId;
    return id ? windowWorldPosition(layout, id) : null;
  }, [layout, worldState.ladder.targetWindowId]);

  const hoseOrigin = useMemo(
    () => interactionPoints.find((point) => point.role === "hose_operator")!.position,
    [interactionPoints],
  );
  const hoseTarget = useMemo(() => {
    const id = worldState.hose.targetWindowId;
    return id ? windowWorldPosition(layout, id) : null;
  }, [layout, worldState.hose.targetWindowId]);

  const fires = useMemo(
    () =>
      Object.entries(worldState.fires)
        .filter(([, intensity]) => intensity > 0.01)
        .map(([roomId, intensity]) => {
          const room = findRoom(layout, roomId);
          if (!room) return null;
          const floor = layout.floors.find((entry) => entry.id === room.floorId)!;
          const [x, , z] = fireAnchor(room);
          return { roomId, intensity, position: [x, floor.y, z] as [number, number, number] };
        })
        .filter((entry): entry is { roomId: string; intensity: number; position: [number, number, number] } => entry !== null),
    [layout, worldState.fires],
  );

  const smokeOnly = useMemo(
    () =>
      Object.entries(worldState.smoke)
        .filter(([roomId, intensity]) => intensity > 0.01 && !(worldState.fires[roomId] > 0.01))
        .map(([roomId, intensity]) => ({ roomId, intensity, position: roomCenter(layout, roomId) })),
    [layout, worldState.fires, worldState.smoke],
  );

  return (
    <group name="engine9-scene">
      <fog attach="fog" args={[palette.fog, 48, 145]} />
      <CameraDirector cue={cameraCue} closeupCue={closeupCue} closeupTarget={closeupTarget} />

      <NightEnvironment exterior={exterior} />
      <Building layout={layout} worldState={worldState} />
      <FireEngine engine={exterior.engine} lightsOn={worldState.engineLights} zOffset={engineZOffset} />
      <Ladder origin={ladderOrigin} target={ladderTarget} deployed={worldState.ladder.deployed} />
      <WaterStream origin={hoseOrigin} supply={exterior.hydrant} target={hoseTarget} active={worldState.hose.active} />

      {fires.map((fire) => (
        <FireEffect key={fire.roomId} position={[fire.position[0], fire.position[1], fire.position[2]]} intensity={fire.intensity} />
      ))}
      {smokeOnly.map((entry) => (
        <group key={entry.roomId} position={[entry.position[0], entry.position[1] + 1.4, entry.position[2]]}>
          <Smoke intensity={entry.intensity} />
        </group>
      ))}

      {showDebugMarkers && <InteractionMarkers points={interactionPoints} />}
      {children}
    </group>
  );
}

/**
 * Offset from the active character to the camera. Keeps the camera on the open (south) side of the
 * building, slightly left and above, so every cut looks into the cutaway instead of at a closed wall.
 */
const CLOSEUP_OFFSET = new THREE.Vector3(-5, 2.6, -12);

function CameraDirector({
  cue,
  closeupCue,
  closeupTarget,
}: {
  cue?: number;
  closeupCue?: number;
  closeupTarget?: [number, number, number];
}) {
  const { camera } = useThree();
  const tweening = useRef(false);
  const elapsed = useRef(0);
  const duration = useRef(1.6);
  const start = useRef(new THREE.Vector3());
  const destPos = useRef(ESTABLISHING_SHOT.position.clone());
  const destLookAt = useRef(ESTABLISHING_SHOT.target.clone());

  useEffect(() => {
    if (cue === undefined) return;
    tweening.current = true;
    elapsed.current = 0;
    duration.current = 1.6;
    start.current.copy(camera.position);
    destPos.current.copy(ESTABLISHING_SHOT.position);
    destLookAt.current.copy(ESTABLISHING_SHOT.target);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cue]);

  useEffect(() => {
    if (closeupCue === undefined || !closeupTarget) return;
    const [x, y, z] = closeupTarget;
    tweening.current = true;
    elapsed.current = 0;
    duration.current = 0.9;
    start.current.copy(camera.position);
    destPos.current.set(x, y, z).add(CLOSEUP_OFFSET);
    destLookAt.current.set(x, y + 1.3, z);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [closeupCue]);

  useFrame((_, delta) => {
    if (!tweening.current) return;
    elapsed.current += delta;
    const t = Math.min(1, elapsed.current / duration.current);
    const eased = 1 - Math.pow(1 - t, 3);
    camera.position.lerpVectors(start.current, destPos.current, eased);
    camera.lookAt(destLookAt.current);
    if (t >= 1) tweening.current = false;
  });

  return null;
}
