import {
  BUILDING_DEPTH,
  BUILDING_WIDTH,
  EXTERIOR,
  FLOOR_HEIGHT,
  FLOOR_IDS,
  type BuildingLayout,
  type CharacterRole,
  type DoorLayout,
  type EngineLayout,
  type ExteriorLayout,
  type FloorId,
  type FloorLayout,
  type InteractionPoint,
  type NavEdge,
  type NavGraph,
  type NavNode,
  type RoomLayout,
  type WallKind,
  type WallSegment,
  type WindowLayout,
  floorY,
} from "./types";

const EXTERIOR_H = 2.72;
const INTERIOR_H = 2.42;
const RAIL_H = 0.86;
const WALL_T = 0.14;
const WINDOW_W = 1.32;
const WINDOW_H = 1.22;
const WINDOW_Y = 1.48;
const DOOR_W = 0.94;

/** Stair and hall core. x 6–10, z 3.85–8.6. */
export const STAIR_CORE = { x: 6, z: 3.85, w: 4, d: 4.75 } as const;

const CROSS_Z = 6.15;

export function createBuildingLayout(): BuildingLayout {
  return { floors: FLOOR_IDS.map(createFloor) };
}

export function findRoom(layout: BuildingLayout, roomId: string): RoomLayout | undefined {
  for (const floor of layout.floors) {
    const room = floor.rooms.find((entry) => entry.id === roomId);
    if (room) return room;
  }
  return undefined;
}

/**
 * Open floor in a room, toward the cutaway (south) and toward the stair core,
 * so a fire placed in any room stays visible and off the furniture.
 */
export function fireAnchor(room: RoomLayout): [number, number, number] {
  const towardCore = room.x < BUILDING_WIDTH / 2 ? 0.7 : 0.3;
  return [room.x + room.w * towardCore, 0, room.z + room.d * 0.32];
}

function createFloor(floorId: FloorId): FloorLayout {
  const rooms = roomsFor(floorId);
  const doors = doorsFor(floorId);
  const windows = windowsFor(floorId);
  const walls = wallsFor(floorId, doors, windows);
  return { id: floorId, y: floorY(floorId), rooms, walls, doors, windows };
}

function rid(floorId: FloorId, kind: string): string {
  return `${floorId}-${kind}`;
}

function roomsFor(floorId: FloorId): RoomLayout[] {
  const west: RoomLayout[] = [
    { id: rid(floorId, "living"), floorId, kind: "living", label: "Living", x: 0, z: 0, w: 6, d: CROSS_Z },
    { id: rid(floorId, "bedroom-w"), floorId, kind: "bedroom", label: "Bedroom", x: 0, z: CROSS_Z, w: 6, d: BUILDING_DEPTH - CROSS_Z },
  ];
  const east: RoomLayout[] = [
    { id: rid(floorId, "kitchen"), floorId, kind: "kitchen", label: "Kitchen", x: 10, z: 0, w: 6, d: CROSS_Z },
    { id: rid(floorId, "bedroom-e"), floorId, kind: "bedroom", label: "Bedroom", x: 10, z: CROSS_Z, w: 6, d: BUILDING_DEPTH - CROSS_Z },
  ];
  const core: RoomLayout[] = [
    { id: rid(floorId, "hall"), floorId, kind: "hall", label: "Hall", x: 6, z: 0, w: 4, d: STAIR_CORE.z },
    {
      id: rid(floorId, "landing"),
      floorId,
      kind: "landing",
      label: "Landing",
      x: 6,
      z: STAIR_CORE.z + STAIR_CORE.d,
      w: 4,
      d: BUILDING_DEPTH - (STAIR_CORE.z + STAIR_CORE.d),
    },
  ];
  return [...west, ...east, ...core];
}

function doorsFor(floorId: FloorId): DoorLayout[] {
  const between = (a: string, b: string): [string, string] => [rid(floorId, a), rid(floorId, b)];
  return [
    {
      id: rid(floorId, "door-living-hall"),
      floorId,
      between: between("living", "hall"),
      axis: "z",
      x: 6,
      z: 2.35 - DOOR_W / 2,
      width: DOOR_W,
      swing: 0.7,
    },
    {
      id: rid(floorId, "door-kitchen-hall"),
      floorId,
      between: between("kitchen", "hall"),
      axis: "z",
      x: 10,
      z: 2.35 - DOOR_W / 2,
      width: DOOR_W,
      swing: -0.7,
    },
    {
      id: rid(floorId, "door-living-bed"),
      floorId,
      between: between("living", "bedroom-w"),
      axis: "x",
      x: 2.55,
      z: CROSS_Z,
      width: DOOR_W,
      swing: 0.5,
    },
    {
      id: rid(floorId, "door-kitchen-bed"),
      floorId,
      between: between("kitchen", "bedroom-e"),
      axis: "x",
      x: 12.7,
      z: CROSS_Z,
      width: DOOR_W,
      swing: -0.5,
    },
    {
      id: rid(floorId, "door-bed-w-landing"),
      floorId,
      between: between("bedroom-w", "landing"),
      axis: "z",
      x: 6,
      z: 9.85,
      width: DOOR_W,
      swing: 0.55,
    },
    {
      id: rid(floorId, "door-bed-e-landing"),
      floorId,
      between: between("bedroom-e", "landing"),
      axis: "z",
      x: 10,
      z: 9.85,
      width: DOOR_W,
      swing: -0.55,
    },
  ];
}

function windowsFor(floorId: FloorId): WindowLayout[] {
  const specs: Array<Omit<WindowLayout, "floorId" | "id" | "roomId"> & { id: string; room: string }> = [
    { id: "window-living-w", room: "living", facing: "west", x: WALL_T / 2, z: 2.5, y: WINDOW_Y, w: WINDOW_W, h: WINDOW_H },
    { id: "window-bed-w", room: "bedroom-w", facing: "west", x: WALL_T / 2, z: 9.2, y: WINDOW_Y, w: WINDOW_W, h: WINDOW_H },
    { id: "window-bed-w-n", room: "bedroom-w", facing: "north", x: 2.5, z: BUILDING_DEPTH - WALL_T / 2, y: WINDOW_Y, w: WINDOW_W, h: WINDOW_H },
    { id: "window-landing-n", room: "landing", facing: "north", x: 8, z: BUILDING_DEPTH - WALL_T / 2, y: WINDOW_Y, w: WINDOW_W, h: WINDOW_H },
    { id: "window-bed-e-n", room: "bedroom-e", facing: "north", x: 13.2, z: BUILDING_DEPTH - WALL_T / 2, y: WINDOW_Y, w: WINDOW_W, h: WINDOW_H },
  ];
  return specs.map((spec) => ({
    id: rid(floorId, spec.id),
    floorId,
    roomId: rid(floorId, spec.room),
    x: spec.x,
    z: spec.z,
    y: spec.y,
    w: spec.w,
    h: spec.h,
    facing: spec.facing,
  }));
}

function wallsFor(floorId: FloorId, doors: DoorLayout[], windows: WindowLayout[]): WallSegment[] {
  const walls: WallSegment[] = [];

  const pushSpans = (
    id: string,
    fixed: number,
    along: "x" | "z",
    from: number,
    to: number,
    gaps: Array<[number, number]>,
    kind: WallKind,
    height: number,
  ) => {
    const spans = subtractGaps(from, to, gaps);
    spans.forEach(([a, b], index) => {
      const center = (a + b) / 2;
      const length = b - a;
      const thickness = kind === "rail" ? 0.08 : WALL_T;
      walls.push({
        id: rid(floorId, `${id}-${index}`),
        floorId,
        x: along === "z" ? fixed : center,
        z: along === "z" ? center : fixed,
        w: along === "z" ? thickness : length,
        d: along === "z" ? length : thickness,
        h: height,
        kind,
      });
    });
  };

  const doorGaps = (axis: "x" | "z", fixed: number) =>
    doors
      .filter((door) => door.axis === axis && Math.abs((axis === "z" ? door.x : door.z) - fixed) < 0.01)
      .map((door) => {
        const start = axis === "z" ? door.z : door.x;
        return [start, start + door.width] as [number, number];
      });

  pushSpans(
    "west-facade",
    WALL_T / 2,
    "z",
    0,
    BUILDING_DEPTH,
    windows.filter((win) => win.facing === "west").map((win) => [win.z - win.w / 2, win.z + win.w / 2]),
    "exterior-west",
    EXTERIOR_H,
  );

  pushSpans(
    "north-facade",
    BUILDING_DEPTH - WALL_T / 2,
    "x",
    0,
    BUILDING_WIDTH,
    windows.filter((win) => win.facing === "north").map((win) => [win.x - win.w / 2, win.x + win.w / 2]),
    "exterior-north",
    EXTERIOR_H,
  );

  pushSpans("partition-west", 6, "z", 0, STAIR_CORE.z, doorGaps("z", 6), "interior", INTERIOR_H);
  pushSpans("rail-west-stair", 6, "z", STAIR_CORE.z, STAIR_CORE.z + STAIR_CORE.d, [], "rail", RAIL_H);
  pushSpans(
    "partition-west-back",
    6,
    "z",
    STAIR_CORE.z + STAIR_CORE.d,
    BUILDING_DEPTH - WALL_T,
    doorGaps("z", 6),
    "interior",
    INTERIOR_H,
  );

  pushSpans("partition-east", 10, "z", 0, STAIR_CORE.z, doorGaps("z", 10), "interior", INTERIOR_H);
  pushSpans("rail-east-stair", 10, "z", STAIR_CORE.z, STAIR_CORE.z + STAIR_CORE.d, [], "rail", RAIL_H);
  pushSpans(
    "partition-east-back",
    10,
    "z",
    STAIR_CORE.z + STAIR_CORE.d,
    BUILDING_DEPTH - WALL_T,
    doorGaps("z", 10),
    "interior",
    INTERIOR_H,
  );

  pushSpans("cross-west", CROSS_Z, "x", WALL_T, 6, doorGaps("x", CROSS_Z).filter((gap) => gap[0] < 6), "interior", INTERIOR_H);
  pushSpans("cross-east", CROSS_Z, "x", 10, BUILDING_WIDTH - 0.04, doorGaps("x", CROSS_Z).filter((gap) => gap[0] > 9), "interior", INTERIOR_H);

  return walls;
}

/** Center of a room on its own floor, at walkable height. */
export function roomCenter(layout: BuildingLayout, roomId: string): [number, number, number] {
  const room = findRoom(layout, roomId);
  if (!room) throw new Error(`Unknown room id: ${roomId}`);
  const floor = layout.floors.find((entry) => entry.id === room.floorId);
  if (!floor) throw new Error(`Unknown floor for room: ${roomId}`);
  return [room.x + room.w / 2, floor.y, room.z + room.d / 2];
}

export function findDoor(layout: BuildingLayout, doorId: string): DoorLayout | undefined {
  for (const floor of layout.floors) {
    const door = floor.doors.find((entry) => entry.id === doorId);
    if (door) return door;
  }
  return undefined;
}

export function findWindow(layout: BuildingLayout, windowId: string): WindowLayout | undefined {
  for (const floor of layout.floors) {
    const win = floor.windows.find((entry) => entry.id === windowId);
    if (win) return win;
  }
  return undefined;
}

/** World position of a window's glass, for aiming the ladder or the hose. */
export function windowWorldPosition(layout: BuildingLayout, windowId: string): [number, number, number] {
  const win = findWindow(layout, windowId);
  if (!win) throw new Error(`Unknown window id: ${windowId}`);
  const floor = layout.floors.find((entry) => entry.id === win.floorId);
  if (!floor) throw new Error(`Unknown floor for window: ${windowId}`);
  return [win.x, floor.y + win.y, win.z];
}

/** Street, sidewalk, fire engine parking spot and hydrant, west of the building. */
export function buildExteriorLayout(): ExteriorLayout {
  const sidewalkWidth = 2.2;
  const streetWidth = 6.4;
  const setback = 0;
  const engine: EngineLayout = {
    position: [-(setback + sidewalkWidth + streetWidth / 2), 0, BUILDING_DEPTH / 2],
    rotation: 0,
    length: 9.2,
    width: 2.6,
  };
  return {
    sidewalkWidth,
    streetWidth,
    setback,
    engine,
    hydrant: [-(setback + sidewalkWidth * 0.55), 0, 1.4],
  };
}

/**
 * One stable station per teammate-built character. Positions only: no
 * behavior, no assignment logic, no story outcome. Teammates mount their own
 * character models here and drive them from the Python timeline.
 */
export function buildInteractionPoints(layout: BuildingLayout, exterior: ExteriorLayout): InteractionPoint[] {
  const point = (
    id: string,
    role: CharacterRole,
    floorId: InteractionPoint["floorId"],
    position: [number, number, number],
    heading: number,
    navNodeId: string,
    label: string,
  ): InteractionPoint => ({ id, role, floorId, position, heading, navNodeId, label });

  const [ex, ey, ez] = exterior.engine.position;

  return [
    point(
      "station-coordinator",
      "coordinator",
      EXTERIOR,
      [ex - exterior.engine.width, ey, ez - 2.5],
      Math.PI / 2,
      "exterior-command",
      "Incident command post, street side of the engine",
    ),
    point(
      "station-ladder-operator",
      "ladder_operator",
      EXTERIOR,
      [ex, ey, ez + exterior.engine.length / 2 - 0.6],
      Math.PI / 2,
      "exterior-engine",
      "Aerial ladder turntable control panel",
    ),
    point(
      "station-hose-operator",
      "hose_operator",
      EXTERIOR,
      [exterior.hydrant[0] + 0.8, 0, exterior.hydrant[2]],
      Math.PI / 2,
      "exterior-hydrant",
      "Hydrant hookup and hose bed",
    ),
    point("station-rescuer", "rescuer", 1, roomCenter(layout, "1-hall"), 0, "1-hall", "Ground floor hall, staging for interior search"),
    point("station-elder", "elder", 2, roomCenter(layout, "2-bedroom-w"), 0, "2-bedroom-w", "Floor 2 west bedroom, nearest the fire"),
    point("station-adult", "adult", 3, roomCenter(layout, "3-living"), 0, "3-living", "Floor 3 living room"),
    point("station-child", "child", 4, roomCenter(layout, "4-bedroom-e"), 0, "4-bedroom-e", "Floor 4 east bedroom"),
  ];
}

/**
 * Walkable graph for all seven characters: a node per room, per door, per
 * stair link, and a short exterior chain from the fire engine to the
 * building entrance. Geometry only, used to plan a route; nothing here moves
 * a character or decides where one should go.
 */
export function buildNavGraph(layout: BuildingLayout, exterior: ExteriorLayout): NavGraph {
  const nodes: Record<string, NavNode> = {};
  const edges: NavEdge[] = [];
  const addNode = (node: NavNode) => {
    nodes[node.id] = node;
  };
  const addEdge = (a: string, b: string) => {
    const na = nodes[a];
    const nb = nodes[b];
    const distance = na && nb ? distance3(na.position, nb.position) : undefined;
    edges.push({ a, b, distance });
  };

  const [ex, ey, ez] = exterior.engine.position;
  addNode({ id: "exterior-engine", floorId: EXTERIOR, kind: "exterior", position: [ex, ey, ez] });
  addNode({
    id: "exterior-command",
    floorId: EXTERIOR,
    kind: "exterior",
    position: [ex - exterior.engine.width, ey, ez - 2.5],
  });
  addNode({ id: "exterior-hydrant", floorId: EXTERIOR, kind: "exterior", position: [...exterior.hydrant] });
  addNode({
    id: "exterior-sidewalk",
    floorId: EXTERIOR,
    kind: "exterior",
    position: [-exterior.setback - exterior.sidewalkWidth / 2, 0, BUILDING_DEPTH / 2],
  });
  addNode({ id: "exterior-entry", floorId: EXTERIOR, kind: "exterior", position: [-0.05, 0, 1.9] });
  addEdge("exterior-engine", "exterior-command");
  addEdge("exterior-engine", "exterior-hydrant");
  addEdge("exterior-engine", "exterior-sidewalk");
  addEdge("exterior-hydrant", "exterior-sidewalk");
  addEdge("exterior-sidewalk", "exterior-entry");

  for (const floor of layout.floors) {
    for (const room of floor.rooms) {
      addNode({
        id: room.id,
        floorId: room.floorId,
        kind: room.kind === "hall" ? "hall" : room.kind === "landing" ? "landing" : "room",
        position: [room.x + room.w / 2, floor.y, room.z + room.d / 2],
        roomId: room.id,
      });
    }
    for (const door of floor.doors) {
      addNode({ id: door.id, floorId: door.floorId, kind: "door", position: [door.x, floor.y, door.z] });
      addEdge(door.between[0], door.id);
      addEdge(door.id, door.between[1]);
    }
  }

  addEdge("exterior-entry", rid(1, "hall"));

  // Vertical routes follow the switchback stair mesh (Staircase.tsx), not a
  // straight hall→hall chord through the slab. Nodes sit on the lower flight,
  // mid-landing, and upper flight so pathfinding walks the visible stairs.
  for (let floorId = 1; floorId < FLOOR_IDS.length; floorId += 1) {
    const lower = floorId as FloorId;
    const upper = (floorId + 1) as FloorId;
    const y0 = floorY(lower);
    const enterId = `${lower}-stair-enter`;
    const midId = `${lower}-stair-mid`;
    const exitId = `${lower}-stair-exit`;
    addNode({
      id: enterId,
      floorId: lower,
      kind: "stair",
      position: [7.0, y0 + 0.05, 4.2],
    });
    addNode({
      id: midId,
      floorId: lower,
      kind: "stair",
      position: [8.0, y0 + FLOOR_HEIGHT / 2, 7.95],
    });
    addNode({
      id: exitId,
      floorId: upper,
      kind: "stair",
      position: [9.0, y0 + FLOOR_HEIGHT - 0.05, 4.2],
    });
    addEdge(rid(lower, "hall"), enterId);
    addEdge(enterId, midId);
    addEdge(midId, exitId);
    addEdge(exitId, rid(upper, "hall"));
    // Mid-landing also reaches the north landing room on the lower floor.
    addEdge(midId, rid(lower, "landing"));
  }

  return { nodes, edges };
}

function distance3(a: [number, number, number], b: [number, number, number]): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

function subtractGaps(from: number, to: number, gaps: Array<[number, number]>): Array<[number, number]> {
  let spans: Array<[number, number]> = [[from, to]];
  for (const [g0, g1] of gaps) {
    const next: Array<[number, number]> = [];
    for (const [a, b] of spans) {
      if (g1 <= a || g0 >= b) {
        next.push([a, b]);
        continue;
      }
      if (g0 > a) next.push([a, Math.max(a, g0)]);
      if (g1 < b) next.push([Math.min(b, g1), b]);
    }
    spans = next;
  }
  return spans.filter(([a, b]) => b - a > 0.08);
}
