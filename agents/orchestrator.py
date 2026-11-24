"""Firefighter Robots orchestrator (thin wrapper around the story engine).

The plot is NOT scripted here. engine.py runs a discrete-event simulation in which a commander, scout,
hose and rescue robot, eight residents, a Director and a human approver each make their own decisions
through a Policy (policy.py heuristic stand-in, or llm.py when RUNWARE_API_KEY/RUNWARE_MODEL are set).

    python3 agents/orchestrator.py --seed 1 | psql "$DATABASE_URL"
    python3 agents/orchestrator.py --seed 1 --json web/public/runs/seed-1.json --no-sql
    python3 agents/orchestrator.py --seed 1 --policy heuristic
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine import DEFAULT_MEMORY, run_story  # noqa: E402

MEMORY_PATH = Path(__file__).parent / "memory.json"
DEFAULT_SCENARIO = "apartment-3f"


def load_memory() -> dict:
    if MEMORY_PATH.exists():
        try:
            return {**DEFAULT_MEMORY, **json.loads(MEMORY_PATH.read_text())}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_MEMORY)


def save_memory(memory: dict) -> None:
    MEMORY_PATH.write_text(json.dumps(memory, indent=2))


def default_policy() -> str:
    return "llm" if (os.environ.get("RUNWARE_API_KEY") and os.environ.get("RUNWARE_MODEL")) else "heuristic"


def build_story(seed: int, memory: dict | None = None, policy: str | None = None) -> dict:
    """Runs one story. Loads/updates/saves agents/memory.json itself unless `memory` is passed in."""
    owns = memory is None
    if owns:
        memory = load_memory()
    result = run_story(seed, memory, policy or default_policy())
    if owns:
        save_memory(result["memory"])
    return result


def build_run(seed: int, memory: dict | None = None):
    """Back-compat for server.py: (events, memory, run_id)."""
    r = build_story(seed, memory)
    return r["events"], r["memory"], r["run_id"]


# -- output: SQL (same contract as db/fake_run.py) and/or JSON -------------

def sql_str(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def build_sql(events, seed, run_id, scenario_id=DEFAULT_SCENARIO) -> str:
    started = datetime.now(timezone.utc).replace(microsecond=0)
    ended = started + timedelta(seconds=events[-1]["t_sim"] + 5)
    lines = ["begin;", f"delete from raw.events where run_id = '{run_id}';", f"delete from raw.runs where run_id = '{run_id}';"]
    lines.append(
        "insert into raw.runs (run_id, seed, scenario_id, notes, started_at, ended_at) values "
        f"('{run_id}', {seed}, {sql_str(scenario_id)}, 'orchestrator run (agent-driven story engine)', "
        f"'{started.isoformat()}', '{ended.isoformat()}');"
    )
    for e in events:
        received = started + timedelta(seconds=e["t_sim"])
        lines.append(
            "insert into raw.events (run_id, seq, t_sim, agent_id, agent_role, type, payload, reasoning, "
            "confidence, model, latency_ms, tokens_in, tokens_out, received_at) values ("
            f"'{run_id}', {e['seq']}, {e['t_sim']}, {sql_str(e['agent_id'])}, {sql_str(e['agent_role'])}, "
            f"{sql_str(e['type'])}, {sql_str(json.dumps(e['payload']))}::jsonb, {sql_str(e['reasoning'])}, "
            f"{sql_str(e['confidence'])}, {sql_str(e['model'])}, {sql_str(e.get('latency_ms'))}, "
            f"{sql_str(e.get('tokens_in'))}, {sql_str(e.get('tokens_out'))}, '{received.isoformat()}');"
        )
    lines.append("commit;")
    return "\n".join(lines)


def print_sql(events, seed, run_id=None, scenario_id=DEFAULT_SCENARIO):
    run_id = run_id or str(uuid.uuid4())
    print(build_sql(events, seed, run_id, scenario_id))
    return run_id


def write_to_postgres(sql_text: str, container: str = "ff-pg", db: str = "firefighter", user: str = "postgres") -> None:
    """Pipes SQL into the local Bruin Postgres container via `docker exec` (only Docker needed on the host)."""
    import subprocess

    result = subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-U", user, "-d", db],
        input=sql_text.encode(), capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql exited {result.returncode}: {result.stderr.decode()[-800:]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--json", type=str, default=None, help="also write the run as JSON here (for the web app)")
    parser.add_argument("--no-sql", action="store_true", help="skip printing SQL to stdout")
    parser.add_argument("--postgres", action="store_true", help="also write straight into the local ff-pg container")
    parser.add_argument("--live", action="store_true", help="play the story in real time, printing each event as JSON lines")
    parser.add_argument("--speed", type=float, default=1.0, help="with --live: wall-clock speed-up")
    parser.add_argument("--policy", choices=("heuristic", "llm"), default=None,
                        help="agent brains (default: llm if RUNWARE_API_KEY and RUNWARE_MODEL are set, else heuristic)")
    args = parser.parse_args()

    if args.live:
        import time
        from engine import iter_run
        run = iter_run(args.seed, load_memory(), args.policy or default_policy())
        t0 = time.monotonic()
        for ev in run:
            wait = (ev['t_sim'] - 4.0) / args.speed - (time.monotonic() - t0)
            if wait > 0:
                time.sleep(wait)
            print(json.dumps(ev), flush=True)
        save_memory(run.memory)
        print(f"ending={run.result['ending']} policy={run.result['policy']}", file=sys.stderr)
        return

    r = build_story(args.seed, policy=args.policy)
    events, memory, run_id = r["events"], r["memory"], r["run_id"]

    if not args.no_sql or args.postgres:
        sql_text = build_sql(events, args.seed, run_id)
        if not args.no_sql:
            print(sql_text)
        if args.postgres:
            write_to_postgres(sql_text)
            print(f"wrote run {run_id} to postgres (ff-pg/firefighter)", file=sys.stderr)

    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({
            "seed": args.seed, "run_id": run_id, "run_number": memory["runs"], "memory": memory,
            "ending": r["ending"], "policy": r["policy"], "stats": r["stats"], "events": events,
        }, indent=2))
        print(f"wrote {len(events)} events to {out_path} (run #{memory['runs']}, ending={r['ending']}, policy={r['policy']})", file=sys.stderr)


if __name__ == "__main__":
    main()
