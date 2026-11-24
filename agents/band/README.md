# Band: Engine 9 commander → robot delegation

No-model Band agents (LangGraph) so Commander assigns Scout / Hose / Rescue in a
shared Band room — the SPEC §5 prize path. Assignment radio lines live in
[`../assignments.py`](../assignments.py) and are the same strings the orchestrator
emits into the Three.js film.

Glasser property intel (offline fixture) is appended to the Commander's first
Band message when `../tools/fixtures/apartment-3f_briefing.json` exists.

## One-time setup

### 1. Create four remote agents

In [app.band.ai](https://app.band.ai) → **Agents** → **Connect remote agent**:

| Suggested name | Description (min 10 chars) |
| --- | --- |
| `Commander` | Engine 9 IC; assigns scout, hose, rescue over Band |
| `Scout-1` | Maps rooms and finds victims; radio ack only |
| `Hose-1` | Holds stairwell / suppression; radio ack only |
| `Rescue-1` | Extracts victims; radio ack only |

Copy each **ID** and **API key** (shown once).

### 2. Write credentials

```sh
cd firefighter_builder/agents/band
cp agent_config.yaml.example agent_config.yaml
# paste the four agent_id / api_key pairs
```

`agent_config.yaml` is gitignored.

### 3. Install deps

```sh
cd firefighter_builder/agents/band
uv sync
```

No Anthropic / OpenAI key required — these agents are rule-based.

## Run the room demo

Four terminals (leave them running):

```sh
cd firefighter_builder/agents/band
uv run python commander_agent.py
uv run python scout_agent.py
uv run python hose_agent.py
uv run python rescue_agent.py
```

Then in Band:

1. **Rooms** → **New room**
2. Add Commander, Scout-1, Hose-1, Rescue-1 as participants
3. Mention Commander: `@Commander structure fire apartment-3f — deploy`

Expected chat flow:

1. Commander confirms + posts Glasser briefing (if fixture present)
2. Commander `@Scout-1` with the scout sweep assign
3. Scout-1 radio ack
4. Commander `@Hose-1` `@Rescue-1` with the hose/rescue assign
5. Hose-1 and Rescue-1 radio acks

In parallel, hit **Play** on the web app (`npm run dev` in `web/`, orchestrator on
`:8787`) for the 3D film. Film decide events use the same assign utterances.

## Glasser briefing (already wired)

Prep (paid once, ~$0.0814) from `firefighter_builder/`:

```sh
python3 -m agents.tools.glasser_briefing \
  --scenario apartment-3f \
  --address "5500 Grand Lake Dr, San Antonio, TX 78244" \
  --zip 78244 \
  --label "Harbor Court Apartments (simulated)"
```

Runtime is offline: orchestrator and Commander Band agent only `load` /
`summarize` the fixture. No live Glasser calls during Play.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Config file not found` | Run from `agents/band/` where `agent_config.yaml` lives |
| Agent online but silent | Message must **@mention** that agent; agent must be a room participant |
| Commander cannot find robots | Agents must be contacts/peers of Commander on Band; names should contain `scout` / `hose` / `rescue` |
| `UnauthorizedError` | Regenerate API key in Band and update `agent_config.yaml` |
