"""Send a run's events to the event API (SPEC.md section 1.2). Stdlib only.

    export FF_API_URL=http://<alb-url>      # from the CDK stack output
    export FF_API_TOKEN=<token>             # from Secrets Manager, see infra/README.md

The API assigns seq numbers in the order events are sent, so send them in order.
"""

import json
import os
import urllib.request

API_URL = os.environ.get("FF_API_URL", "").rstrip("/")
API_TOKEN = os.environ.get("FF_API_TOKEN", "")

EVENT_FIELDS = ("t_sim", "agent_id", "agent_role", "type", "payload", "reasoning", "confidence",
                "model", "latency_ms", "tokens_in", "tokens_out")


def enabled() -> bool:
    return bool(API_URL)


def _post(path: str, body) -> dict:
    req = urllib.request.Request(
        f"{API_URL}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read() or b"{}")


def start_run(seed: int, run_id: str | None = None, scenario_id: str = "apartment-3f", notes: str | None = None) -> str:
    body = {"seed": seed, "scenario_id": scenario_id, "notes": notes}
    if run_id:
        body["run_id"] = run_id
    return _post("/runs", body)["run_id"]


def log_events(run_id: str, events: list[dict]) -> list[int]:
    """Post events (dicts in the SPEC.md shape). Extra keys such as seq are dropped."""
    clean = [{k: e.get(k) for k in EVENT_FIELDS if k in e} for e in events]
    return _post(f"/runs/{run_id}/events", clean)["seq"]


def end_run(run_id: str) -> dict:
    """Mark the run finished. On AWS this also starts a Bruin run right away."""
    return _post(f"/runs/{run_id}/end", {})


def post_run(events: list[dict], seed: int, run_id: str, notes: str | None = None) -> str:
    """Send a whole finished run in one go: create, post all events, end."""
    run_id = start_run(seed, run_id, notes=notes)
    for i in range(0, len(events), 200):
        log_events(run_id, events[i:i + 200])
    end_run(run_id)
    return run_id


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{API_URL}{path}", headers={"Authorization": f"Bearer {API_TOKEN}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def get_learning(limit: int = 12) -> dict:
    """Recent lessons (with the human verdict on the run they came from) and the track record line."""
    return _get(f"/learning?limit={limit}")


def post_lessons(run_id: str, lessons: list[dict]) -> dict:
    keys = ("role", "lesson", "evidence", "model", "latency_ms")
    return _post(f"/runs/{run_id}/lessons", [{k: l.get(k) for k in keys} for l in lessons])
