# Live story: how the film is made

Track 1 (Agent Animated Film): **we set the world, the characters and the opening event; the agents
decide every beat, including the ending.** Same setup, different endings on every run. The output is
a 1 to 3 minute animated short.

## What we fix, what the agents decide

| We set (the same every run) | The agents decide (different every run) |
| --- | --- |
| A 5-floor apartment building, night, fire engine outside | Who searches where, and in what order |
| The cast: commander, scout, hose, rescue robot; 8 residents with persona cards (`agents/personas/`) | Who gets rescued first, who is persuaded, who bolts, hides, or refuses |
| The opening event: a grease fire starts in the floor 3 kitchen | Where the fire spreads (it is a live simulation, see below), and how everyone adapts |
| The role prompts (`agents/roles/`) | Which twists land, when to vent or breach (risky acts wait for approval), when to retreat |
| | **How it ends** (computed from the final state, e.g. `brigade_arrives_in_time`, `family_lost`, `commander_retreat`) |

Each seed re-rolls every agent's traits (courage, caution, empathy, panic, trust...). The same seed
replays identically on the offline policy; different seeds give different stories. Across a 40-seed
sweep (`python agents/sweep.py`): 12 distinct endings, a different rescue order every time, 27
distinct sets of who is lost.

## Two brains behind one interface

- **Heuristic policy** (`agents/policy.py`): offline stand-in. Persona and role driven utility
  choices with seeded randomness. Runs with no network.
- **LLM policy** (`agents/llm.py`): the real autonomy path. Calls an OpenAI-compatible endpoint
  (Runware: `POST https://api.runware.ai/v1/chat/completions`). It is the default when both
  `RUNWARE_API_KEY` and `RUNWARE_MODEL` are set. Any failed or malformed reply falls back to the
  heuristic for that decision, so a run never stalls.

`GET /stream` and `--policy` pick between them; the `policy` field in every run says which one ran.

## Live fire

`agents/world.py` simulates the building. Each room has fuel and grows or burns out; flames spread
faster through open doors and up the stairwell; smoke leaks further than flame. Fire/smoke changes
are emitted as `world_event`s (about every 3 s per active room). Agents observe the fire, reroute
around burning routes, abandon victims past the point of no return, and the commander re-plans when
fire reaches a victim's floor. The web viewer ramps intensity smoothly between samples so the blaze
visibly grows and spreads.

## Real time, no skipping

The viewer plays the story as it happens:

```
GET /stream?seed=N[&policy=heuristic|llm][&speed=1][&lead=4]     (Server-Sent Events)

event: start   data: {"seed","run_id","policy","lead","speed"}
               data: <one event per message, SPEC.md section 1.1 schema>
: ping                                  (keepalive)
event: end     data: {"ending","policy","stats","run_number","memory","duration"}
event: error   data: {"error"}          (engine crashed; nothing saved)
```

Events are sent no earlier than `t_sim - lead` seconds after the stream starts (a few seconds of
lookahead for smooth movement) and as soon as ready if the agents are slower (for example a slow LLM
call). The viewer's clock can never run ahead of the newest event, so a slow decision shows
"agents deciding..." instead of skipping. There is no scrubber in the normal viewer
(`?debug` brings it back for development). If the streaming endpoint is missing, the viewer falls back
to `GET /run` (the whole story at once) and still plays it in real time.

Start the server and the viewer:

```sh
python agents/server.py          # http://127.0.0.1:8787  (/stream, /run, /memory)
cd web && npm install && npm run dev
```

`GET /run?seed=N` returns the whole run as JSON (used for tests, Postgres and Bruin).

## Animation hints in events

Every event keeps the SPEC schema. The engine adds optional `payload` keys; the viewer ignores
anything it does not know.

| Key | Where | Values |
| --- | --- | --- |
| `anim` | `move`, `act`, `speak`, `status` | `idle`, `walk`, `run`, `carry`, `flinch`, `argue`, `celebrate`, `collapse`, `pickup`, `plead`, `spray` (`sit` is supported by the viewer) |
| `room` | every `move` | room id, one room-to-room hop per event (`exterior-safe` for rescued residents) |
| `position` | most events | `{x, y, z, floor}` as in INTEGRATION.md |

The viewer also derives reactions from status: a resident plays "plead" when found, "celebrate"
when rescued, and collapses when lost.

## Characters

- **Firefighter robots** (commander, scout, hose, rescue): the firefighter PMX from `runcycle/` with
  its run cycle and leg IK (`web/src/scene/characters/Character.tsx`).
- **Residents**: rigged Quaternius characters (`models/victims/`) played by
  `web/src/scene/characters/RiggedCharacter.tsx`. Their clip sets (Idle, Walk, Run, Walk_Carry,
  RecieveHit, Death, Victory, PickUp, SitDown, Defeat) give real on-screen reactions.
- Movement follows the building's nav graph (doors, halls, stairs), not straight lines through walls.

## Making the film

Click **Record a story (.webm)** in the viewer, pick this tab, and it records one whole live story
from the first frame to the ending card. Stories run 2:00 to 2:45, inside the 1 to 3 minute limit.

## Status of the pieces

- Verified: the engine sweep (variety, durations, schema), the stream protocol, a full live story in
  a real browser end to end, the animation states in screenshots.
- Not verified: the LLM policy against the real Runware API (only against a local fake server; needs
  `RUNWARE_API_KEY` and `RUNWARE_MODEL`).
- Band: `agents/band/` has the commander-to-robot delegation agents; they are not yet driven by the
  live engine.
