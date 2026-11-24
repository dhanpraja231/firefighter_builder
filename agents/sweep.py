"""Dev tool: run many seeds, print the variety/validity numbers the story engine must hit.

    python agents/sweep.py [N=40] [--policy heuristic]
Uses a fresh in-memory memory per seed and never touches agents/memory.json.
"""

import collections
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine import DEFAULT_MEMORY, run_story  # noqa: E402

ROLES = {"scout", "suppression", "rescue", "commander", "victim", "director", "human"}
TYPES = {"move", "speak", "decide", "act", "request_approval", "approval", "world_event", "status"}
VICTIMS = ["victim-teen", "victim-elderly", "victim-couple-a", "victim-couple-b", "victim-skeptic", "victim-parent", "victim-child", "victim-regular"]


def validate(res):
    ev, errs = res["events"], []
    reqs = {}
    last_t, rescued = -1.0, set()
    status_final = {}
    for i, e in enumerate(ev, 1):
        if e["seq"] != i:
            errs.append(f"seq gap at {i}")
        if e["agent_role"] not in ROLES or e["type"] not in TYPES:
            errs.append(f"bad enum {e['agent_role']}/{e['type']}")
        if e["t_sim"] < last_t:
            errs.append(f"time went backwards at seq {i}")
        last_t = e["t_sim"]
        if e["type"] in ("decide", "act", "request_approval") and not e["reasoning"]:
            errs.append(f"missing reasoning seq {i}")
        p = e["payload"]
        if e["type"] == "request_approval":
            reqs[e["seq"]] = None
        if e["type"] == "approval" and p.get("approval_of_seq") is not None:
            if p["approval_of_seq"] not in reqs:
                errs.append(f"approval {i} points at unknown request")
            reqs[p["approval_of_seq"]] = p["action"]
        if e["type"] == "act" and p.get("risky"):
            if reqs.get(p.get("approval_of_seq")) != "approve":
                errs.append(f"risky act seq {i} without approved request")
        if e["type"] == "status":
            if e["agent_role"] != "victim":
                errs.append(f"status from non-victim seq {i}")
            s = p["victim_status"]
            if s == "rescued":
                if e["agent_id"] in rescued:
                    errs.append(f"{e['agent_id']} rescued twice")
                rescued.add(e["agent_id"])
            status_final[e["agent_id"]] = s
        if e["type"] == "move" and not ({"x", "y", "z", "floor"} <= set(p["position"])):
            errs.append(f"bad move position seq {i}")
    for v in VICTIMS:
        fin = status_final.get(v)
        if fin not in ("rescued", "lost", "trapped"):
            errs.append(f"{v} ends as {fin}")
        if fin == "trapped" and res["ending"] not in ("commander_retreat", "all_robots_down"):
            errs.append(f"{v} still trapped after a '{res['ending']}' ending")
    return errs


def main():
    n = int(next((a for a in sys.argv[1:] if a.isdigit()), 40))
    endings, durs, nrescued, nlost = collections.Counter(), [], [], []
    orders, first, lost_who, lost_sets = set(), collections.Counter(), collections.Counter(), set()
    ign, burned, adapt = [], [], collections.Counter()
    adapt_runs = 0
    problems = []
    for seed in range(1, n + 1):
        res = run_story(seed, dict(DEFAULT_MEMORY), "heuristic")
        s = res["stats"]
        endings[res["ending"]] += 1
        durs.append(s["duration"])
        nrescued.append(len(s["rescue_order"]))
        nlost.append(len(s["lost"]))
        orders.add(tuple(s["rescue_order"]))
        first[s["rescue_order"][0] if s["rescue_order"] else "(none)"] += 1
        for v in s["lost"]:
            lost_who[v] += 1
        lost_sets.add(tuple(sorted(s["lost"])))
        ign.append(s["ignitions"])
        burned.append(s["rooms_burned"])
        for k, v in s["adapt"].items():
            adapt[k] += v
        adapt_runs += 1 if sum(s["adapt"].values()) > 0 else 0
        for err in validate(res):
            problems.append((seed, err))
    print(f"seeds: {n}")
    print("\nENDINGS (distinct = %d):" % len(endings))
    for k, c in endings.most_common():
        print(f"  {k:26} {c:3}  {100 * c / n:5.1f}%")
    print(f"\nDURATION s  min {min(durs):.1f}  mean {statistics.mean(durs):.1f}  max {max(durs):.1f}   (must be 60-170)")
    print("RESCUED per run:", dict(sorted(collections.Counter(nrescued).items())))
    print("LOST per run:   ", dict(sorted(collections.Counter(nlost).items())))
    print(f"\n(a) distinct rescue-order sequences: {len(orders)} / {n}")
    print("(b) first victim rescued:", {k: f"{100 * c / n:.0f}%" for k, c in first.most_common()})
    print(f"(c) distinct lost-sets: {len(lost_sets)}; times each victim was lost:", dict(lost_who.most_common()))
    print(f"\nFIRE: ignition events min {min(ign)} mean {statistics.mean(ign):.1f} max {max(ign)};  rooms burned min {min(burned)} mean {statistics.mean(burned):.1f} max {max(burned)}")
    print(f"      runs with >=3 rooms burned: {sum(1 for b in burned if b >= 3)}/{n}")
    print(f"ADAPTATION (fire-driven decisions, all runs): {dict(adapt)}   runs with >=1: {adapt_runs}/{n}")
    print(f"\nVALIDATION: {'OK, no problems' if not problems else str(len(problems)) + ' problems'}")
    for seed, err in problems[:15]:
        print("  seed", seed, err)
    # determinism
    a = json.dumps(run_story(7, dict(DEFAULT_MEMORY), "heuristic")["events"], sort_keys=True)
    b = json.dumps(run_story(7, dict(DEFAULT_MEMORY), "heuristic")["events"], sort_keys=True)
    print("DETERMINISM (seed 7 twice):", "identical" if a == b else "DIFFERENT")


if __name__ == "__main__":
    main()
