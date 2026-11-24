# Engine 9 scene: integration guide

This is the contract between the 3D environment (`web/`) and everything that plugs into it: the
seven character models, and the Python simulation + Bruin event log. The scene owns geometry,
materials, and presentation only. It never decides what happens — every fire, door, ladder move,
or hose spray comes in from the outside as `WorldState`, and nothing here places a character,
assigns a task, or picks an outcome.

If you only read one section, read [4. Event schema](#4-event-schema) and
[5. Mounting characters](#5-mounting-characters).

How the film itself is made (autonomous agents, the live `/stream` protocol, the animation hints
the engine adds to events, recording) is in [`LIVE_STORY.md`](LIVE_STORY.md).

## Contents

- [1. Coordinate system](#1-coordinate-system)
- [2. Location IDs](#2-location-ids)
- [3. Navigation graph](#3-navigation-graph)
- [4. Event schema](#4-event-schema)
- [5. Mounting characters](#5-mounting-characters)
- [6. Interaction points](#6-interaction-points)
- [7. `Engine9Scene` props](#7-engine9scene-props)
- [8. Verified today](#8-verified-today)

## 1. Coordinate system

- Units: meters. Axes: Y-up, right-handed (same as Three.js).
- Origin: the south-west corner of story 1 (the ground floor), at ground level. `x` increases
  east, `z` increases north, `y` increases up.
- Building footprint: `x` from 0 to 16 (`BUILDING_WIDTH`), `z` from 0 to 12 (`BUILDING_DEPTH`).
- Story height: 3 m. Story `n` (1-based, `web/src/scene/types.ts` → `FloorId`, 1 to 5) sits at
  `y = (n - 1) * 3`.
- **SPEC.md's event schema uses a 0-based `floor`** (`payload.position.floor`, `y = floor * 3`).
  The two agree on `y`; the index is offset by one:

  ```
  web FloorId = payload.position.floor + 1
  payload.position.floor = web FloorId - 1
  ```

  Floor 0 in the event log is `FloorId = 1` here (the ground floor), and so on up to floor 4 →
  `FloorId = 5`.
- Exterior (street, sidewalk, fire engine, hydrant) is modeled as pseudo-floor `0`
  (`EXTERIOR` in `types.ts`), west of the building (`x < 0`). The building's real exterior wall
  with windows is the west and north facade; the south and east sides have no exterior wall —
  that's the cutaway the camera looks through.
- `payload.position.x/y/z` from the event log can be used as-is for any character's world
  position; no scaling or axis flips are needed.

## 2. Location IDs

Everything in the scene that can be referenced has a stable string id, generated once per floor
by `createBuildingLayout()` in `web/src/scene/layout.ts`. `{f}` below is the `FloorId`, 1 to 5.

**Rooms** (`{f}-{kind}`): `{f}-living`, `{f}-kitchen`, `{f}-bedroom-w`, `{f}-bedroom-e`,
`{f}-hall`, `{f}-landing`. Layout per floor: west side is `living` (south) + `bedroom-w` (north);
east side is `kitchen` (south) + `bedroom-e` (north); the central core is `hall` (south, at the
foot of the stairs) and `landing` (north, across the stair core). `hall` and `landing` are **not**
directly connected — the loop is hall ↔ living/kitchen ↔ bedroom ↔ landing.

**Doors** (`{f}-door-{a}-{b}`): `door-living-hall`, `door-kitchen-hall`, `door-living-bed`,
`door-kitchen-bed`, `door-bed-w-landing`, `door-bed-e-landing`. Look up geometry with
`findDoor(layout, id)`.

**Windows** (`{f}-window-{name}`): `window-living-w`, `window-bed-w` (both on the west facade),
`window-bed-w-n`, `window-landing-n`, `window-bed-e-n` (north facade). Look up world position with
`windowWorldPosition(layout, id)` — this is what you pass as a ladder or hose target.

**Stairs**: one switchback flight per floor gap, inside the central core (`x` 6–10, `z` 3.85–8.6),
rising from floor `n`'s hall to floor `n + 1`'s hall. There are 4 flights (1↔2, 2↔3, 3↔4, 4↔5).

**Exterior**: fire engine parked on the street at `x ≈ -5.4, z = 6` (`buildExteriorLayout()`),
hydrant near the south end of the sidewalk. Call `buildExteriorLayout()` for exact numbers — it's
a pure function, same output every time.

## 3. Navigation graph

`buildNavGraph(layout, exterior)` (in `layout.ts`) returns a `NavGraph`: one node per room, one
node per door (at its hinge point), a node per exterior waypoint, and edges for every door
connection plus one vertical edge per stair flight (`{f}-hall` ↔ `{f+1}-hall`) and a short chain
from the fire engine to the building entrance (`exterior-engine → exterior-sidewalk →
exterior-entry → 1-hall`).

`findPath(graph, fromId, toId)` in `web/src/scene/nav.ts` runs Dijkstra over that graph and
returns an ordered list of node ids, or `null` if unreachable. `pathWaypoints(graph, path)` turns
that into world-space points you can feed to any movement system. This is geometry only — it does
not know about door state, fire, or who is allowed where; that's for the Python sim to decide
before (or while) it emits `move` events.

Verified today: `findPath(graph, "exterior-engine", "3-hall")` returns
`exterior-engine → exterior-sidewalk → exterior-entry → 1-hall → 2-hall → 3-hall` (22.6 m), and a
placeholder capsule (`PlaceholderWalker`) walks it and arrives at exactly `(8, 6, 1.925)`, the
floor-3 hall center. `web/src/App.tsx` has a "Walk placeholder: engine → floor 3" button that
re-runs this live.

## 4. Event schema

The scene is a pure function of `WorldState` (`web/src/scene/events.ts`). Nothing in `scene/`
mutates it. Replay, live SSE, or a simple `useState` — whatever drives the host app — is
responsible for building the current `WorldState` and passing it to `<Engine9Scene worldState=
{...} />` every render.

```ts
interface WorldState {
  fires: Record<string, number>;         // roomId -> intensity, 0..1
  smoke: Record<string, number>;         // roomId -> intensity, 0..1 (independent of fires)
  doors: Record<string, number>;         // doorId -> openness, 0 closed .. 1 fully open
  brokenWindows: Record<string, boolean>; // windowId -> glass broken
  ladder: { deployed: number; targetWindowId: string | null }; // 0..1, null = stowed
  hose: { active: boolean; targetWindowId: string | null };
  engineLights: boolean;
}
```

`applyWorldEvent(state, event)` folds one `WorldEvent` into a new `WorldState` (pure, no
mutation). `applyWorldEvents(state, events)` folds a list. Use this to replay a timeline.

```ts
type WorldEvent =
  | { type: "fire"; roomId: string; intensity: number }
  | { type: "smoke"; roomId: string; intensity: number }
  | { type: "door"; doorId: string; openness: number }
  | { type: "window"; windowId: string; broken: boolean }
  | { type: "ladder"; deployed?: number; targetWindowId?: string | null }
  | { type: "hose"; active?: boolean; targetWindowId?: string | null }
  | { type: "engine_lights"; on: boolean };
```

**How this maps onto SPEC.md's event log**: a `WorldEvent` is exactly what belongs in
`payload.world` on a `world_event` row (`type: "world_event"`, sent by `director` or the sim).
Example row:

```json
{
  "run_id": "6f1c...",
  "seq": 88,
  "t_sim": 42.0,
  "agent_id": "director",
  "agent_role": "director",
  "type": "world_event",
  "payload": {
    "world": { "type": "fire", "roomId": "2-kitchen", "intensity": 0.6 }
  },
  "reasoning": "Grease fire reaches the cabinets.",
  "confidence": null
}
```

A timeline player folds these in order:

```ts
const worldState = timeline
  .filter((row) => row.type === "world_event")
  .reduce((state, row) => applyWorldEvent(state, row.payload.world), createDefaultWorldState());
```

`roomId`, `doorId`, `windowId` must be the location ids from [section 2](#2-location-ids) —
remember the floor-index offset from [section 1](#1-coordinate-system) when the sim picks a floor.

Fire and smoke are independent so a hallway can fill with smoke without flame in it. The scene
does not spread fire between rooms or infer smoke from fire — if a burning room's smoke should
also show, the sim should emit both a `fire` and a `smoke` event for that `roomId`.

## 5. Mounting characters

The scene renders zero characters. For `coordinator`, `rescuer`, `hose_operator`,
`ladder_operator`, `elder`, `adult`, and `child`:

1. Mount your character component as a **child of `<Engine9Scene>`** (it accepts `children`), so it
   shares the same coordinate space — no extra transform needed.
2. Drive position/rotation from the `move` events in the timeline (`payload.position.x/y/z`,
   converting `floor` per [section 1](#1-coordinate-system)). Interpolate between ticks however
   you like; `PlaceholderWalker` (`web/src/scene/characters/PlaceholderWalker.tsx`) is a worked
   example of walking a list of waypoints at a fixed speed, built only to verify the nav graph —
   feel free to copy its interpolation approach for a real character, but it is not meant to ship.
3. For a default/idle pose before the first `move` event arrives, use that role's entry in
   `buildInteractionPoints(layout, exterior)` — see [section 6](#6-interaction-points).
4. To plan a route for an `act` like `"move to 2B"`, resolve the destination to a room id, then
   `findPath(navGraph, startNodeId, roomId)` for waypoints. The sim decides the destination and
   timing; the graph just supplies geometry.
5. `speak` events (speech bubbles), approval modals, and the decision-log panel are host-app UI,
   not part of this scene — render them alongside `<Engine9Scene>`, not inside it.

## 6. Interaction points

`buildInteractionPoints(layout, exterior)` returns one stable station per role — a position,
heading, and the nearest nav graph node. These are starting/default positions only, not
assignments or behavior:

| id | role | floor | default location | nav node |
| --- | --- | --- | --- | --- |
| `station-coordinator` | `coordinator` | exterior | street side of the engine | `exterior-command` |
| `station-ladder-operator` | `ladder_operator` | exterior | ladder turntable control panel | `exterior-engine` |
| `station-hose-operator` | `hose_operator` | exterior | hydrant hookup / hose bed | `exterior-hydrant` |
| `station-rescuer` | `rescuer` | 1 | ground floor hall | `1-hall` |
| `station-elder` | `elder` | 2 | floor 2 west bedroom | `2-bedroom-w` |
| `station-adult` | `adult` | 3 | floor 3 living room | `3-living` |
| `station-child` | `child` | 4 | floor 4 east bedroom | `4-bedroom-e` |

Pass `showDebugMarkers` to `<Engine9Scene>` to render a colored ring + label at each point while
wiring up a character — turn it off once the real model is mounted there.

## 7. `Engine9Scene` props

```ts
interface Engine9SceneProps {
  worldState: WorldState;     // required, see section 4
  cameraCue?: number;         // increment to glide the camera to the establishing shot
  showDebugMarkers?: boolean; // show interaction-point gizmos (default false/omitted)
  children?: ReactNode;       // mount characters and any host-app-owned objects here
}
```

`Engine9Scene` does not own the `<Canvas>`, camera, or `OrbitControls` — the host app does (see
`web/src/App.tsx` for a working example with a small control panel for manual testing).

## 8. Verified today

- `npx tsc --noEmit` and `npm run build` both pass.
- The scene renders: building (5 floors, stacked stairs), night exterior (street, sidewalk,
  streetlights, moon, stars), fire engine with a strobing light bar, deployed ladder reaching a
  floor-3 window, hose jet, and fire/smoke on floor 2, confirmed both visually and by inspecting
  the live Three.js scene graph (object names, world-space positions of the fire anchor, ladder
  tip, and window glass all matched expectations within centimeters).
- `findPath` + `PlaceholderWalker` confirmed end to end: walking from `exterior-engine` to
  `3-hall` lands at exactly `(8, 6, 1.925)`, the floor-3 hall center.
