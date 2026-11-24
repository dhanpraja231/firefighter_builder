"""Firefighter Robots orchestrator.

Runs the beat-by-beat version of the tick loop in SPEC.md section 0, using
the cast and twists from story/outline.md and story/characters.md. Every
agent's decision goes through `decide_*`, which has exactly the shape a real
LLM call would have (persona + observation -> action) and is seeded, so two
seeds genuinely diverge (the child does or doesn't bolt, the skeptic waits
or doesn't, the vent request is approved or denied). There is no LLM wired
in yet -- this is the rule-based stand-in so the rest of the pipeline
(events -> Postgres -> Bruin -> mart.*, and events -> JSON -> the Three.js
scene) works end to end today. Swapping in Bedrock or Anthropic means
replacing the bodies of the `decide_*` functions; nothing else changes.

    python3 agents/orchestrator.py --seed 1 | psql "$DATABASE_URL"
    python3 agents/orchestrator.py --seed 1 --json web/public/runs/seed-1.json
"""

import argparse
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODEL = "rule-based-v0"  # swap for "openai.gpt-oss-120b-1:0" (Bedrock) once creds exist

FLOOR_Y = {1: 0.0, 2: 3.0, 3: 6.0, 4: 9.0, 5: 12.0}
FLOOR_HEIGHT = 3.0

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
    "sidewalk": (-2.1, 0.0, 6.0),
}

# Same-floor door graph (mirrors layout.ts doorsFor).
ROOM_ADJ = {
    "living": ["hall", "bedroom-w"],
    "bedroom-w": ["living", "landing"],
    "landing": ["bedroom-w", "bedroom-e"],
    "bedroom-e": ["landing", "kitchen"],
    "kitchen": ["hall", "bedroom-e"],
    "hall": ["living", "kitchen"],
}

# Rooms that catch fire from a neighbor once intensity is high enough.
FIRE_ADJ = {
    "kitchen": ["hall", "bedroom-e"],
    "hall": ["kitchen", "living"],
    "living": ["hall", "bedroom-w"],
    "bedroom-w": ["living", "landing"],
    "bedroom-e": ["kitchen", "landing"],
    "landing": ["bedroom-w", "bedroom-e"],
}


def pos(floor: int, kind: str) -> dict:
    x, z = ROOM_XZ[kind]
    return {"x": x, "y": FLOOR_Y[floor], "z": z, "floor": floor - 1}


def ext(name: str) -> dict:
    x, y, z = EXTERIOR[name]
    return {"x": x, "y": y, "z": z, "floor": -1}


def room_id(floor: int, kind: str) -> str:
    return f"{floor}-{kind}"


def _bfs_rooms(start: str, goal: str) -> list[str]:
    if start == goal:
        return [start]
    queue = [start]
    prev = {start: None}
    while queue:
        cur = queue.pop(0)
        for nxt in ROOM_ADJ.get(cur, []):
            if nxt in prev:
                continue
            prev[nxt] = cur
            if nxt == goal:
                path = [goal]
                while path[-1] != start:
                    path.append(prev[path[-1]])
                return list(reversed(path))
            queue.append(nxt)
    return [start, goal]


def _stair_climb(from_floor: int) -> list[dict]:
    """Waypoints along the switchback between from_floor and from_floor+1."""
    y0 = FLOOR_Y[from_floor]
    return [
        {"x": 7.0, "y": y0 + 0.05, "z": 4.2, "floor": from_floor - 1},
        {"x": 7.0, "y": y0 + 0.75, "z": 5.8, "floor": from_floor - 1},
        {"x": 8.0, "y": y0 + FLOOR_HEIGHT / 2, "z": 7.95, "floor": from_floor - 1},
        {"x": 9.0, "y": y0 + 2.25, "z": 5.8, "floor": from_floor},
        {"x": 9.0, "y": y0 + FLOOR_HEIGHT - 0.05, "z": 4.2, "floor": from_floor},
    ]


def route_positions(origin, destination) -> list[dict]:
    """World positions from origin -> destination via halls and stairs.

    Locations are either ("ext", name) or (floor:int, kind:str).
    """
    if origin == destination:
        return []

    points: list[dict] = []

    def emit_same_floor(floor: int, a: str, b: str):
        for kind in _bfs_rooms(a, b)[1:]:
            points.append(pos(floor, kind))

    # Normalize: step onto floor 1 hall if starting outside.
    if origin[0] == "ext":
        if origin[1] != "entry":
            if origin[1] == "engine":
                points.append(ext("sidewalk"))
            points.append(ext("entry"))
        points.append(pos(1, "hall"))
        cur_floor, cur_kind = 1, "hall"
    else:
        cur_floor, cur_kind = origin

    if destination[0] == "ext":
        # Walk to floor-1 hall, then out.
        if cur_floor != 1 or cur_kind != "hall":
            if cur_kind != "hall":
                emit_same_floor(cur_floor, cur_kind, "hall")
                cur_kind = "hall"
            step = 1 if 1 > cur_floor else -1
            while cur_floor != 1:
                nxt = cur_floor + step
                if step > 0:
                    points.extend(_stair_climb(cur_floor))
                else:
                    points.extend(reversed(_stair_climb(nxt)))
                cur_floor = nxt
                points.append(pos(cur_floor, "hall"))
            cur_kind = "hall"
        points.append(ext("entry"))
        if destination[1] != "entry":
            if destination[1] == "engine":
                points.append(ext("sidewalk"))
            points.append(ext(destination[1]))
        return points

    dest_floor, dest_kind = destination

    if cur_kind != "hall" and cur_floor != dest_floor:
        emit_same_floor(cur_floor, cur_kind, "hall")
        cur_kind = "hall"
    elif cur_floor == dest_floor:
        emit_same_floor(cur_floor, cur_kind, dest_kind)
        return points

    step = 1 if dest_floor > cur_floor else -1
    while cur_floor != dest_floor:
        nxt = cur_floor + step
        if step > 0:
            points.extend(_stair_climb(cur_floor))
        else:
            points.extend(list(reversed(_stair_climb(nxt))))
        cur_floor = nxt
        points.append(pos(cur_floor, "hall"))
        cur_kind = "hall"

    if dest_kind != "hall":
        emit_same_floor(cur_floor, "hall", dest_kind)
    return points


def walk_to(log: "EventLog", agent_id: str, role: str, state: dict, destination, dt_per_hop: float = 0.7):
    """Emit move events along a stair-aware route; track agent location in state['at']."""
    origin = state.setdefault("at", {}).get(agent_id, ("ext", "engine"))
    for point in route_positions(origin, destination):
        log.move(agent_id, role, point, dt=dt_per_hop)
    state["at"][agent_id] = destination


def emit_fire_stage(log: "EventLog", stage: int, vent_approved: bool | None = None):
    """Progressive fire/smoke across rooms. Scene only renders what we emit."""
    if stage == 0:
        log.world({"type": "fire", "roomId": room_id(3, "kitchen"), "intensity": 0.28},
                   "Grease fire starts on the stove.", dt=0.0)
        log.world({"type": "smoke", "roomId": room_id(3, "hall"), "intensity": 0.2},
                   "Smoke reaches the hall first.")
        log.world({"type": "door", "doorId": "3-door-kitchen-hall", "openness": 0.15},
                   "Kitchen door ajar — heat already leaking into the hall.", dt=0.1)
    elif stage == 1:
        log.world({"type": "fire", "roomId": room_id(3, "kitchen"), "intensity": 0.55},
                   "Kitchen fire climbing; cabinets involved.")
        log.world({"type": "fire", "roomId": room_id(3, "hall"), "intensity": 0.22},
                   "Fire pushes into the hall toward the stair core.")
        log.world({"type": "smoke", "roomId": room_id(3, "hall"), "intensity": 0.45},
                   "Hall smoke thickens.")
        log.world({"type": "smoke", "roomId": room_id(3, "living"), "intensity": 0.25},
                   "Smoke drifts into the living room.", dt=0.2)
    elif stage == 2:
        intensity = 0.35 if vent_approved else 0.7
        log.world({"type": "fire", "roomId": room_id(3, "kitchen"), "intensity": intensity + 0.15},
                   "Origin still burning after hose contact.")
        log.world({"type": "fire", "roomId": room_id(3, "hall"), "intensity": 0.18 if vent_approved else 0.4},
                   "Stair-adjacent hall still hot.")
        log.world({"type": "smoke", "roomId": room_id(3, "bedroom-w"), "intensity": 0.3},
                   "Smoke reaches the skeptic's bedroom.")
        log.world({"type": "smoke", "roomId": room_id(4, "hall"), "intensity": 0.25},
                   "Heat column drives smoke up the stairwell to floor 4.", dt=0.2)
    elif stage == 3:
        if vent_approved:
            log.world({"type": "fire", "roomId": room_id(3, "kitchen"), "intensity": 0.25},
                       "Venting and water knocked the kitchen back.")
            log.world({"type": "fire", "roomId": room_id(3, "hall"), "intensity": 0.08},
                       "Hall fire nearly out.")
            log.world({"type": "smoke", "roomId": room_id(4, "landing"), "intensity": 0.2},
                       "Residual smoke upstairs.", dt=0.2)
        else:
            log.world({"type": "fire", "roomId": room_id(3, "kitchen"), "intensity": 0.85},
                       "Sealed kitchen flashover risk.")
            log.world({"type": "fire", "roomId": room_id(3, "hall"), "intensity": 0.55},
                       "Hall fully involved; stairs threatened.")
            log.world({"type": "fire", "roomId": room_id(3, "bedroom-e"), "intensity": 0.3},
                       "Fire spreads east into the bedroom.")
            log.world({"type": "smoke", "roomId": room_id(4, "hall"), "intensity": 0.5},
                       "Floor 4 hall filling — family is next on the path.")
            log.world({"type": "smoke", "roomId": room_id(4, "landing"), "intensity": 0.35},
                       "Landing smoke cuts the north exit.", dt=0.2)


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


# -- decide_* functions: the pluggable "LLM" interface --------------------
# Each takes (log, rng, state) and returns nothing; it pushes whatever
# events that agent decided on. `state` is a plain dict both read and
# written, standing in for the observation a real LLM call would get.

def decide_commander_open(log: EventLog, rng, state):
    log.decide(
        "commander", "commander",
        {"action": "assign", "target": "scout-1", "utterance": "Scout, sweep every floor and report what you find."},
        "Need the full picture before committing the rescue robot anywhere.",
    )


def decide_scout_sweep(log: EventLog, rng, state):
    tour = [
        (1, "living", "victim-teen"),
        (2, "bedroom-w", "victim-elderly"),
        (2, "bedroom-e", "victim-couple-a"),
        (3, "kitchen", None),
        (3, "bedroom-w", "victim-skeptic"),
        (4, "bedroom-e", "victim-parent"),
        (5, "living", "victim-regular"),
    ]
    state.setdefault("at", {})["scout-1"] = ("ext", "engine")
    for floor, kind, victim in tour:
        walk_to(log, "scout-1", "scout", state, (floor, kind), dt_per_hop=0.55)
        if kind == "kitchen":
            log.act("scout-1", "scout", "scan_room", room_id(floor, kind),
                     "Heat signature matches an active stove fire.", dt=1.0)
            log.speak("scout-1", "scout", "Confirmed, fire is in the floor 3 kitchen.", None, dt=0.5)
            state["fire_confirmed"] = True
            emit_fire_stage(log, 1)
            continue
        log.act("scout-1", "scout", "scan_room", room_id(floor, kind),
                 f"Checking {kind.replace('-', ' ')} on floor {floor}.", dt=1.0)
        if victim:
            log.status(victim, "found", "scout-1")
            if victim == "victim-couple-a":
                log.status("victim-couple-b", "found", "scout-1")
            if victim == "victim-parent":
                log.status("victim-child", "found", "scout-1")
            state.setdefault("found", []).append(victim)
            log.speak("scout-1", "scout", f"Found someone on floor {floor}, {kind.replace('-', ' ')}.", None, dt=0.4)


def decide_commander_assign(log: EventLog, rng, state):
    log.decide(
        "commander", "commander",
        {"action": "assign", "target": "hose-1,rescue-1",
         "utterance": "Hose-1, hold the floor 3 stairwell. Rescue-1, start with the easiest extracts and work up."},
        "Fire is confirmed on 3. Buy time on the stairwell while rescue clears rooms floor by floor.",
    )


def decide_hose(log: EventLog, rng, state):
    state.setdefault("at", {})["hose-1"] = ("ext", "engine")
    walk_to(log, "hose-1", "suppression", state, (3, "hall"), dt_per_hop=0.6)
    vent_approved = rng.random() < 0.6
    seq = log.request_approval(
        "hose-1", "suppression", "vent", room_id(3, "kitchen"),
        "Venting would clear smoke from the stairwell route, but the kitchen door is still closed on an active fire.",
    )
    log.approval("approve" if vent_approved else "deny", seq)
    if vent_approved:
        log.act("hose-1", "suppression", "vent", room_id(3, "kitchen"), "Operator approved, venting now.",
                 risky=True, extra={"approval_of_seq": seq})
        log.world({"type": "door", "doorId": "3-door-kitchen-hall", "openness": 0.9},
                   "Kitchen door opened for vent.")
        log.world({"type": "window", "windowId": "3-window-living-w", "broken": True},
                   "West window broken to relieve pressure.")
    else:
        log.act("hose-1", "suppression", "spray", room_id(3, "kitchen"), "Operator denied the vent, holding with water instead.")
    state["vent_approved"] = vent_approved
    emit_fire_stage(log, 2, vent_approved=vent_approved)


def decide_rescue_easy(log: EventLog, rng, state, floor, kind, victim_id, name):
    walk_to(log, "rescue-1", "rescue", state, (floor, kind), dt_per_hop=0.55)
    log.speak("rescue-1", "rescue", f"{name}, this way, let's go.", "First ask, no complication expected.")
    log.status(victim_id, "moving", "rescue-1")
    log.status(victim_id, "rescued", "rescue-1", dt=3.0)


def decide_rescue_teen(log: EventLog, rng, state):
    walk_to(log, "rescue-1", "rescue", state, (1, "living"), dt_per_hop=0.55)
    log.speak("rescue-1", "rescue", "Time to go, the fire's upstairs.", None)
    log.speak("victim-teen", "victim", "One sec, let me get the flames in frame.",
              "Streaming the fire live, won't leave mid-stream per persona.")
    log.speak("rescue-1", "rescue", "The stream cuts when the router does. Let's move.",
               "Give the stated reason the teen actually responds to.")
    log.status("victim-teen", "moving", "rescue-1")
    log.status("victim-teen", "rescued", "rescue-1", dt=3.0)


def decide_rescue_elderly(log: EventLog, rng, state):
    walk_to(log, "rescue-1", "rescue", state, (2, "bedroom-w"), dt_per_hop=0.55)
    log.speak("rescue-1", "rescue", "Mrs. Okafor, we need to leave now.", None)
    log.speak("victim-elderly", "victim", "Not without my cat.",
              "Won't leave without her pet, per persona.")
    log.speak("rescue-1", "rescue", "I'll look for the cat on my way back. Let's get you out first.",
               "Only condition that satisfies her stated compliance rule.")
    log.status("victim-elderly", "moving", "rescue-1")
    log.status("victim-elderly", "rescued", "rescue-1", dt=4.0)


def decide_rescue_couple(log: EventLog, rng, state):
    walk_to(log, "rescue-1", "rescue", state, (2, "bedroom-e"), dt_per_hop=0.55)
    log.speak("rescue-1", "rescue", "Let's go, both of you.", None)
    log.status("victim-couple-a", "moving", "rescue-1")
    log.status("victim-couple-b", "moving", "rescue-1")
    log.status("victim-couple-a", "rescued", "rescue-1", dt=3.0)
    log.status("victim-couple-b", "rescued", "rescue-1", dt=0.2)


def decide_rescue_skeptic(log: EventLog, rng, state):
    walk_to(log, "rescue-1", "rescue", state, (3, "bedroom-w"), dt_per_hop=0.55)
    log.speak("rescue-1", "rescue", "I can get you out safely, follow me.", None)
    already_saved = bool(state.get("already_rescued"))
    if not already_saved:
        log.speak("victim-skeptic", "victim", "I'll wait for an actual firefighter.",
                   "Distrusts robots per persona; hasn't seen one succeed yet.")
        log.speak("rescue-1", "rescue", "Understood. I'll check back.", "Can't force compliance, moving on.")
        state["skeptic_pending"] = True
    else:
        log.speak("victim-skeptic", "victim", "...Fine. Saw what you did back there. Let's go.",
                   "Won over by watching the robot rescue someone else first, per persona.")
        log.status("victim-skeptic", "moving", "rescue-1")
        log.status("victim-skeptic", "rescued", "rescue-1", dt=3.0)
        state["skeptic_pending"] = False


def decide_child_refusal(log: EventLog, rng, state, memory: dict):
    """The beat the whole run hinges on: the commander's evacuation order
    reaches the parent and child, and the child's own persona decides
    whether to comply -- seeded, not scripted, and shaped by what past runs
    taught `memory` about how to approach this child."""
    walk_to(log, "rescue-1", "rescue", state, (4, "bedroom-e"), dt_per_hop=0.55)
    emit_fire_stage(log, 3, vent_approved=state.get("vent_approved"))
    log.speak("commander", "commander", "Rescue-1, get the family out, floor 4 is next on the fire's path.",
               "Smoke is rising from 3; floor 4 can't wait.")
    if memory["cautious_briefing"]:
        log.speak("rescue-1", "rescue", "I know this is loud and scary. I'll go slow, take my hand when you're ready.",
                   f"Learned from {memory['child_losses']} earlier run(s): a blunt order makes this child bolt. Lead with the promise instead.")
    else:
        log.speak("rescue-1", "rescue", "Time to go, both of you, now.", "First time handling this child; no prior lesson to draw on.")
    bolts = rng.random() < memory["bolt_prob"]
    state["child_bolted"] = bolts
    if bolts:
        log.speak("victim-child", "victim", "No! You're too loud, I'm not going with you.",
                   "Distrusts a direct order from a robot on the first ask, per persona.")
        state.setdefault("at", {})["victim-child"] = (4, "bedroom-e")
        walk_to(log, "victim-child", "victim", state, (4, "bedroom-w"), dt_per_hop=0.45)
        log.world({"type": "smoke", "roomId": room_id(4, "landing"), "intensity": 0.45},
                   "Child slipped out of the room before reaching the exit -- the stakes just went up.")
        log.speak("victim-parent", "victim", "Where did they go?! I'm not leaving without them!",
                   "Refuses to move toward the exit until the child is confirmed found, per persona.")
        log.decide("commander", "commander",
                    {"action": "re-assign", "target": "rescue-1", "utterance": "Rescue-1, the child bolted toward bedroom-w. Find them first."},
                    "The parent won't move without the child; re-plan around finding the child.")
        walk_to(log, "rescue-1", "rescue", state, (4, "bedroom-w"), dt_per_hop=0.5)
        found = rng.random() < memory["found_prob"]
        if found:
            log.speak("rescue-1", "rescue", "Found you. I'll go slow, I promise.",
                       "Matches the child's stated compliance condition: go slow, don't force it.")
            log.speak("victim-child", "victim", "...Okay. Don't let go.",
                       "Complies once a robot promises to go slow, per persona.")
            log.status("victim-child", "moving", "rescue-1")
            log.status("victim-parent", "moving", "rescue-1")
            log.status("victim-child", "rescued", "rescue-1", dt=3.0)
            log.status("victim-parent", "rescued", "rescue-1", dt=0.3)
        else:
            log.world({"type": "smoke", "roomId": room_id(4, "bedroom-w"), "intensity": 0.6},
                       "Smoke closed in on bedroom-w before rescue-1 reached the child.")
            log.status("victim-child", "lost", "rescue-1", dt=3.0)
            log.status("victim-parent", "moving", "rescue-1", dt=0.3)
            log.speak("victim-parent", "victim", "No. No, no, no.", "Devastated; outcome the human verdict will have to judge.")
            log.status("victim-parent", "rescued", "rescue-1", dt=2.0)
    else:
        log.speak("victim-child", "victim", "...Okay, but hold my hand.",
                   "Complies on the first ask this run -- the seed landed the other way.")
        log.status("victim-child", "moving", "rescue-1")
        log.status("victim-parent", "moving", "rescue-1")
        log.status("victim-child", "rescued", "rescue-1", dt=3.0)
        log.status("victim-parent", "rescued", "rescue-1", dt=0.3)


def decide_stairwell_twist(log: EventLog, rng, state):
    if not rng.random() < 0.7:
        return
    log.world({"type": "smoke", "roomId": room_id(2, "landing"), "intensity": 0.5},
               "Structural groan from the stairwell core -- the Director is treating floor 2-3 as a compromised route.")
    log.decide("commander", "commander",
                {"action": "re-route", "target": "all", "utterance": "Stair core between 2 and 3 is compromised. Use the far stair only."},
                "Stairwell collapse risk per the twist trigger: a robot has been on floor 2 or 3 past t=60.")


def decide_human_verdict(log: EventLog, rng, state, outcomes):
    rescued = sum(1 for v in outcomes.values() if v == "rescued")
    lost = sum(1 for v in outcomes.values() if v == "lost")
    verdict = "approve" if lost == 0 else ("approve" if rng.random() < 0.5 else "deny")
    log.speak("director", "director",
               f"{rescued} rescued, {lost} lost. Run complete.", None, dt=0.2)
    log._push("human", "human", "approval",
               {"action": verdict, "approval_of_seq": None, "note": f"outcome verdict: {rescued} rescued / {lost} lost"},
               None, llm=False, dt=2.0)


def build_run(seed: int, memory: dict | None = None) -> list:
    """Builds one run's events and, unless `memory` was passed in by the
    caller (the server threads one instance across calls), loads/updates/
    saves agents/memory.json itself -- so `python3 orchestrator.py --seed N`
    run twice in a row already shows the learning curve."""
    owns_memory = memory is None
    if owns_memory:
        memory = load_memory()

    rng = random.Random(seed)
    log = EventLog()
    log.rng = rng
    state = {
        "at": {
            "scout-1": ("ext", "engine"),
            "hose-1": ("ext", "engine"),
            "rescue-1": ("ext", "engine"),
        }
    }

    emit_fire_stage(log, 0)

    decide_commander_open(log, rng, state)
    decide_scout_sweep(log, rng, state)
    decide_commander_assign(log, rng, state)
    decide_hose(log, rng, state)

    outcomes = {}

    decide_rescue_easy(log, rng, state, 5, "living", "victim-regular", "Neighbor")
    outcomes["victim-regular"] = "rescued"
    state["already_rescued"] = True

    decide_rescue_teen(log, rng, state)
    outcomes["victim-teen"] = "rescued"

    decide_rescue_elderly(log, rng, state)
    outcomes["victim-elderly"] = "rescued"

    decide_rescue_couple(log, rng, state)
    outcomes["victim-couple-a"] = "rescued"
    outcomes["victim-couple-b"] = "rescued"

    decide_stairwell_twist(log, rng, state)

    decide_rescue_skeptic(log, rng, state)
    if state.get("skeptic_pending"):
        decide_rescue_skeptic(log, rng, state)  # second pass: already_rescued is now true, so this one lands
    outcomes["victim-skeptic"] = "rescued"

    decide_child_refusal(log, rng, state, memory)
    last_two = log.events[-6:]
    child_status = next((e["payload"]["victim_status"] for e in reversed(last_two)
                          if e["agent_id"] == "rescue-1" and e["payload"].get("target") == "victim-child"
                          and e["type"] == "status" and e["payload"]["victim_status"] in ("rescued", "lost")), "rescued")
    outcomes["victim-child"] = child_status
    outcomes["victim-parent"] = "rescued"

    decide_human_verdict(log, rng, state, outcomes)

    # The actual learning step: a run that involved the bolt at all teaches
    # the system something, win or lose this time. `cautious_briefing` is
    # sticky once learned; the probabilities keep improving each time the
    # lesson gets reinforced.
    if state.get("child_bolted"):
        memory["cautious_briefing"] = True
        memory["bolt_prob"] = round(max(0.12, memory["bolt_prob"] - 0.1), 3)
        memory["found_prob"] = round(min(0.95, memory["found_prob"] + 0.08), 3)
    if outcomes["victim-child"] == "lost":
        memory["child_losses"] += 1
    memory["runs"] += 1

    if owns_memory:
        save_memory(memory)

    return log.events, memory, str(uuid.uuid4())


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
        f"('{run_id}', {seed}, {sql_str(scenario_id)}, 'orchestrator run (rule-based decide_fn)', "
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
    args = parser.parse_args()

    events, memory, run_id = build_run(args.seed)

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
        out_path.write_text(json.dumps({"seed": args.seed, "run_id": run_id, "run_number": memory["runs"], "memory": memory, "events": events}, indent=2))
        print(f"wrote {len(events)} events to {out_path} (run #{memory['runs']}, cautious_briefing={memory['cautious_briefing']})", file=sys.stderr)


if __name__ == "__main__":
    main()
