# Engine 9 scene

React, TypeScript, and React Three Fiber night-time cutaway of a five-story apartment building:
stacked floors with a central stair, a fire engine with a deployable aerial ladder, a hose with a
controllable water stream, and fire/smoke — all externally controlled. No agents, story logic, or
predetermined outcomes live here.

```bash
cd web
npm install
npm run dev
```

`npm run dev` opens a small dev harness (`src/App.tsx`) with buttons to toggle fire, doors, the
ladder, the hose, and to walk a placeholder capsule from the fire engine to floor 3 (verifying the
nav graph end to end).

`Engine9Scene` in `src/scene/Engine9Scene.tsx` is the piece to drop into another app. It takes one
required prop, `worldState` (see `src/scene/events.ts`), plus optional `cameraCue` and
`showDebugMarkers`. It renders no characters and makes no decisions — everything it draws comes
from `worldState`, which the host app builds by folding `world_event` rows from the Python sim's
event log with `applyWorldEvent`.

**See [`INTEGRATION.md`](../INTEGRATION.md) at the repo root** for the coordinate system, every
location id (rooms, doors, windows, stairs), the nav graph, the full event schema, the seven
character interaction points, and how to mount a character.

Coordinates are meters, y-up. The origin is the south-west corner of story 1. Story `n` is at
`y = (n - 1) * 3`.
