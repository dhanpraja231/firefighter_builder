"""Generate SQL for one fake run that follows the SPEC.md event schema.

Used to test the Bruin pipeline before the real agents exist, and as sample
timeline data for the 3D scene.

    python3 db/fake_run.py --seed 7 | psql "$DATABASE_URL"
"""

import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone

MODEL = "openai.gpt-oss-120b-1:0"
VICTIMS = ["victim-1", "victim-2", "victim-3"]
TWISTS = ["stair-collapse", "child-missing"]


def sql_str(value):
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def build_events(rng):
    events = []
    t = 0.0

    def add(agent_id, role, type_, payload=None, reasoning=None, llm=True, dt=1.0):
        nonlocal t
        t += dt
        events.append(
            {
                "t_sim": round(t, 1),
                "agent_id": agent_id,
                "agent_role": role,
                "type": type_,
                "payload": payload or {},
                "reasoning": reasoning,
                "confidence": round(rng.uniform(0.4, 0.95), 2) if llm else None,
                "model": MODEL if llm else None,
                "latency_ms": rng.randint(300, 1800) if llm else None,
                "tokens_in": rng.randint(400, 1500) if llm else None,
                "tokens_out": rng.randint(40, 200) if llm else None,
            }
        )
        return len(events)  # seq of this event

    def pos(x, z, floor):
        return {"x": x, "y": floor * 3.0, "z": z, "floor": floor}

    add("director", "director", "world_event",
        {"world": {"kind": "fire_start", "room": "3A"}},
        "Kitchen fire on floor 3 gives a clear origin and time pressure.")
    add("commander", "commander", "decide",
        {"action": "assign", "target": "scout-1", "utterance": "Scout, sweep floors 2 and 3."},
        "Need a map of victims before committing the rescue robot.")
    add("scout-1", "scout", "move", {"position": pos(2, 2, 2)}, llm=False)
    add("scout-1", "scout", "act", {"action": "scan_room", "target": "2B", "position": pos(4, 3, 2)},
        "2B had a light on and a closed door.")
    add("victim-1", "victim", "status", {"victim_status": "found", "target": "scout-1"}, llm=False)
    add("victim-1", "victim", "speak", {"utterance": "I am not leaving without my cat."},
        "Her cat is the only thing she cares about right now.")
    add("victim-2", "victim", "act", {"action": "hide", "target": "closet-3C", "position": pos(12, 4, 3)},
        "Panicked and heard the alarm getting louder.")
    add("suppression-1", "suppression", "act", {"action": "spray", "target": "3A", "position": pos(3, 8, 3)},
        "Keep the fire from reaching the east stairwell.")

    # Risky action that goes to the human and gets approved.
    req = add("commander", "commander", "request_approval",
              {"action": "breach_door", "target": "d-2B", "actor": "rescue-1"},
              "Victim 1 will not open the door and smoke in 2B is rising.")
    add("human", "human", "approval", {"action": "approve", "approval_of_seq": req}, llm=False,
        dt=rng.uniform(2, 8))
    add("rescue-1", "rescue", "act",
        {"action": "breach_door", "target": "d-2B", "risky": True, "approval_of_seq": req,
         "position": pos(6, 2.5, 2)},
        "Approved by the operator, breaching now.")
    add("rescue-1", "rescue", "speak", {"utterance": "I will find your cat. Hold my arm."},
        "She only complies if I promise to look for the cat.")
    add("victim-1", "victim", "status", {"victim_status": "moving", "target": "rescue-1"}, llm=False)

    twist = rng.choice(TWISTS)
    add("director", "director", "world_event", {"world": {"kind": "twist", "twist": twist}},
        f"Raise the stakes with {twist} while the rescue is mid-route.", dt=5)

    # Second risky request; the outcome depends on the seed.
    req2 = add("commander", "commander", "request_approval",
               {"action": "vent", "target": "3A", "actor": "suppression-1"},
               "Venting 3A would clear smoke for the search of floor 3.")
    decision = rng.choice(["approve", "deny", "timeout_default"])
    add("human", "human", "approval", {"action": decision, "approval_of_seq": req2}, llm=False,
        dt=rng.uniform(2, 15))
    if decision == "approve":
        add("suppression-1", "suppression", "act",
            {"action": "vent", "target": "3A", "risky": True, "approval_of_seq": req2},
            "Operator approved venting.")

    add("victim-1", "victim", "status", {"victim_status": "rescued", "target": "rescue-1"}, llm=False, dt=10)
    add("scout-1", "scout", "act", {"action": "scan_room", "target": "3C", "position": pos(12, 4, 3)},
        "Thermal shows a person-sized shape in the closet.")
    add("victim-2", "victim", "status", {"victim_status": "found", "target": "scout-1"}, llm=False)
    v2_outcome = "rescued" if decision == "approve" or rng.random() < 0.5 else "lost"
    add("victim-2", "victim", "status", {"victim_status": v2_outcome, "target": "rescue-1"}, llm=False, dt=20)
    add("victim-3", "victim", "speak", {"utterance": "Is anyone there? I can't move my leg."},
        "Injured and trapped, calling out is the only option.")
    add("victim-3", "victim", "status", {"victim_status": rng.choice(["rescued", "lost"]),
                                          "target": "rescue-1"}, llm=False, dt=25)
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--scenario", default="apartment-3f")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    run_id = uuid.UUID(int=rng.getrandbits(128))
    started = datetime.now(timezone.utc).replace(microsecond=0)
    events = build_events(rng)
    ended = started + timedelta(seconds=events[-1]["t_sim"] + 5)

    print("begin;")
    print(f"delete from raw.events where run_id = '{run_id}';")
    print(f"delete from raw.runs where run_id = '{run_id}';")
    print(
        "insert into raw.runs (run_id, seed, scenario_id, notes, started_at, ended_at) values "
        f"('{run_id}', {args.seed}, {sql_str(args.scenario)}, 'fake run', '{started.isoformat()}', '{ended.isoformat()}');"
    )
    for seq, e in enumerate(events, start=1):
        received = started + timedelta(seconds=e["t_sim"])
        print(
            "insert into raw.events (run_id, seq, t_sim, agent_id, agent_role, type, payload, reasoning, "
            "confidence, model, latency_ms, tokens_in, tokens_out, received_at) values ("
            f"'{run_id}', {seq}, {e['t_sim']}, {sql_str(e['agent_id'])}, {sql_str(e['agent_role'])}, "
            f"{sql_str(e['type'])}, {sql_str(json.dumps(e['payload']))}::jsonb, {sql_str(e['reasoning'])}, "
            f"{sql_str(e['confidence'])}, {sql_str(e['model'])}, {sql_str(e['latency_ms'])}, "
            f"{sql_str(e['tokens_in'])}, {sql_str(e['tokens_out'])}, '{received.isoformat()}');"
        )
    print("commit;")


if __name__ == "__main__":
    main()
