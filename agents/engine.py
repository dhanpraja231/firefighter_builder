"""Story engine entry point: `run_story(seed, memory, policy)`.

The fixed setup (the SPEC's opening event): a night-time grease fire in the floor-3 kitchen of a five-story
apartment block, eight residents (personas/*.json), a commander, a scout drone, a hose robot, a rescue
robot, a Director, and a human on the loop. Everything after that is decided by the agents' policies and by
the physics. Same seed + heuristic policy => identical run; different seeds => different people, different
fire, different choices, different endings.
"""

from __future__ import annotations

import itertools
import random
import uuid

from policy import HeuristicPolicy
from sim_actions import ActionsMixin
from sim_core import Actor, Approver, CoreMixin, VICTIM_START, Victim, load_personas
from sim_options import OptionsMixin, roll_traits
from world import ROOMS, World

DEFAULT_MEMORY = {"runs": 0, "child_losses": 0, "cautious_briefing": False, "bolt_prob": 0.55, "found_prob": 0.75}


class Sim(CoreMixin, OptionsMixin, ActionsMixin):
    def __init__(self, seed, memory, policy):
        self.seed, self.memory, self.policy = seed, memory, policy
        self.rng = random.Random(f"world:{seed}")
        self.world = World(self.rng)
        self.events: list[dict] = []
        self.now = 0.0
        self._last_t = 0.0
        self._q: list = []
        self._cnt = itertools.count()
        self.radio: list[str] = []
        self.dirty = False
        self.scanned: set[str] = set()
        self.scan_count: dict[str, int] = {}
        self.twists: list[str] = []
        self.last_twist_t = -99.0
        self.last_ladder_t = -99.0
        self.alerts: list[str] = []
        self.adapt = {"reroute": 0, "abandon": 0, "reprioritize": 0}
        self.ignition_count = 0
        self.rescued_order: list[str] = []
        self.flags: dict = {}
        self.power_back = 0.0
        self.ended = False
        self.ending = None
        self.end_reason = None
        self.approver = Approver(seed)
        self.brigade_eta = random.Random(f"eta:{seed}").uniform(110.0, 158.0)  # when the human fire brigade gets there

        personas = load_personas()
        traits = roll_traits(seed, VICTIM_START)
        self.commander = Actor("commander", "commander", "exterior-command", 1.0, seed, "robot")
        self.scout = Actor("scout-1", "scout", "exterior-engine", 4.5, seed, "robot")
        self.hose = Actor("hose-1", "suppression", "exterior-engine", 3.0, seed, "robot")
        self.rescue = Actor("rescue-1", "rescue", "exterior-engine", 3.6, seed, "robot")
        self.director = Actor("director", "director", "exterior-command", 1.0, seed, "director")
        self.human = Actor("human", "human", "exterior-command", 1.0, seed, "human")
        self.robots = [self.scout, self.hose, self.rescue]
        self.robots_by_id = {r.id: r for r in self.robots}
        self.commander.traits = traits["commander"]
        for r in self.robots:
            r.traits = traits[r.id]
        self.director.traits = {}
        self.victims = {}
        for vid, room in VICTIM_START.items():
            v = Victim(vid, room, personas[vid], seed)
            v.traits = traits[vid]
            v.panic = v.traits["panic"] * 0.5
            self.victims[vid] = v
        # a few residents have locked themselves in (needs a breach, which needs the human)
        for room in sorted({v.room for v in self.victims.values()}):
            if self.rng.random() < 0.3:
                self.world.locked.add(room)

    def start(self):
        w = self.world
        w.ignite("3-kitchen", 0.25, 0.0)
        w._rep_fire["3-kitchen"] = 0.25
        self.world_event({"type": "fire", "roomId": "3-kitchen", "intensity": 0.25}, "A grease fire starts on the stove in the floor 3 kitchen.")
        w.smoke["3-kitchen"] = 0.2
        w._rep_smoke["3-kitchen"] = 0.2
        self.world_event({"type": "smoke", "roomId": "3-kitchen", "intensity": 0.2}, "Smoke rolls off the stove.")
        self.spawn(self.physics_proc(), 1.0)
        self.spawn(self.commander_proc(), 0.0)
        self.spawn(self.director_proc(), 0.0)
        for r, start in ((self.scout, 1.5), (self.hose, 2.5), (self.rescue, 3.0)):
            self.spawn(self.robot_proc(r, start), 0.0)


def make_policy(name):
    """`name`: 'heuristic', 'llm', 'auto' (llm if RUNWARE_API_KEY and RUNWARE_MODEL are set), or a Policy object."""
    if not isinstance(name, str):
        return name
    if name in ("llm", "auto"):
        from llm import LLMPolicy
        p = LLMPolicy()
        if p.available() or name == "llm":
            return p
    return HeuristicPolicy()


def policy_label(policy) -> str:
    avail = getattr(policy, "available", None)
    return "llm" if (callable(avail) and avail()) else "heuristic"


class LiveRun:
    """One story, produced incrementally. Iterate it to receive each event the moment the agents decide it
    (with the LLM policy, each agent call happens as the story advances). Events come out in non-decreasing
    t_sim. After the iterator is exhausted, `.result` holds the run-level info (events, ending, policy,
    stats, run_id, memory); before that it is None. `run_id`, `policy` and `seed` are known immediately."""

    def __init__(self, seed: int, memory: dict | None = None, policy="auto"):
        memory = memory if memory is not None else dict(DEFAULT_MEMORY)
        for k, v in DEFAULT_MEMORY.items():
            memory.setdefault(k, v)
        # Learning is real but never guarantees a good run: keep a floor of genuine variance in the persisted values.
        memory["bolt_prob"] = round(max(0.25, float(memory["bolt_prob"])), 3)
        memory["found_prob"] = round(min(0.8, float(memory["found_prob"])), 3)
        self.seed, self.memory = seed, memory
        self._pol = make_policy(policy)
        self.policy = policy_label(self._pol)
        self.run_id = str(uuid.uuid4())
        self.sim = Sim(seed, memory, self._pol)
        self.result: dict | None = None
        self._started = False

    def __iter__(self):
        if self._started:
            raise RuntimeError("a LiveRun can only be iterated once")
        self._started = True
        return self._events()

    def _events(self):
        sim, sent = self.sim, 0
        sim.start()
        while sent < len(sim.events):
            yield sim.events[sent]
            sent += 1
        for _ in sim.steps():
            while sent < len(sim.events):
                yield sim.events[sent]
                sent += 1
        if not sim.ended:
            sim.finish("time_up")
        while sent < len(sim.events):
            yield sim.events[sent]
            sent += 1
        self.result = self._summary()

    def _summary(self) -> dict:
        sim, pol = self.sim, self._pol
        vs = sim.victims
        stats = {
            "ignitions": sim.ignition_count,
            "rooms_burned": sum(1 for r in ROOMS if sim.world.ignited_at.get(r) is not None),
            "adapt": dict(sim.adapt),
            "twists": list(sim.twists),
            "rescue_order": list(sim.rescued_order),
            "lost": [v.id for v in vs.values() if v.status == "lost"],
            "left_inside": [v.id for v in vs.values() if not v.resolved],
            "duration": sim.events[-1]["t_sim"],
            "llm_fallbacks": getattr(pol, "fallbacks", 0),
        }
        return {"events": sim.events, "memory": self.memory, "run_id": self.run_id, "ending": sim.ending,
                "policy": self.policy, "stats": stats}


def iter_run(seed: int, memory: dict | None = None, policy="auto") -> LiveRun:
    """Incremental story: `for event in iter_run(seed): ...`, then read `.result` once exhausted."""
    return LiveRun(seed, memory, policy)


def run_story(seed: int, memory: dict | None = None, policy="auto") -> dict:
    """Whole-run convenience: drains iter_run and returns the result dict (same shape as before)."""
    run = LiveRun(seed, memory, policy)
    for _ in run:
        pass
    return run.result
