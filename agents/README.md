# agents

Orchestrator, tick-based sim (sim.py), role prompts (roles/), persona cards (personas/), Runware LLM client (llm.py), event API client (api_client.py). See SPEC.md sections 4, 4b and 5.

- **Glasser briefing** (offline RentCast fixture): [`tools/glasser_briefing.py`](tools/glasser_briefing.py). Fed into every Commander decision prompt and the opening assignment.
- **Band delegation** (commander to robots in a Band room): [`band/README.md`](band/README.md).
- Shared radio lines: [`assignments.py`](assignments.py), used by the Band agents and the sim's opening assignment.
