# Firefighter Robots: spec

Multiplayer AI Hackathon, Track 1 (agent animated film). Submission: public GitHub repo and demo before 6:00 PM, 2026-11-23.

Robots fight a fire in a multi-floor building. AI agents (robots, a commander, victims and a story director) decide what
happens. A human on the loop approves or denies risky actions. The film is a 1 to 3 minute recording of a Three.js 3D
simulation. Every decision is logged, and Bruin turns the logs into the decision log and run metrics shown on screen.

Different seeds, different twists and different human approvals give different endings.

## Contents

- [0. Overview and run flow](#0-overview-and-run-flow)
- [1. Data warehousing and observability](#1-data-warehousing-and-observability)
- [2. Initial story](#2-initial-story)
- [3. Scene modelling](#3-scene-modelling)
- [4. Victim personalities](#4-victim-personalities)
- [5. Firefighter agent roles](#5-firefighter-agent-roles)
- [6. Schedule and owners](#6-schedule-and-owners)
- [7. Requirements checklist](#7-requirements-checklist)
- [8. Open questions](#8-open-questions)

## 0. Overview and run flow

1. `POST /runs` with a seed and a scenario id. The API returns a `run_id`.
2. The Director agent reads the scenario and the seed and picks which twists are in play.
3. The orchestrator runs a tick loop (one tick = 1 s of sim time). Each tick, every agent gets an observation, calls the
   LLM, and returns one action.
4. Actions marked risky are not executed until the human approves them (or the timeout default kicks in).
5. Every observation result, decision and world change is POSTed to the API as an event.
6. The Three.js scene plays the event timeline (live over SSE, or replayed from the start).
7. Bruin runs every 2 minutes and at run end, building `mart.*` tables from the raw events.
8. The scene's side panel shows the decision log and metrics from `mart.*`.
9. We record one or more runs and cut the film and demo video in AdaL.

```
                         +--------------------------------------+
agents (orchestrator) -->|  API + dashboard (FastAPI, :8010)    |--> Postgres (Docker)  raw.*
human approver -------->|                                      |          |
Three.js scene  <-------|  timeline, SSE, decision-log, metrics |<--+      | bruin run
                         +--------------------------------------+   |      | (run by the API: every 2 min
                                                                    |      |  and on run end)
                                                                    +-- mart.* <-+
```

Repo layout:

| Path | What lives there | Owner |
| --- | --- | --- |
| `api/` | Event API and dashboard (FastAPI) | Part 1 |
| `bruin/` | Bruin pipeline (`pipeline.yml`, `assets/`) and its Dockerfile | Part 1 |
| `infra/` | How to run everything locally | Part 1 |
| `agents/` | Orchestrator, agent prompts, persona cards, Runware LLM client (`llm.py`), event API client (`api_client.py`) | Parts 2, 4, 5 |
| `story/` | Story outline, characters, twists, beats | Part 2 |
| `scenarios/` | Scenario JSON files | Part 2 |
| `web/` | Three.js scene, decision-log panel, approval modal | Part 3 |

## 1. Data warehousing and observability

Owner: data lead (add your name).

Bruin is a CLI (`bruin run`), not a server, and its MCP server only runs locally over stdio. So agents never call Bruin.
They call our API, which writes to Postgres, and the API runs Bruin to transform what is there.

### 1.1 Event schema

This is the one contract every part writes to or reads from. Field names are fixed. Add new keys inside `payload` only.

```json
{
  "run_id": "6f1c...",
  "seq": 42,
  "t_sim": 37.0,
  "agent_id": "rescue-1",
  "agent_role": "rescue",
  "type": "act",
  "payload": {
    "position": {"x": 4.0, "y": 6.0, "z": 2.5, "floor": 2},
    "target": "victim-3",
    "action": "breach_door",
    "risky": true,
    "utterance": "Breaching door 2B, victim behind it.",
    "approval_of_seq": null,
    "victim_status": null,
    "world": null
  },
  "reasoning": "Victim 3 has stopped responding and smoke in 2B is rising.",
  "confidence": 0.7,
  "model": "google:gemma@4-31b",
  "latency_ms": 820,
  "tokens_in": 900,
  "tokens_out": 120
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `run_id` | uuid | From `POST /runs` |
| `seq` | int | Assigned by the API, gap-free per run, starts at 1. Clients do not send it. |
| `t_sim` | float | Sim seconds since run start |
| `agent_id` | string | Unique in the run: `scout-1`, `suppression-1`, `rescue-1`, `commander`, `victim-1`, `director`, `human` |
| `agent_role` | enum | `scout`, `suppression`, `rescue`, `commander`, `victim`, `director`, `human` |
| `type` | enum | See below |
| `payload` | object | See below |
| `reasoning` | string or null | Why the agent chose this. Required for `decide`, `act`, `request_approval`. |
| `confidence` | float or null | 0 to 1, self-reported by the agent |
| `model`, `latency_ms`, `tokens_in`, `tokens_out` | | Filled by the orchestrator on events that came from an LLM call, null otherwise |

Event types:

| `type` | Sent by | Meaning |
| --- | --- | --- |
| `move` | any agent | Moved to `payload.position` |
| `speak` | any agent | Said `payload.utterance` (shown as a speech bubble, optionally voiced) |
| `decide` | robots, commander, victims | Chose a plan without acting yet (for example, task assignment) |
| `act` | robots, victims | Did `payload.action` on `payload.target`. If `risky` is true, it must carry `approval_of_seq` (the request's `seq`) and only runs after approval. |
| `request_approval` | commander or a robot | Asks the human to approve a risky action. `payload.action` and `payload.target` are the proposed action, `payload.actor` is the robot that will do it. |
| `approval` | `human` | `payload.action` is `approve`, `deny` or `timeout_default`, and `payload.approval_of_seq` points at the request |
| `world_event` | `director` or the sim | `payload.world.kind` is `fire_start`, `fire_spread` or `twist`. Twists also set `payload.world.twist` to the twist id from the scenario. |
| `status` | sim | Victim state change. `agent_id` is the victim, `payload.victim_status` is `trapped`, `found`, `moving`, `rescued` or `lost`, `payload.target` is the robot involved. |

The approval chain, as the Bruin checks expect it:

```
seq 9   commander  request_approval  {action: breach_door, target: d-2B, actor: rescue-1}
seq 10  human      approval          {action: approve, approval_of_seq: 9}
seq 11  rescue-1   act               {action: breach_door, target: d-2B, risky: true, approval_of_seq: 9}
```

A risky `act` without an approved request fails a blocking check, and the marts stop updating until it is fixed.

Coordinates: meters, y-up, origin at the building's south-west corner on the ground floor, floor height 3 m
(`y = floor * 3`). Part 2 and part 3 both use this.

### 1.2 API

FastAPI, one container, JSON in and out. CORS open for the demo. A shared bearer token (`API_TOKEN`) on write routes.

| Method and path | Purpose | Used by |
| --- | --- | --- |
| `POST /runs` | Body `{seed, scenario_id, notes}`. Creates a run, returns `{run_id}`. | Orchestrator |
| `POST /runs/{id}/events` | Body is a list of events (no `seq`). Inserts in order, returns assigned `seq` values. | Orchestrator |
| `GET /runs/{id}/timeline?since_seq=0` | Events after `since_seq`, ordered by `seq` | Three.js replay |
| `GET /runs/{id}/stream` | Server-sent events, one message per new event | Three.js live |
| `GET /runs/{id}/approvals?status=pending` | Open approval requests | Approval modal, orchestrator |
| `POST /runs/{id}/approvals/{seq}` | Body `{decision: "approve" or "deny", note}`. Writes an `approval` event. | Approval modal |
| `GET /runs/{id}/decision-log` | Rows from `mart.decision_log` | Side panel |
| `GET /runs/{id}/metrics` | Rows from `mart.agent_metrics` and `mart.victim_outcomes` | Side panel |
| `GET /runs/compare` | Rows from `mart.run_summary` | End card of the film |
| `POST /runs/{id}/end` | Marks the run finished, starts the Bruin task with `ecs:RunTask` | Orchestrator |
| `GET /health` | DB check | Dashboard, scripts |

The orchestrator waits on approvals by polling `GET /approvals` once per tick. If the human does not answer within the
timeout (default 15 s wall clock), the orchestrator writes `approval` with `timeout_default` and applies the role's
default (usually deny).

### 1.3 Postgres

Postgres (local Docker container). Three schemas.

`raw` (written only by the API):

```sql
create table raw.runs (
  run_id uuid primary key,
  seed int not null,
  scenario_id text not null,
  notes text,
  started_at timestamptz not null default now(),
  ended_at timestamptz
);

create table raw.events (
  run_id uuid not null references raw.runs,
  seq int not null,
  t_sim real not null,
  agent_id text not null,
  agent_role text not null,
  type text not null,
  payload jsonb not null default '{}',
  reasoning text,
  confidence real,
  model text,
  latency_ms int,
  tokens_in int,
  tokens_out int,
  received_at timestamptz not null default now(),
  primary key (run_id, seq)
);
```

Approvals are `approval` events in `raw.events`, so there is no separate approvals table. The DDL lives in
`db/schema.sql`. `db/fake_run.py --seed N` prints SQL for one fake run, for testing and as sample data for the 3D scene.

`staging` and `mart` are owned by Bruin.

### 1.4 Bruin pipeline

`bruin/` holds `pipeline.yml`, `assets/`, `config.production.yml` and a Dockerfile based on
`ghcr.io/bruin-data/bruin:v0.11.832`. Locally, each person copies `.bruin.example.yml` to `.bruin.yml` (gitignored).
On ECS, `config.production.yml` reads the DB host and credentials from env vars that ECS injects from Secrets Manager.
See `bruin/README.md` for commands.

Assets (all `pg.sql`, materialized as tables):

| Asset | Depends on | Contents |
| --- | --- | --- |
| `staging.events` | `raw.events` | Typed columns from `payload`: `action`, `target`, `risky`, `utterance`, `approval_of_seq`, `victim_status`, `floor`, `x`, `y`, `z` |
| `mart.decision_log` | `staging.events` | One row per `decide`, `act`, `request_approval`: agent, role, action, target, reasoning, confidence, and for risky acts the approval outcome and how long the human took |
| `mart.agent_metrics` | `staging.events` | Per run and agent: decision count, avg and p95 LLM latency, tokens, approvals requested, approved, denied |
| `mart.victim_outcomes` | `staging.events` | Per run and victim: time found, time rescued, final status, which robot rescued them |
| `mart.run_summary` | all of the above | Per run: seed, twists triggered, victims rescued and lost, sim duration, approvals, ending (`everyone saved`, `some saved`, `no one saved`, `in progress`) |

Quality checks:

- `not_null` on `run_id`, `seq`, `agent_id` in every asset.
- `accepted_values` on `agent_role` and `type` (the enums above).
- Custom, blocking: every `act` with `risky = true` has a matching `approval` with `approve`.
- Custom, blocking: `seq` has no gaps within a run.
- Custom, non-blocking: every `decide` and `act` from an LLM has non-empty `reasoning`.
- One row per key in `mart.agent_metrics` and `mart.run_summary`, `accepted_values` on victim status and ending.

CI: GitHub Actions runs `bruin validate bruin/` using `bruin-data/setup-bruin`.

### 1.5 Deployment

Local, on one laptop. Commands are in `infra/README.md`.

- Postgres 17 in Docker (`ff-pg`, port 5433).
- Event API and dashboard (`api/`, FastAPI, port 8010). On startup it applies `db/schema.sql`. It runs
  `bruin run bruin/` every 2 minutes, when a run ends (`POST /runs/{id}/end`) and from the dashboard's
  "Run Bruin now" button.
- Agents (`agents/`) call Runware for the LLM and post events to the API.

An AWS version (RDS, ECS Fargate, ALB, EventBridge) was built and torn down the same day. `bruin/Dockerfile` and
`bruin/config.production.yml` are left from it.

### 1.6 Observability

- The dashboard at `/` shows whether Postgres and Bruin are healthy, the live event feed, the decision log, agent
  metrics (LLM calls, latency, tokens) and victim outcomes.
- `mart.agent_metrics` is the agent-level view: LLM latency, token use, approval rate per agent.
- Optional (Telem prize): wrap each Runware call in a Telem trace span with `run_id`, `agent_id` and `seq` attributes so
  traces and decision-log rows join on `seq`.

## 2. Initial story

Owner: TBD. The full story (characters, twists, beats) is in [story/README.md](story/README.md). This section is the summary plus the scenario file format.

### Story outline

- **Setting:** a 3-floor apartment block at night. The fire starts in a kitchen on floor 3.
- **Style:** documentary. It should feel like an incident replay: bodycam and drone shots, on-screen captions with
  timestamps, agent names and decisions, and no music-video drama.
- **Cast:** 3 robots and an AI commander (section 5), and 6 victim units, 8 people in all (section 4).
- **Twists the Director can use:**
  - **Stairwell collapse:** cuts off a route mid-rescue.
  - **Child goes missing:** the child slips away from the parent.
- **Ending:** open. The agents decide, so a run can end with everyone saved, some saved or no one saved. A human
  approves or declines the overall outcome of each run. The verdict and the commander's lessons feed the next run (section 4b).
- **Beats (roughly 2 minutes):**
  1. Alarm, the fire starts, the robots arrive, the commander assigns floors.
  2. The scout sweeps floors 2 and 3 and finds victims. Each one reacts in character.
  3. Rescues are under way and the victims complicate them: the elderly person won't leave, the skeptic argues, the
     teen keeps filming.
  4. The Director triggers a twist.
  5. The robots re-plan. Some victims get out, some may not.
  6. End card with who was saved, the key decisions, and the human's verdict.

### Scenario file

Output: `scenarios/<scenario_id>.json`. The orchestrator loads it at run start and the Three.js scene loads the same
file for geometry.

```json
{
  "scenario_id": "apartment-3f",
  "title": "Third-floor kitchen fire",
  "floors": 3,
  "rooms": [
    {"id": "2B", "floor": 2, "rect": {"x": 0, "z": 0, "w": 6, "d": 5}, "kind": "apartment"}
  ],
  "doors": [{"id": "d-2B", "between": ["2B", "hall-2"], "x": 6, "z": 2.5, "floor": 2, "locked": true}],
  "stairs": [{"id": "stair-east", "x": 18, "z": 1, "floors": [0, 1, 2]}],
  "fire": {"origin_room": "3A", "spread_per_tick": 0.05},
  "robots": [{"agent_id": "scout-1", "role": "scout", "start": {"x": 1, "y": 0, "z": -2}}],
  "victims": [{"agent_id": "victim-1", "persona": "personas/elderly-resident.json", "room": "2B"}],
  "twists": [
    {"id": "stair-collapse", "trigger": "after t_sim 60 if any robot is on floor 2 or 3"},
    {"id": "child-missing", "trigger": "after the parent and child are found, before they reach the exit"}
  ]
}
```

Scope:

- One building, 2 or 3 floors, enough rooms for robots to split up.
- A story premise of a few sentences that the Director agent gets as context.
- The 2 twists above, with clear trigger rules. The Director decides which fire at runtime, using the seed and current state,
  and logs each one as a `world_event` with its reasoning.

## 3. Scene modelling

Owner: teammates (Three.js).

Inputs:

- `scenarios/<id>.json` for walls, rooms, doors, stairs, start positions.
- `GET /runs/{id}/timeline` (replay) or `GET /runs/{id}/stream` (live) for everything that moves.
- `GET /runs/{id}/decision-log` and `/metrics` for the side panel.

Must show:

- Robots and victims as distinct models, moving between `move` positions (interpolate over the tick).
- Fire and smoke growing per `world_event`.
- Speech bubbles for `speak`.
- A decision-log panel: agent, action, one line of reasoning, approval result.
- An approval modal when a `request_approval` arrives: shows the action and reasoning, buttons call
  `POST /runs/{id}/approvals/{seq}`.
- Camera moves that suit a film (follow the agent in the current event, cut on twists).

Output: the film is a screen recording of a replayed run, so replay must play cleanly from `seq = 1` at 1x and 2x.

## 4. Victim personalities

Owner: TBD.

Output: `agents/personas/<name>.json`, one per victim unit (pairs share one file with two people listed).

Cast (6 units, 8 people):

| Unit | Who | What makes them hard to rescue |
| --- | --- | --- |
| `victim-elderly` | Stubborn elderly resident | Won't leave without their pet |
| `victim-parent`, `victim-child` | Panicked parent and young child | Parent runs the wrong way, and the child can go missing (twist) |
| `victim-skeptic` | Resident who distrusts robots | Refuses help from a machine and argues with it |
| `victim-teen` | Teen filming on their phone | Won't leave, streaming the fire live |
| `victim-regular` | Regular resident | Cooperative, follows instructions. A baseline to compare with the others. |
| `victim-couple-a`, `victim-couple-b` | A normal couple | Want to stay together. Splitting them slows things down. |

Pairs are separate agents (each has its own `agent_id` and memory) but start in the same room and try to stay together.

```json
{
  "agent_id": "victim-1",
  "name": "Mrs. Okafor",
  "age": 78,
  "mobility": "walker",
  "temperament": "calm but stubborn",
  "goal": "will not leave without her cat",
  "fears": ["stairs", "loud machines"],
  "compliance": "follows a robot only after it agrees to look for the cat",
  "voice": "slow, polite",
  "memory": []
}
```

Behavior:

- Victims are agents too. Each tick they get what they can see and hear and choose `speak`, `move` or `act`
  (open door, hide, follow robot).
- `memory` grows during the run (what they saw, what robots told them) and is passed back in the next prompt.
- The cast above is the mix. The robots have to adapt to each one.
- Optional (Runware prize): generate a portrait per persona for the decision-log panel.

## 4b. Sim rules, decisions and learning

`agents/sim.py` runs the world on a 1 s tick, so agents can lose. All rates are in `SPREAD` and `AIR_DRAIN` at the
top of the file.

- **Fire:** starts in `3-kitchen` at 0.35, grows 0.05/s, and spreads to neighbors (12%/s), the room above (20%/s) and
  rarely the room below. Smoke spreads from burning rooms and rises up the stair core.
- **Victims:** each has 100 air, drained by smoke and fire in their room. At 0 they are `lost` (`payload.cause`:
  `air` or `fire`).
- **Deadline:** at 150 s the building is unsafe and everyone still inside is lost (`cause: collapse`).
- **Twists:** the stairs between floors 2 and 3 can collapse at 50 to 90 s, the child can run off, and venting can
  cause a backdraft. Twist rows carry `payload.twist`.
- **Resources:** the rescue robot (one unit at a time, by the stairs) and the ladder truck (one window at a time,
  floors 1 to 4, about 24 s).

Decision points, where the LLM picks one listed option (or the first option without a key):

- **commander:** which found unit the rescue robot or the ladder goes for next
- **rescue-1:** how to approach a unit (options per persona, each with a time cost and side effects)
- **hose-1:** every 15 s, which room to fight, or ask the human to vent a floor

Learning: after each run the commander writes up to 5 lessons (`learn.lessons`). On the dashboard a human approves or
declines the run's outcome (`learn.verdicts`). The next run's prompts include recent lessons, with the declined
runs' lessons marked as priority fixes, and the saved-per-run track record.

## 5. Firefighter agent roles

Owner: TBD.

| Agent | Goal | Allowed actions | Risky actions (need approval) |
| --- | --- | --- | --- |
| `scout-1` (drone) | Map rooms, find victims and hot spots | `move`, `scan_room`, `report` | none |
| `suppression-1` | Contain the fire, keep exit routes open | `move`, `spray`, `close_door`, `vent` | `vent` near a closed burning room (backdraft risk) |
| `rescue-1` | Reach and extract victims | `move`, `open_door`, `carry`, `guide`, `speak` | `breach_door`, entering a floor flagged unstable |
| `commander` | Assign tasks, decide priorities, ask the human | `assign`, `request_approval`, `speak` | none (it asks on behalf of robots) |
| `human` | Approve or deny risky actions | `approve`, `deny` | |

For each role, `agents/roles/<role>.md` holds:

- System prompt with goal. All robots and the commander share one calm, professional, procedural voice (radio-style
  call-outs). What varies between them is their job, not their personality.
- Observation shape: own position, visible rooms, heat readings, known victims, last N messages, task from commander.
- Output format: strict JSON matching the event schema (`type`, `payload`, `reasoning`, `confidence`).
- Memory: short running notes kept by the orchestrator and fed back each tick.
- Default action if the human times out.

LLM: `google:gemma@4-31b` (open-weight) on Runware, through its OpenAI-compatible `/v1/chat/completions` endpoint. `agents/llm.py` makes the calls and fills `model`, `latency_ms`, `tokens_in` and `tokens_out` on each event from the response's `usage`. The key is `RUNWARE_API_KEY` in the repo's gitignored `.env`, never committed.

Optional (BAND prize): use BAND for commander-to-robot task delegation instead of plain function calls.

## 6. Schedule and owners

| Time | Part 1 (data) | Parts 2, 4, 5 (agents and story) | Part 3 (3D) |
| --- | --- | --- | --- |
| 11:30 to 1:00 | Event schema frozen, API running locally, CDK deployed | Scenario JSON draft, role prompts, persona cards | Load scenario JSON, place static models |
| 2:00 to 4:00 | Bruin assets and checks, run by the API | Orchestrator posting events to the deployed API | Timeline replay, approval modal |
| 4:00 to 5:00 | Decision-log and metrics endpoints, run compare | Several runs with different seeds | Decision-log panel, camera work |
| 5:00 to 5:45 | Disable schedule after final runs | Pick the best run | Record film, AdaL demo video |
| 5:45 | Push public repo, submit | | |

## 7. Requirements checklist

| Requirement | Covered by |
| --- | --- |
| At least 3 AI agents with distinct roles and personalities | Part 5 (4 robot-side agents), part 4 (3+ victims), Director |
| Visual characters | Part 3 |
| Animated video or simulation with visible movement and interaction | Part 3, driven by part 1 timeline |
| Decision log of what agents decided and why | `mart.decision_log` (part 1), panel in part 3 |
| Different runs produce different outcomes | Seeds, Director twists, human approvals; shown with `GET /runs/compare` |
| Bruin (mandatory) | Part 1 pipeline, run by the API |
| AdaL demo video | Section 6, last hour |
| Public GitHub repo before 6:00 PM | Section 6 |
| Bonus: 3D | Part 3 |
| Bonus: agent memory, adaptive behavior | Parts 4 and 5 memory fields, later the outcome-verdict self-improvement loop |
| Bonus: voice | Optional TTS on `speak` events if time allows |

## 8. Open questions

- LLM: Runware `google:gemma@4-31b`, about 0.7 s for a short reply and about 1.8 s for an agent decision.
- Who owns parts 2, 4 and 5.
- Live SSE or replay only for the recorded film. Replay is safer for recording.
- Whether the human approver is a teammate clicking live during recording, or scripted approvals for a repeatable take.
