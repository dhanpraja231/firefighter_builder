"""Core of the story engine: actors, scheduler, event log, physics, twists, endings.

A discrete-event simulation. Every agent runs as a generator "process" that
yields the number of sim-seconds to wait; `Sim.run()` resumes them in time
order. Nothing here scripts a plot: agents choose actions through a Policy,
the world pushes back (fire, smoke, collapse), and the ending falls out of the
final state.
"""

from __future__ import annotations

import heapq
import itertools
import json
import random
from pathlib import Path

from policy import pretty_room
from world import (
    EXTERIOR, FLOORS, LADDER_WINDOW, ROOMS, SAFE_SPOTS, World, floor_of, is_exterior, links,
    position_payload, split_room, xyz,
)

CAP = 160.0  # sim seconds; at this point the human fire brigade arrives and takes over ('time_up')
PERSONAS_DIR = Path(__file__).parent / "personas"

VICTIM_START = {
    "victim-teen": "1-living",
    "victim-elderly": "2-bedroom-w",
    "victim-couple-a": "2-bedroom-e",
    "victim-couple-b": "2-bedroom-e",
    "victim-skeptic": "3-bedroom-w",
    "victim-parent": "4-bedroom-e",
    "victim-child": "4-bedroom-e",
    "victim-regular": "5-living",
}
VICTIM_SPEED = {"victim-elderly": 1.0, "victim-child": 2.4}
POSITION_TYPES = ("move", "speak", "decide", "act", "request_approval", "status")


def load_personas() -> dict:
    personas = {}
    for path in PERSONAS_DIR.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "agents" in data:
            for entry in data["agents"]:
                personas[entry["agent_id"]] = {**{k: v for k, v in data.items() if k != "agents"}, **entry}
        else:
            personas[data["agent_id"]] = data
    return personas


class Actor:
    def __init__(self, aid, role, room, speed, seed, kind):
        self.id, self.role, self.room, self.speed, self.kind = aid, role, room, speed, kind
        self.rng = random.Random(f"{seed}:{aid}")
        self.integrity = 1.0
        self.disabled = False
        self.followers: list[Victim] = []
        self.task: dict | None = None
        self.denied: dict[tuple, float] = {}
        self.tried: dict[str, set] = {}
        self.cleared: set[int] = set()
        self.notes: list[str] = []
        self.traits: dict = {}


class Victim(Actor):
    def __init__(self, aid, room, persona, seed):
        super().__init__(aid, "victim", room, VICTIM_SPEED.get(aid, 2.0), seed, "victim")
        self.persona = persona
        self.name = persona.get("name", aid)
        self.health = 1.0
        self.panic = 0.0
        self.status = "trapped"
        self.known_room: str | None = None
        self.found_t = 0.0
        self.leader: Actor | None = None
        self.carried = False
        self.refused = 0
        self.hiding_until = 0.0
        self.last_flee = -99.0
        self.by_brigade = False
        self.ever_found = False

    @property
    def resolved(self) -> bool:
        return self.status in ("rescued", "lost")


class Approver:
    """Seeded stand-in for the human on the loop (a live approver can replace it)."""

    RISK = {"breach_door": 0.35, "enter_unstable": 0.6, "vent": 0.75}

    def __init__(self, seed):
        self.rng = random.Random(f"human:{seed}")
        self.caution = self.rng.uniform(0.15, 0.85)

    def decide(self, action, urgency):
        if self.rng.random() < 0.04:
            return "timeout_default", 15.0  # nobody answered in time: role default is deny
        p = 0.97 - self.caution * self.RISK.get(action, 0.5) * 1.15 + 0.3 * urgency
        delay = round(self.rng.uniform(1.5, 6.0), 1)
        return ("approve" if self.rng.random() < p else "deny"), delay

    def verdict(self, rescued, lost):
        if lost == 0:
            return "approve"
        return "approve" if self.rng.random() < max(0.15, 0.7 - 0.12 * lost - 0.3 * self.caution) else "deny"


class CoreMixin:
    # -- scheduling -------------------------------------------------------
    def schedule(self, t, gen):
        heapq.heappush(self._q, (t, next(self._cnt), gen))

    def spawn(self, gen, delay=0.0):
        self.schedule(self.now + delay, gen)

    def steps(self):
        """Advance the simulation one process step at a time; yields after each step so a caller can
        collect the events that step produced (and call the next agent policy only when it is needed)."""
        while self._q and not self.ended:
            t, _, gen = heapq.heappop(self._q)
            if t > CAP + 30:
                break
            self.now = t
            try:
                dt = next(gen)
            except StopIteration:
                yield
                continue
            self.schedule(self.now + max(0.05, float(dt)), gen)
            yield

    def run(self):
        for _ in self.steps():
            pass

    # -- events -----------------------------------------------------------
    def emit(self, a, type_, payload=None, reasoning=None, confidence=None, dec=None, t=None):
        t = self.now if t is None else t
        t = max(t, self._last_t)
        self._last_t = t
        payload = dict(payload or {})
        if type_ in POSITION_TYPES and "position" not in payload and getattr(a, "room", None):
            payload["position"] = position_payload(a.room)
        if confidence is None and dec is not None:
            confidence = dec.confidence
        ev = {
            "seq": len(self.events) + 1, "t_sim": round(t, 2), "agent_id": a.id, "agent_role": a.role,
            "type": type_, "payload": payload, "reasoning": reasoning, "confidence": confidence,
            "model": dec.model if dec is not None else None,
        }
        if dec is not None and dec.latency_ms is not None:
            ev["latency_ms"], ev["tokens_in"], ev["tokens_out"] = dec.latency_ms, dec.tokens_in, dec.tokens_out
        self.events.append(ev)
        if type_ in ("decide", "act", "speak") and hasattr(a, "notes"):
            a.notes.append(f"t={t:.0f} {payload.get('action') or 'said'} {payload.get('target') or payload.get('utterance', '')}"[:90])
            del a.notes[:-6]
        return ev["seq"]

    def world_event(self, world, reason=None, dec=None, **extra):
        payload = {"world": world, **extra}
        return self.emit(self.director, "world_event", payload, reason, None, dec)

    def say(self, a, text, dec=None, **payload):
        if text:
            self.radio.append(f"{a.id}: {text}")
            del self.radio[:-8]
            return self.emit(a, "speak", {"utterance": text, **payload}, None, None, dec)
        return None

    def emit_move(self, a, room, anim):
        a.room = room
        self.emit(a, "move", {"position": position_payload(room), "room": room, "anim": anim})

    def emit_move_xyz(self, a, xyz_, anim):
        x, y, z = xyz_
        self.emit(a, "move", {"position": {"x": x, "y": y, "z": z, "floor": -1}, "room": "exterior-safe", "anim": anim})

    def victim_status(self, v, status, helper, anim=None):
        v.status = status
        if status == "found":
            v.ever_found = True
        self.emit(v, "status", {"victim_status": status, "target": helper, **({"anim": anim} if anim else {})})

    # -- physics ----------------------------------------------------------
    def physics_proc(self):
        while True:
            yield 1.0
            now = self.now
            events = self.world.step(now, self.rng)
            ign = {room: (src, kind, was_open) for room, src, kind, was_open in self.world.ignitions}
            for room, (src, kind, was_open) in ign.items():
                self.on_ignition(room, src, kind, was_open)
            for e in events:
                reason = None
                if e["type"] == "fire" and e["roomId"] in ign:
                    src, kind, was_open = ign[e["roomId"]]
                    reason = self.ignition_reason(e["roomId"], src, kind, was_open)
                elif e["type"] == "fire" and e["intensity"] == 0.0:
                    reason = f"The fire in {pretty_room(e['roomId'])} burns out."
                self.world_event(e, reason)
            if self.power_back and now >= self.power_back:
                self.power_back = 0.0
                self.world.power = True
                self.world_event({"type": "power", "on": True}, "Power is restored.")
            for a in self.robots:
                if not a.disabled and not is_exterior(a.room):
                    a.integrity -= 0.007 * self.world.fire[a.room] + 0.0015 * self.world.smoke[a.room]
                    if a.integrity <= 0:
                        self.disable(a)
            for v in self.victims.values():
                if v.resolved or is_exterior(v.room):
                    continue
                fire, smoke = self.world.fire[v.room], self.world.smoke[v.room]
                v.health -= 0.032 * fire + 0.007 * smoke ** 1.3
                near = any(r.room == v.room and not r.disabled for r in self.robots)
                nfire = max((self.world.fire[n] for n, _, k, _ in links(v.room) if not is_exterior(n)), default=0.0)
                base = v.traits.get("panic", 0.3)
                v.panic = max(0.0, min(1.0, v.panic + (0.03 + 0.06 * base) * (fire + 0.5 * smoke + 0.6 * nfire) - (0.08 if near else 0.0) - 0.01))
                if v.health <= 0:
                    self.lose(v)
                    continue
                self.victim_autonomy(v)
            self.check_end()
            if self.ended:
                return

    def ignition_reason(self, room, src, kind, was_open):
        if kind == "stairs":
            word = "climb the stairwell" if floor_of(room) > floor_of(src) else "drop down the stairwell"
            return f"Flames {word} from {pretty_room(src)} into {pretty_room(room)}."
        if kind == "door":
            how = "through the open door" if was_open else "burn through the closed door"
            return f"Flames reach {pretty_room(room)} {how} from {pretty_room(src)}."
        return f"Fire spreads into {pretty_room(room)}."

    def on_ignition(self, room, src, kind, was_open):
        """A new room catches. Anyone who matters to that room is told, and the commander must re-plan."""
        self.ignition_count += 1
        self.alerts.append(f"fire reached {pretty_room(room)}")
        del self.alerts[:-6]
        affected = [v for v in self.victims.values() if not v.resolved and v.known_room
                    and (v.known_room == room or floor_of(v.known_room) == floor_of(room))]
        if affected or room.endswith("hall"):
            self.dirty = True

    def disable(self, a):
        a.disabled = True
        self.world_event({"type": "robot_down", "agent": a.id}, f"{a.id} has taken too much damage and is down.")
        for v in list(a.followers):
            self.release(v, a)
        a.followers = []
        self.dirty = True
        self.say(self.commander, f"Lost {a.id}. It's not responding.")

    def release(self, v, leader):
        v.leader = None
        v.carried = False
        if v.status == "moving":
            self.victim_status(v, "found", leader.id)

    def lose(self, v):
        if v.leader is not None and v in v.leader.followers:
            v.leader.followers.remove(v)
        v.leader = None
        self.victim_status(v, "lost", "fire", "collapse")
        self.dirty = True
        self.say(self.commander, f"We've lost {v.name}.")

    def hazard_entry(self, a, group, room):
        if is_exterior(room):
            return
        f, s = self.world.fire[room], self.world.smoke[room]
        if not a.disabled:
            a.integrity -= 0.05 * f + 0.005 * s
            if a.integrity <= 0:
                self.disable(a)
        for v in group:
            v.health -= 0.05 * f

    def victim_autonomy(self, v):
        if v.leader is not None or v.status not in ("trapped", "found") or self.now < v.hiding_until:
            return
        if v.hiding_until and self.now >= v.hiding_until and v.known_room is None:
            v.hiding_until = 0.0
            self.shout(v)
            return
        danger = self.world.danger(v.room)
        if danger > 0.42 and self.now - v.last_flee > 12 and v.rng.random() < 0.3:
            self.flee(v)

    def flee_options(self, v):
        opts = []
        for nbr, d, kind, door in links(v.room):
            if kind != "door" or is_exterior(nbr):
                continue
            opts.append({"action": "flee", "target": nbr, "risky": False, "label": f"run to {pretty_room(nbr)}",
                         "meta": {"danger": round(self.world.danger(nbr), 2), "dist": round(d, 1)}})
        opts.append({"action": "hide", "target": None, "risky": False, "label": "hide in place", "meta": {}})
        opts.append({"action": "stay", "target": None, "risky": False, "label": "stay put", "meta": {}})
        for i, o in enumerate(opts):
            o["i"] = i
        return opts

    def flee(self, v, forced=False):
        opts = self.flee_options(v)
        obs = {"t": round(self.now, 1), "persona": v.persona, "memory": self.mem_view(),
               "ctx": {"danger_here": round(self.world.danger(v.room), 2), "health": round(v.health, 2)}}
        dec = self.policy.decide(v.id, "victim", obs, opts, v.rng)
        opt = opts[dec.index]
        if forced and opt["action"] != "flee":
            cand = [o for o in opts if o["action"] == "flee"]
            if not cand:
                return
            opt = min(cand, key=lambda o: o["meta"]["danger"])
        v.last_flee = self.now
        if opt["action"] == "flee":
            self.say(v, dec.utterance, dec, anim="plead")
            door = self.world.door_between(v.room, opt["target"])
            if door and not self.world.door_open[door]:
                self.world.door_open[door] = True
                self.world_event({"type": "door", "doorId": door, "openness": 1}, f"{v.name} opens the door and runs.")
            self.emit_move(v, opt["target"], "run")
            self.reveal(v)
        elif opt["action"] == "hide":
            v.hiding_until = self.now + v.rng.uniform(8, 16)

    def shout(self, v):
        self.say(v, (self.policy_lines(v, "help")), None, anim="plead")
        self.reveal(v)

    def reveal(self, v):
        """Being heard puts the victim on the commander's map."""
        if v.status == "trapped":
            self.victim_status(v, "found", "radio")
            v.found_t = self.now
        v.known_room = v.room
        self.dirty = True

    def policy_lines(self, v, key):
        from policy import VICTIM_LINES
        lines = VICTIM_LINES.get(v.id, {}).get(key) or ["Help!"]
        return lines[int(v.rng.random() * len(lines)) % len(lines)]

    # -- twists -----------------------------------------------------------
    def backdraft(self, room, cause):
        w = self.world
        w.fire[room] = 1.0
        for nbr, _, kind, door in links(room):
            if not is_exterior(nbr):
                w.fire[nbr] = max(w.fire[nbr], 0.3)
                w.smoke[nbr] = min(1.0, w.smoke[nbr] + 0.3)
                if kind == "door":
                    w.door_open[door] = True
        for a in self.robots:
            if a.room == room and not a.disabled:
                a.integrity -= 0.25
                if a.integrity <= 0:
                    self.disable(a)
        for v in self.victims.values():
            if not v.resolved and v.room == room:
                v.health -= 0.3
                v.panic = 1.0
        self.world_event({"type": "fire", "roomId": room, "intensity": 1.0},
                         f"Backdraft in {pretty_room(room)}: fresh air hit a sealed fire (triggered by {cause}).")
        self.world_event({"type": "twist", "twist": "backdraft", "room": room}, None, room=room, anim="flinch")
        self.twists.append("backdraft")
        self.dirty = True

    def collapse(self, flight, reason, dec=None):
        self.world.collapsed.add(flight)
        if flight + 1 <= 4:
            self.world.unstable.add(flight + 1)
        self.world.unstable.discard(flight)
        self.world_event({"type": "twist", "twist": "stair-collapse", "flight": [flight, flight + 1]}, reason, dec,
                         room=f"{flight}-hall", anim="flinch")
        self.twists.append("stair-collapse")
        self.dirty = True

    # -- ending -----------------------------------------------------------
    def check_end(self):
        if self.ended:
            return
        unresolved = [v for v in self.victims.values() if not v.resolved]
        if not unresolved:
            self.finish("resolved")
        elif self.now >= self.brigade_eta:
            self.finish("time_up")
        elif all(r.disabled for r in (self.rescue, self.hose)):
            self.finish("all_robots_down")

    def brigade(self, t0):
        """Time is up: human firefighters go in. Whoever is still inside lives or dies by their real state."""
        left = [v for v in self.victims.values() if not v.resolved]
        if not left:
            return
        self.emit(self.director, "world_event", {"world": {"type": "twist", "twist": "brigade-arrives"}},
                  "The fire brigade arrives and goes in after whoever is left.", None, None, t=t0 + 0.2)
        for i, v in enumerate(left):
            t = t0 + 0.5 + 0.3 * i
            p = max(0.03, min(0.9, 0.95 * v.health - 1.2 * self.world.danger(v.room) - 0.05 * (floor_of(v.room) - 1) - (0.3 if v.status == 'trapped' else 0.0) + 0.1))
            v.leader = None
            if self.rng.random() < p:
                v.by_brigade = True
                v.status = "rescued"
                self.emit(v, "status", {"victim_status": "rescued", "target": "brigade", "anim": "celebrate"}, t=t)
            else:
                v.status = "lost"
                self.emit(v, "status", {"victim_status": "lost", "target": "fire", "anim": "collapse"}, t=t)

    SINGLE_LOSS = {
        "victim-skeptic": "skeptic_waited_too_long",
        "victim-elderly": "elderly_left_behind",
        "victim-teen": "teen_never_left_the_stream",
        "victim-regular": "neighbor_lost_on_five",
        "victim-couple-a": "couple_separated",
        "victim-couple-b": "couple_separated",
        "victim-parent": "parent_lost",
        "victim-child": "child_lost",
    }

    def compute_ending(self, reason):
        vs = self.victims
        rescued = [v for v in vs.values() if v.status == "rescued"]
        lost = [v for v in vs.values() if v.status == "lost"]
        if reason == "commander_retreat":
            return "commander_retreat"
        if reason == "all_robots_down":
            return "all_robots_down"
        brig = sum(1 for v in rescued if v.by_brigade)
        if not lost:
            if brig >= 3:
                return "brigade_clears_the_building"
            return "brigade_arrives_in_time" if brig else "all_saved"
        ids = {v.id for v in lost}
        if {"victim-child", "victim-parent"} <= ids:
            return "family_lost"
        cut = [v for v in lost if self.world.collapsed and floor_of(v.room) > min(self.world.collapsed) + 1]
        if self.world.collapsed and len(cut) >= 2:
            return "stairwell_collapse_trap"
        if len(lost) >= 4:
            return "heavy_losses"
        if len(lost) == 1:
            return self.SINGLE_LOSS[lost[0].id]
        if "victim-child" in ids:
            return "child_lost"
        if any(not v.ever_found for v in lost):
            return "search_too_slow"
        if all(floor_of(v.room) >= 4 for v in lost):
            return "upper_floors_lost"
        if any(v.refused >= 2 for v in lost):
            return "refusals_cost_lives"
        return "mixed_outcome"

    def finish(self, reason):
        if self.ended:
            return
        self.ended = True
        self.end_reason = reason
        t0 = self.now
        if reason == "time_up":
            self.brigade(t0)
        else:
            for v in self.victims.values():
                if not v.resolved:
                    self.emit(v, "status", {"victim_status": "trapped", "target": "end"}, t=t0 + 0.2)
        self.ending = self.compute_ending(reason)
        rescued = sum(1 for v in self.victims.values() if v.status == "rescued")
        lost = sum(1 for v in self.victims.values() if v.status == "lost")
        text = f"{rescued} rescued, {lost} lost, {len(self.victims) - rescued - lost} still inside. {self.ending.replace('_', ' ')}."
        self.emit(self.director, "speak", {"utterance": text}, None, None, None, t=t0 + 1.0)
        self.emit(self.director, "world_event", {"world": {"type": "ending", "label": self.ending}},
                  f"The night ends: {self.ending.replace('_', ' ')} ({reason.replace('_', ' ')}).", None, None, t=t0 + 1.2)
        verdict = self.approver.verdict(rescued, lost)
        self.emit(self.human, "approval",
                  {"action": verdict, "approval_of_seq": None, "verdict": True, "note": f"outcome verdict: {rescued} rescued / {lost} lost"},
                  None, None, None, t=t0 + 4.0)
        self.learn()

    def learn(self):
        m = self.memory
        if self.flags.get("child_bolted"):
            m["cautious_briefing"] = True
            m["bolt_prob"] = round(max(0.25, m.get("bolt_prob", 0.55) - 0.08), 3)
            m["found_prob"] = round(min(0.8, m.get("found_prob", 0.75) + 0.04), 3)
        if self.victims["victim-child"].status != "rescued":
            m["child_losses"] = m.get("child_losses", 0) + 1
        m["runs"] = m.get("runs", 0) + 1
