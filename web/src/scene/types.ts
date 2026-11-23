import type { ReactNode } from "react";

export const FLOOR_IDS = [1, 2, 3, 4, 5] as const;

/** 1-based story number. Story 1 is the ground floor. */
export type FloorId = (typeof FLOOR_IDS)[number];

/** Meters between walkable surfaces. Story n sits at y = (n - 1) * FLOOR_HEIGHT. */
export const FLOOR_HEIGHT = 3;

export const BUILDING_WIDTH = 16;
export const BUILDING_DEPTH = 12;

export function floorY(floorId: FloorId): number {
  return (floorId - 1) * FLOOR_HEIGHT;
}

export type RoomKind = "living" | "bedroom" | "kitchen" | "hall" | "landing";

export interface RoomLayout {
  id: string;
  floorId: FloorId;
  kind: RoomKind;
  label: string;
  /** Min corner on the ground plane. */
  x: number;
  z: number;
  w: number;
  d: number;
}

export type WallKind = "exterior-west" | "exterior-north" | "interior" | "rail";

export interface WallSegment {
  id: string;
  floorId: FloorId;
  /** Center of the segment on the floor plane. */
  x: number;
  z: number;
  w: number;
  d: number;
  h: number;
  kind: WallKind;
}

export interface DoorLayout {
  id: string;
  floorId: FloorId;
  between: [string, string];
  /** Hinge point. The leaf extends along the wall from here. */
  x: number;
  z: number;
  width: number;
  /** "z" = wall has constant x (leaf runs along z). "x" = wall has constant z. */
  axis: "x" | "z";
  /** Fully-open target angle, radians around Y. Positive swings toward -x / -z. Actual rotation is `swing * openness`. */
  swing: number;
}

export interface WindowLayout {
  id: string;
  floorId: FloorId;
  roomId: string;
  x: number;
  z: number;
  /** Center height above the walkable floor. */
  y: number;
  w: number;
  h: number;
  /** Which exterior wall the glass sits in. */
  facing: "west" | "north";
}

export interface FloorLayout {
  id: FloorId;
  y: number;
  rooms: RoomLayout[];
  walls: WallSegment[];
  doors: DoorLayout[];
  windows: WindowLayout[];
}

export interface BuildingLayout {
  floors: FloorLayout[];
}

/**
 * Visual fire only. A timeline player should pass the current values in;
 * the scene does not spread fire or pick an outcome.
 */
export interface FireVisualProps {
  floorId: FloorId;
  roomId: string;
  /** 0 hides the effect. 1 is a fully developed blaze. */
  intensity: number;
}

/** 0-based "exterior" pseudo-floor for anything that lives on the street. */
export type ExteriorLevel = 0;
export const EXTERIOR: ExteriorLevel = 0;

/**
 * Nav graph node. `floorId` is 0 for exterior nodes (street, engine, entry).
 * Positions are world-space meters, y-up, matching the building origin.
 */
export interface NavNode {
  id: string;
  floorId: FloorId | ExteriorLevel;
  kind: "room" | "door" | "hall" | "landing" | "stair" | "exterior";
  position: [number, number, number];
  /** Room this node sits in, when applicable. */
  roomId?: string;
}

export interface NavEdge {
  a: string;
  b: string;
  /** Meters. Defaults to the straight-line distance between the two nodes. */
  distance?: number;
}

export interface NavGraph {
  nodes: Record<string, NavNode>;
  edges: NavEdge[];
}

/** Which of the seven teammate-built characters a station is for. */
export type CharacterRole =
  | "coordinator"
  | "rescuer"
  | "hose_operator"
  | "ladder_operator"
  | "elder"
  | "adult"
  | "child";

/**
 * A stable place in the world a character's role is expected to occupy or
 * work from. Geometry only: no behavior, no assignment logic.
 */
export interface InteractionPoint {
  id: string;
  role: CharacterRole;
  floorId: FloorId | ExteriorLevel;
  position: [number, number, number];
  /** Facing direction in radians around Y, 0 = +Z. */
  heading: number;
  /** Nearest nav graph node, so a path can be planned to/from this point. */
  navNodeId: string;
  label: string;
}

export interface EngineLayout {
  /** Cab-forward position of the fire engine on the street, meters. */
  position: [number, number, number];
  /** Radians around Y. 0 = facing +Z (toward the building). */
  rotation: number;
  length: number;
  width: number;
}

export interface ExteriorLayout {
  streetWidth: number;
  sidewalkWidth: number;
  /** Distance the street's near edge sits from the building's west facade. */
  setback: number;
  engine: EngineLayout;
  hydrant: [number, number, number];
}

export interface Engine9SceneProps {
  /** Current state of every externally controllable world element. */
  worldState: import("./events").WorldState;
  /** Increment to glide the camera back to the establishing shot. */
  cameraCue?: number;
  /** Show small debug gizmos at every interaction point and nav node. */
  showDebugMarkers?: boolean;
  /** Added to the fire engine's parked z position. Nonzero while it's still driving in; 0 once parked. */
  engineZOffset?: number;
  /** Increment to cut the camera to a closeup framing `closeupTarget`. */
  closeupCue?: number;
  closeupTarget?: [number, number, number];
  children?: ReactNode;
}
