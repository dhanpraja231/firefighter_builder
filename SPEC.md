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
agents (orchestrator) -->|  API  (FastAPI, ECS Fargate, ALB)    |--> RDS Postgres  raw.*
human approver -------->|                                      |          |
Three.js scene  <-------|  timeline, SSE, decision-log, metrics |<--+      | bruin run
                         +--------------------------------------+   |      | (ECS task: every 2 min
                                                                    |      |  and on run end)
                                                                    +-- mart.* <-+
```

Repo layout:

| Path | What lives there | Owner |
| --- | --- | --- |
| `api/` | FastAPI service, Dockerfile | Part 1 |
| `bruin/` | Bruin pipeline (`pipeline.yml`, `assets/`) and its Dockerfile | Part 1 |
| `infra/` | CDK (Python) stack for AWS | Part 1 |
| `agents/` | Orchestrator, agent prompts, persona cards, Bedrock client | Parts 2, 4, 5 |
| `scenarios/` | Scenario JSON files | Part 2 |
| `web/` | Three.js scene, decision-log panel, approval modal | Part 3 |

## 1. Data warehousing and observability

Owner: data lead (add your name).

Bruin is a CLI (`bruin run`), not a server, and its MCP server only runs locally over stdio. So agents never call Bruin.
They call our API, which writes to Postgres, and Bruin runs as a container task on ECS that transforms what is there.

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
  "model": "openai.gpt-oss-120b-1:0",
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
| `act` | robots, victims | Did `payload.action` on `payload.target`. If `risky` is true, it only runs after approval. |
| `request_approval` | commander or a robot | Asks the human to approve a risky `act`. The pending `act` follows only if approved. |
| `approval` | `human` | `payload.action` is `approve`, `deny` or `timeout_default`, and `payload.approval_of_seq` points at the request |
| `world_event` | `director` or the sim | Fire spread, collapse, power loss, twist triggered. Details in `payload.world`. |
| `status` | sim | Victim state change in `payload.victim_status`: `trapped`, `found`, `moving`, `rescued`, `lost` |

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
| `GET /health` | DB check | ALB |

The orchestrator waits on approvals by polling `GET /approvals` once per tick. If the human does not answer within the
timeout (default 15 s wall clock), the orchestrator writes `approval` with `timeout_default` and applies the role's
default (usually deny).

### 1.3 Postgres

RDS Postgres. Three schemas.

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

Approvals are `approval` events in `raw.events`, so there is no separate approvals table.

`staging` and `mart` are owned by Bruin.

### 1.4 Bruin pipeline

`bruin/` holds `pipeline.yml`, `assets/`, and a Dockerfile based on `ghcr.io/bruin-data/bruin`. `.bruin.yml` (the
connection config) is never committed. In AWS it comes from Secrets Manager; locally each person keeps their own.

Assets (all `pg.sql`, materialized as tables):

| Asset | Depends on | Contents |
| --- | --- | --- |
| `staging.events` | `raw.events` | Typed columns from `payload`: `action`, `target`, `risky`, `utterance`, `approval_of_seq`, `victim_status`, `floor`, `x`, `y`, `z` |
| `mart.decision_log` | `staging.events` | One row per `decide`, `act`, `request_approval`: agent, role, action, target, reasoning, confidence, and for risky acts the approval outcome and how long the human took |
| `mart.agent_metrics` | `staging.events` | Per run and agent: decision count, avg and p95 LLM latency, tokens, approvals requested, approved, denied |
| `mart.victim_outcomes` | `staging.events` | Per run and victim: time found, time rescued, final status, which robot rescued them |
| `mart.run_summary` | all of the above | Per run: seed, twists triggered, victims rescued and lost, sim duration, approvals, ending label |

Quality checks:

- `not_null` on `run_id`, `seq`, `agent_id` in every asset.
- `accepted_values` on `agent_role` and `type` (the enums above).
- Custom, blocking: every `act` with `risky = true` has a matching `approval` with `approve`.
- Custom, blocking: `seq` has no gaps within a run.
- Custom, non-blocking: every `decide` and `act` from an LLM has non-empty `reasoning`.

CI: GitHub Actions runs `bruin validate bruin/` using `bruin-data/setup-bruin`.

### 1.5 AWS deployment

CDK (Python), one stack, region us-east-1 (same region as the Bedrock models we tested).

- VPC with two public subnets and no NAT gateway. Fargate tasks get public IPs.
- Security groups: internet to ALB on 80, ALB to API on 8000, API and Bruin tasks to RDS on 5432.
- RDS Postgres, `db.t4g.micro`, 20 GB, credentials generated into Secrets Manager.
- ECR repositories `api` and `bruin`.
- ECS cluster:
  - API service: 1 Fargate task (0.5 vCPU, 1 GB) behind an ALB, logs to CloudWatch.
  - Bruin task definition: entrypoint reads the `.bruin.yml` secret, then runs
    `bruin run . --environment production`, logs to CloudWatch.
- EventBridge Scheduler: runs the Bruin task every 2 minutes during the demo window. Disable after the event.
- IAM:
  - API task role: `ecs:RunTask` on the Bruin task definition, `iam:PassRole` for the Bruin roles only.
  - Orchestrator (runs on a laptop or as another task): `bedrock:InvokeModel` and `bedrock:Converse` on the chosen model.
- Outputs: ALB URL, DB endpoint, secret ARNs.

Deploy: `aws login`, then `cdk bootstrap` once, then `cdk deploy`. Build and push images with a `make push` target.

### 1.6 Observability

- CloudWatch Logs for the API and every Bruin run.
- `mart.agent_metrics` is the agent-level view: LLM latency, token use, approval rate per agent.
- Optional (Telem prize): wrap each Bedrock call in a Telem trace span with `run_id`, `agent_id` and `seq` attributes so
  traces and decision-log rows join on `seq`.

## 2. Initial story

Owner: TBD.

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
    {"id": "stair-collapse", "trigger": "after t_sim 60 if any robot on floor 2"},
    {"id": "backdraft", "trigger": "when door to a burning room is opened"},
    {"id": "power-loss", "trigger": "random after t_sim 40"},
    {"id": "victim-moves", "trigger": "when a panicked victim hears fire nearby"}
  ]
}
```

Scope:

- One building, 2 or 3 floors, enough rooms for robots to split up.
- A story premise of a few sentences that the Director agent gets as context.
- 4 to 6 twists with clear trigger rules. The Director decides which fire at runtime, using the seed and current state,
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

Output: `agents/personas/<name>.json`, one per victim, at least 3.

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
- Mix personalities so the robots have to adapt: panicked and moving, injured and immobile, stubborn and arguing.
- Optional (Runware prize): generate a portrait per persona for the decision-log panel.

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

- System prompt with goal and personality (for example, a cautious scout and an impatient rescue robot).
- Observation shape: own position, visible rooms, heat readings, known victims, last N messages, task from commander.
- Output format: strict JSON matching the event schema (`type`, `payload`, `reasoning`, `confidence`).
- Memory: short running notes kept by the orchestrator and fed back each tick.
- Default action if the human times out.

LLM: an open-weight model on Bedrock through the Converse API. The model id is one setting in `agents/config.py` so we
can swap it. No sponsor offers free LLM credits, so keep prompts short and one call per agent per tick.

Optional (BAND prize): use BAND for commander-to-robot task delegation instead of plain function calls.

## 6. Schedule and owners

| Time | Part 1 (data) | Parts 2, 4, 5 (agents and story) | Part 3 (3D) |
| --- | --- | --- | --- |
| 11:30 to 1:00 | Event schema frozen, API running locally, CDK deployed | Scenario JSON draft, role prompts, persona cards | Load scenario JSON, place static models |
| 2:00 to 4:00 | Bruin assets and checks, schedule on ECS | Orchestrator posting events to the deployed API | Timeline replay, approval modal |
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
| Bruin (mandatory) | Part 1 pipeline on ECS |
| AdaL demo video | Section 6, last hour |
| Public GitHub repo before 6:00 PM | Section 6 |
| Bonus: 3D | Part 3 |
| Bonus: agent memory, adaptive behavior | Parts 4 and 5 memory fields |
| Bonus: voice | Optional TTS on `speak` events if time allows |

## 8. Open questions

- Bedrock model: confirmed `openai.gpt-oss-120b-1:0` works on demand in us-east-1 (about 0.4 s for a short reply). Fallbacks: `openai.gpt-oss-20b-1:0`, `qwen.qwen3-32b-v1:0`.
- Who owns parts 2, 4 and 5.
- Live SSE or replay only for the recorded film. Replay is safer for recording.
- Whether the human approver is a teammate clicking live during recording, or scripted approvals for a repeatable take.
