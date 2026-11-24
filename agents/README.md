# agents

The autonomous story engine, role prompts (`roles/`), persona cards (`personas/`). See SPEC.md sections 4
and 5, and [`../LIVE_STORY.md`](../LIVE_STORY.md) for how a story is made and streamed.

**The agents decide the plot.** Nothing is scripted: every agent (commander, scout, hose, rescue, eight
residents, the director, the human approver stand-in) chooses its own action each time it has something
to decide, against a live fire simulation.

| File | What it is |
| --- | --- |
| `engine.py` | `iter_run(seed, ...)` yields events the moment agents decide them; `build_run` drains it |
| `world.py` | the map, doors, stairs, and the fire/smoke model |
| `policy.py` | heuristic (offline) policies with seeded personality rolls |
| `llm.py` | LLM policy for an OpenAI-compatible endpoint (Runware); falls back to heuristic on any error |
| `sim_core.py`, `sim_options.py`, `sim_actions.py` | simulation loop, the options each agent can choose from, and their effects |
| `server.py` | `GET /stream` (live, Server-Sent Events), `GET /run` (whole run), `GET /memory` |
| `orchestrator.py` | CLI and SQL output (`--seed`, `--json`, `--postgres`, `--policy`, `--live`) |
| `sweep.py`, `test_stream.py`, `test_llm_stub.py` | variety sweep over many seeds, stream protocol test, LLM fallback test |

```sh
python agents/server.py                      # story server on :8787 for the web viewer
python agents/orchestrator.py --seed 3 --policy heuristic --no-sql --json run.json
python agents/sweep.py                       # variety / duration / validity over many seeds
RUNWARE_API_KEY=... RUNWARE_MODEL=... python agents/server.py   # LLM agents instead of the heuristic
```

- **Glasser briefing** (offline RentCast fixture): [`tools/glasser_briefing.py`](tools/glasser_briefing.py) — fed into Commander `decide` reasoning.
- **Band delegation** (commander → robots in a Band room): [`band/README.md`](band/README.md).
- Shared radio lines: [`assignments.py`](assignments.py).
