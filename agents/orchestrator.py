"""Firefighter Robots orchestrator.

Builds one run with the tick-based sim in agents/sim.py: fire spreads on its
own clock, victims lose air, the building collapses at a deadline, and the
agents' choices (commander triage, rescue approach, hose target or vent) decide
who gets out. Choices come from Runware (agents/llm.py) when a key is set, or
from a first-option rule. Lessons from earlier runs, with the human's verdict on
each run, come from the event API and go into the agents' prompts.

    python3 agents/orchestrator.py --seed 1 --no-sql                    # rule policy, prints the outcome
    FF_API_URL=http://localhost:8010 python3 agents/orchestrator.py --seed 1 --no-sql --llm --api
"""

import argparse
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODEL = "rule-based-v0"  # replaced per event by the Runware model when --llm / llm.enabled() (agents/llm.py)

FLOOR_Y = {1: 0.0, 2: 3.0, 3: 6.0, 4: 9.0, 5: 12.0}

# Room centers, local to each floor. Mirrors web/src/scene/layout.ts exactly
# (BUILDING_WIDTH=16, BUILDING_DEPTH=12, CROSS_Z=6.15, STAIR_CORE x=6..10 z=3.85..8.6)
# so positions land inside the real rooms the scene renders.
ROOM_XZ = {
    "living": (3.0, 3.075),
    "bedroom-w": (3.0, 9.075),
    "kitchen": (13.0, 3.075),
    "bedroom-e": (13.0, 9.075),
    "hall": (8.0, 1.925),
    "landing": (8.0, 10.3),
}
EXTERIOR = {
    "engine": (-5.4, 0.0, 6.0),
    "command": (-8.0, 0.0, 3.5),
    "hydrant": (-1.21, 0.0, 1.4),
    "entry": (-0.05, 0.0, 1.9),
}


def pos(floor: int, kind: str) -> dict:
    x, z = ROOM_XZ[kind]
    return {"x": x, "y": FLOOR_Y[floor], "z": z, "floor": floor - 1}


def ext(name: str) -> dict:
    x, y, z = EXTERIOR[name]
    return {"x": x, "y": y, "z": z, "floor": -1}


def room_id(floor: int, kind: str) -> str:
    return f"{floor}-{kind}"


PERSONAS_DIR = Path(__file__).parent / "personas"
MEMORY_PATH = Path(__file__).parent / "memory.json"
DEFAULT_MEMORY = {
    "runs": 0,
    "child_losses": 0,
    # Learned, not scripted: starts naive (blunt order, slow search), each
    # run that goes badly nudges these toward the gentler, more competent
    # version. This is what "the next run is better" actually is.
    "cautious_briefing": False,
    "bolt_prob": 0.55,
    "found_prob": 0.75,
}


def load_memory() -> dict:
    if MEMORY_PATH.exists():
        try:
            return {**DEFAULT_MEMORY, **json.loads(MEMORY_PATH.read_text())}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_MEMORY)


def save_memory(memory: dict) -> None:
    MEMORY_PATH.write_text(json.dumps(memory, indent=2))


def load_personas() -> dict:
    personas = {}
    for path in PERSONAS_DIR.glob("*.json"):
        data = json.loads(path.read_text())
        if "agents" in data:  # couple.json holds two agent_ids
            for entry in data["agents"]:
                personas[entry["agent_id"]] = {**data, **entry}
        else:
            personas[data["agent_id"]] = data
    return personas


class EventLog:
    def __init__(self):
        self.events = []
        self.t = 0.0

    def _push(self, agent_id, role, type_, payload=None, reasoning=None, llm=True, dt=1.0, confidence=None):
        self.t += dt
        seq = len(self.events) + 1
        self.events.append(
            {
                "seq": seq,
                "t_sim": round(self.t, 1),
                "agent_id": agent_id,
                "agent_role": role,
                "type": type_,
                "payload": payload or {},
                "reasoning": reasoning,
                "confidence": confidence,
                "model": MODEL if llm else None,
            }
        )
        return seq

    def world(self, event, reasoning, dt=1.0):
        return self._push("director", "director", "world_event", {"world": event}, reasoning, dt=dt)

    def decide(self, agent_id, role, payload, reasoning, dt=1.0):
        return self._push(agent_id, role, "decide", payload, reasoning, dt=dt)

    def move(self, agent_id, role, position, dt=1.5):
        return self._push(agent_id, role, "move", {"position": position}, None, llm=False, dt=dt)

    def act(self, agent_id, role, action, target, reasoning, risky=False, extra=None, dt=1.0):
        payload = {"action": action, "target": target, "risky": risky, **(extra or {})}
        return self._push(agent_id, role, "act", payload, reasoning, dt=dt)

    def speak(self, agent_id, role, utterance, reasoning, dt=0.5):
        return self._push(agent_id, role, "speak", {"utterance": utterance}, reasoning, dt=dt)

    def status(self, victim_id, status, helper_id, dt=0.5):
        """Victim-status events are reported by the victim about themselves
        (`agent_id` = victim, `agent_role` = "victim"), matching the
        convention `db/fake_run.py` and `bruin/assets/mart/victim_outcomes.sql`
        already assume -- `target` names whichever robot caused the change."""
        return self._push(victim_id, "victim", "status", {"victim_status": status, "target": helper_id}, None, llm=False, dt=dt)

    def request_approval(self, agent_id, role, action, target, reasoning, dt=1.0):
        return self._push(agent_id, role, "request_approval", {"action": action, "target": target}, reasoning, dt=dt)

    def approval(self, decision, of_seq, dt=None):
        return self._push(
            "human", "human", "approval", {"action": decision, "approval_of_seq": of_seq}, None, llm=False,
            dt=dt if dt is not None else self.rng.uniform(2, 12),
        )


# -- the run: agents/sim.py owns the world clock, failure and decision points --

def build_run(seed: int, memory: dict | None = None, use_llm: bool | None = None):
    """Run one sim. Agents decide with Runware when the key is set (or use_llm=True),
    otherwise with the first-option rule. Lessons from earlier runs come from the
    event API when FF_API_URL is set. Returns (events, info, run_id); `info` carries
    the outcome and decisions that `after_run` turns into lessons."""
    import api_client
    import llm
    import sim

    use_llm = llm.enabled() if use_llm is None else use_llm
    decide = llm.choose if use_llm else llm.rule_choose
    lessons, history, runs = {}, "", 0
    if api_client.enabled():
        ctx = api_client.get_learning()
        runs = ctx.get("runs", 0)
        history = ctx.get("history", "")
        for l in ctx.get("lessons", []):
            lessons.setdefault(l["role"], []).append(l)

    log = EventLog()
    log.rng = random.Random(seed)
    outcomes, decisions, end_t = sim.run(seed, decide, lessons, history, log, pos, ext)
    twists = sorted({e["payload"]["twist"] for e in log.events if (e["payload"] or {}).get("twist")})
    saved = sum(1 for st, _ in outcomes.values() if st == "rescued")
    log.t = float(end_t)
    log.speak("director", "director", f"{saved} of {len(outcomes)} out. Run complete at {end_t} seconds.", None, dt=1.0)
    log.events[-1]["model"] = None
    info = {"runs": runs + 1, "outcomes": outcomes, "decisions": decisions, "end_t": end_t, "twists": twists,
            "saved": saved, "llm": use_llm, "lessons_used": sum(len(v) for v in lessons.values())}
    return log.events, info, str(uuid.uuid4())


def after_run(info: dict, run_id: str) -> list:
    """Debrief the run into lessons and store them with the run (needs Runware and the API)."""
    import api_client
    import llm

    if not (info.get("llm") and api_client.enabled()):
        return []
    lessons = llm.debrief(info["outcomes"], info["decisions"], info["end_t"], info["twists"])
    if lessons:
        api_client.post_lessons(run_id, lessons)
    return lessons


# -- output: SQL (same contract as db/fake_run.py) and/or JSON -------------

def sql_str(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def build_sql(events, seed, run_id, scenario_id="apartment-3f") -> str:
    started = datetime.now(timezone.utc).replace(microsecond=0)
    ended = started + timedelta(seconds=events[-1]["t_sim"] + 5)
    lines = ["begin;", f"delete from raw.events where run_id = '{run_id}';", f"delete from raw.runs where run_id = '{run_id}';"]
    lines.append(
        "insert into raw.runs (run_id, seed, scenario_id, notes, started_at, ended_at) values "
        f"('{run_id}', {seed}, {sql_str(scenario_id)}, 'orchestrator run (sim)', "
        f"'{started.isoformat()}', '{ended.isoformat()}');"
    )
    for e in events:
        received = started + timedelta(seconds=e["t_sim"])
        lines.append(
            "insert into raw.events (run_id, seq, t_sim, agent_id, agent_role, type, payload, reasoning, "
            "confidence, model, latency_ms, tokens_in, tokens_out, received_at) values ("
            f"'{run_id}', {e['seq']}, {e['t_sim']}, {sql_str(e['agent_id'])}, {sql_str(e['agent_role'])}, "
            f"{sql_str(e['type'])}, {sql_str(json.dumps(e['payload']))}::jsonb, {sql_str(e['reasoning'])}, "
            f"{sql_str(e['confidence'])}, {sql_str(e['model'])}, null, null, null, '{received.isoformat()}');"
        )
    lines.append("commit;")
    return "\n".join(lines)


def print_sql(events, seed, run_id=None, scenario_id="apartment-3f"):
    run_id = run_id or str(uuid.uuid4())
    print(build_sql(events, seed, run_id, scenario_id))
    return run_id


def write_to_postgres(sql_text: str, container: str = "ff-pg", db: str = "firefighter", user: str = "postgres") -> None:
    """Pipes SQL into the local Bruin Postgres container (bruin/README.md's
    "Run locally" setup) via `docker exec`, so no psql binary is needed on
    the host -- only Docker."""
    import subprocess

    result = subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-U", user, "-d", db],
        input=sql_text.encode(),
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql exited {result.returncode}: {result.stderr.decode()[-800:]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--json", type=str, default=None, help="also write the run as JSON here (for the web app)")
    parser.add_argument("--no-sql", action="store_true", help="skip printing SQL to stdout")
    parser.add_argument("--postgres", action="store_true", help="also write straight into the local ff-pg container")
    parser.add_argument("--llm", action="store_true", help="have Runware write reasoning and lines (RUNWARE_API_KEY)")
    parser.add_argument("--api", action="store_true", help="also send the run to the event API (FF_API_URL, FF_API_TOKEN)")
    args = parser.parse_args()

    if args.llm:
        import llm

        if not llm.enabled():
            sys.exit("--llm needs RUNWARE_API_KEY (env or .env)")
    events, memory, run_id = build_run(args.seed, use_llm=args.llm)
    if args.llm:
        llm.enrich_run(events)
    print(f"seed {args.seed}: {memory['saved']}/{len(memory['outcomes'])} saved at t={memory['end_t']}s, "
          f"twists {memory['twists'] or 'none'}, lessons used {memory['lessons_used']}", file=sys.stderr)

    if not args.no_sql or args.postgres:
        sql_text = build_sql(events, args.seed, run_id)
        if not args.no_sql:
            print(sql_text)
        if args.postgres:
            write_to_postgres(sql_text)
            print(f"wrote run {run_id} to postgres (ff-pg/firefighter)", file=sys.stderr)

    if args.api:
        import api_client

        if not api_client.enabled():
            sys.exit("--api needs FF_API_URL (and FF_API_TOKEN) set")
        api_client.post_run(events, args.seed, run_id, notes="orchestrator run (cli)")
        print(f"sent run {run_id} ({len(events)} events) to {api_client.API_URL}", file=sys.stderr)
        for l in after_run(memory, run_id):
            print(f"  lesson [{l['role']}]: {l['lesson']}", file=sys.stderr)

    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"seed": args.seed, "run_id": run_id, "run_number": memory["runs"], "events": events}, indent=2))
        print(f"wrote {len(events)} events to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
