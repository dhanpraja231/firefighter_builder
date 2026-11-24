"""Agent policies: observation + legal options -> one decision.

The engine (engine.py) enumerates the legal options for an agent at a moment
and hands them over with an observation dict. A policy picks one. Two
implementations: `HeuristicPolicy` (persona/role-driven utilities with seeded
randomness, no network) and `LLMPolicy` in llm.py (same interface, backed by an
OpenAI-compatible chat endpoint, falling back to the heuristic on any error).

Option dict: {"i": int, "action": str, "target": str|None, "risky": bool,
              "label": str, "meta": {...}}
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

TACTICS = ("order", "reassure", "bargain", "social_proof", "stream_cutoff", "reunite", "promise_slow", "carry")


@dataclass
class Decision:
    index: int
    utterance: str | None = None
    reasoning: str = ""
    confidence: float = 0.7
    model: str | None = None
    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    extra: dict = field(default_factory=dict)


class Policy(Protocol):
    name: str

    def decide(self, agent_id: str, role: str, obs: dict, options: list[dict], rng) -> Decision: ...


def softmax_pick(scores: list[float], temp: float, rng) -> int:
    m = max(scores)
    weights = [math.exp((s - m) / temp) for s in scores]
    r = rng.random() * sum(weights)
    acc = 0.0
    for i, w in enumerate(weights):
        acc += w
        if r <= acc:
            return i
    return len(scores) - 1


# -- persona reading -------------------------------------------------------

def tactic_fit(persona: dict) -> set[str]:
    """Which tactics the persona card says will work, read from its `compliance` text."""
    text = (persona.get("compliance", "") + " " + persona.get("goal", "")).lower()
    fits: set[str] = set()
    if "cat" in text or "agrees to look" in text:
        fits.add("bargain")
    if "stream" in text:
        fits.add("stream_cutoff")
    if "help someone else" in text or "someone else first" in text:
        fits.add("social_proof")
    if "child is confirmed found" in text or "parent is visibly present" in text:
        fits.add("reunite")
    if "go slow" in text:
        fits.add("promise_slow")
    if "unless the other" in text or "separated" in text or "stay together" in text:
        fits.add("reassure")
    if "first ask" in text and "refuses" not in text.split("first ask")[0][-40:]:
        fits.add("order")
    return fits


# -- spoken lines ----------------------------------------------------------

def _pick(rng, options):
    return options[int(rng.random() * len(options)) % len(options)]


ROBOT_LINES = {
    "scan_room": ["Scanning {room}.", "Sweeping {room}, thermal on.", "Moving to {room}, scanning."],
    "found": ["Contact in {room}. Someone's here.", "Found a person in {room}.", "Heat signature in {room}, it's a person."],
    "clear": ["{room} is clear.", "Nobody in {room}, moving on."],
    "spray": ["Putting water on {room}.", "Suppressing {room}, holding the line."],
    "close_door": ["Closing the door at {room} to starve the fire.", "Door at {room} shut."],
    "vent": ["Requesting to vent {room}, I know the risk.", "Venting {room} would clear the route. Asking approval."],
    "ladder": ["Ladder going up to {room}.", "Raising the aerial to {room}."],
    "breach": ["Door to {room} is locked. Requesting approval to breach.", "Locked room. I need to breach, requesting approval."],
    "unstable": ["That flight is weakened. Requesting approval to cross.", "Stair is flagged unstable. Asking to cross."],
    "evacuate": ["Bringing {n} out now.", "Heading for the exit with {n}."],
    "out": ["{n} clear of the building.", "Exit reached, {n} safe on the sidewalk."],
}

PERSUADE_LINES = {
    "order": ["{name}, this is rescue-1. You need to leave right now.", "{name}, evacuate now. Follow me."],
    "reassure": ["{name}, I know it's frightening. I'll stay right beside you.", "{name}, stay calm. I'm here, we'll do this together."],
    "bargain": ["{name}, I'll deal with what you're worried about on the way out. Come with me first.", "{name}, if you come now I'll go back for what matters to you."],
    "social_proof": ["{name}, others from the lower floors are already outside, safe. Same route.", "{name}, I got someone out a minute ago. I can do it for you."],
    "stream_cutoff": ["{name}, the power's about to go, and the stream goes with it. Let's move.", "{name}, they'll cut your signal anyway. Come on."],
    "reunite": ["{name}, your family is found. They're waiting for you. Come with me.", "{name}, I've seen them, they're okay. Follow me to them."],
    "promise_slow": ["{name}, we'll go slow, I promise. Take my hand.", "{name}, no rushing. One step at a time, I won't let go."],
    "carry": ["{name}, apologies, I'm lifting you now.", "{name}, there's no time. I'm carrying you."],
}

COMMANDER_LINES = {
    "sweep": ["Scout, sweep floor {floor} and report.", "Scout-1, take floor {floor}. Call out anyone you find."],
    "rescue": ["Rescue-1, priority is {name} in {room}.", "Rescue-1, go to {name}, {room}. Move."],
    "suppress": ["Hose-1, hold {room}. Keep the route open.", "Hose-1, knock down the fire in {room}."],
    "ladder": ["Hose-1, put the aerial on {room}. Stairs won't work.", "Hose-1, ladder to {room}, now."],
    "rescue_support": ["Hose-1, drop the line and help rescue-1 with {name}.", "Hose-1, support the extraction of {name}."],
    "retreat": ["All units, withdraw. It's no longer survivable inside.", "Pull back. Everyone out, that's an order."],
}

VICTIM_LINES = {
    "victim-elderly": {
        "comply": ["Well... if you'll look for my cat. Then I'll come.", "All right, dear. Slowly, please."],
        "refuse": ["Not without my cat.", "I won't leave Whiskers behind."],
        "stall": ["Give me a moment, my legs..."],
        "help": ["Hello? Is anyone there?"],
    },
    "victim-teen": {
        "comply": ["Fine, fine. The stream's dying anyway.", "Okay okay, I'm coming. Chat's going to be so mad."],
        "refuse": ["One sec, I'm live. This is insane.", "No way, hold on, I'm getting the shot."],
        "stall": ["Wait wait wait, almost done."],
        "help": ["Uh, guys? It's getting real. Hello?"],
    },
    "victim-skeptic": {
        "comply": ["...Fine. I saw what you did for the others. Lead on.", "Alright. Don't make me regret this."],
        "refuse": ["I'll wait for an actual firefighter, thanks.", "A robot? You're kidding."],
        "stall": ["I'm thinking about it. Don't rush me."],
        "help": ["Hey! Somebody! Anybody?"],
    },
    "victim-parent": {
        "comply": ["Okay. Okay, we go. Is my child with you?", "Yes, yes, let's go, quickly."],
        "refuse": ["I'm not going anywhere without my child.", "Where is my child? I'm not leaving."],
        "stall": ["Wait, I need to find them."],
        "help": ["My child! Has anyone seen my child?"],
    },
    "victim-child": {
        "comply": ["...Okay. Don't let go.", "Okay. Go slow."],
        "refuse": ["No! You're too loud.", "I'm not going with you."],
        "bolt": ["No!"],
        "stall": ["I want mom."],
        "help": ["Mommy? Mommy!"],
    },
    "victim-regular": {
        "comply": ["Got it. Lead the way.", "Sure, let's move."],
        "refuse": ["Give me a second."],
        "stall": ["One moment."],
        "help": ["Hey! I'm up here!"],
    },
    "victim-couple-a": {
        "comply": ["We're coming together, right?", "Okay, we're ready. Both of us."],
        "refuse": ["Not unless we go together.", "We're not splitting up."],
        "stall": ["Give us a second."],
        "help": ["Hello? We're in here!"],
    },
    "victim-couple-b": {
        "comply": ["Together. Please, together.", "Okay, okay. We go now."],
        "refuse": ["I'm not leaving without them.", "Together or not at all."],
        "stall": ["I can't, not yet."],
        "help": ["Help us!"],
    },
}


def robot_line(rng, key: str, **ctx) -> str:
    return _pick(rng, ROBOT_LINES[key]).format(**ctx)


# -- the heuristic policy --------------------------------------------------

class HeuristicPolicy:
    name = "heuristic-policy-v1"

    def decide(self, agent_id: str, role: str, obs: dict, options: list[dict], rng) -> Decision:
        if role == "victim":
            return self._victim(agent_id, obs, options, rng)
        if role == "director":
            return self._director(obs, options, rng)
        scores, why = [], []
        for opt in options:
            s, w = self._score(agent_id, role, obs, opt, rng)
            scores.append(s + rng.random() * 0.15)
            why.append(w)
        temp = 0.28 if role in ("rescue", "suppression") else 0.22
        i = softmax_pick(scores, temp, rng)
        opt = options[i]
        return Decision(
            index=i,
            utterance=self._utterance(agent_id, role, obs, opt, rng),
            reasoning=why[i],
            confidence=round(max(0.3, min(0.95, 0.55 + 0.25 * (scores[i] - sorted(scores)[-2 if len(scores) > 1 else 0]) + rng.random() * 0.1)), 2),
            model=self.name,
        )

    # ---- scoring -------------------------------------------------------
    def _score(self, agent_id, role, obs, opt, rng):
        m, a = opt["meta"], opt["action"]
        traits = obs.get("traits", {})
        if a == "hold":
            if role == "commander":
                return 0.75, "No change to the plan; the assignments still fit what we see."
            return 0.2, "Nothing better to do right now, holding position."
        if a == "retreat":
            if obs["t"] < 55:
                return -9.0, "Too early to pull out."
            s = (-1.9 + 2.0 * traits.get("caution", 0.5) * m["danger_mean"] + 1.5 * (1 - m["min_integrity"]) + 0.2 * m.get("lost", 0))
            return s, (f"Risk inside is high (danger {m['danger_mean']:.2f}, weakest unit at {m['min_integrity']:.0%}); weighing a withdrawal.")
        if a == "assign":
            return self._score_assign(obs, opt)
        if a == "scan_room":
            s = 0.55 + 0.7 * m["priority"] + 0.6 / (1 + m["dist"] / 10) - 1.3 * m["danger"] - (0.5 if m["rescan"] else 0.0)
            return s, f"{opt['label']}: {'rescan since nobody is accounted for' if m['rescan'] else 'unscanned'}, danger {m['danger']:.2f}."
        if a == "spray":
            s = (0.35 + (0.9 + 1.2 * m.get("fire_w", 0.33)) * m["fire"] + 0.5 * m["near_victim"] + 0.9 * m.get("threat", 0.0) + 0.5 * m["route"]
                 - 0.025 * m["dist"] - (1.2 - traits.get("caution", 0.5)) * 0.6 * (m["fire"] > 0.75))
            return s, f"{opt['label']}: fire {m['fire']:.2f}{', near a victim' if m['near_victim'] else ''}."
        if a == "spray_exterior":
            return 0.25 + 0.9 * m["fire"] + 0.5 * m["near_victim"], f"Safe stand-off spray on {opt['label']}, fire {m['fire']:.2f}."
        if a == "close_door":
            return 0.3 + 0.9 * m["fire"], f"Shutting the door starves {opt['label']} of air."
        if a == "vent":
            s = 0.2 + 0.9 * m["smoke_route"] - 0.9 * traits.get("caution", 0.5) - 0.8 * m["fire"]
            return s, f"Venting {opt['label']} would clear smoke, but it is a backdraft risk."
        if a == "deploy_ladder":
            s = 0.1 + 1.6 * m["cut_victims"] + 0.9 * m["victim_here"] + 0.25 * m["victims_above"]
            return s, f"Ladder to {opt['label']}: {m['victims_above']} people above, stairs {'cut' if m['stairs_cut'] else 'open'}."
        if a == "fetch":
            courage, empathy, obey = traits.get("courage", 0.6), traits.get("empathy", 0.5), traits.get("obedience", 0.5)
            s = (0.45 + 1.3 * m["danger_dest"] + (0.15 + 0.9 * empathy) * m["vulnerable"] + (0.2 + 1.0 * obey) * m["assigned"] - 0.022 * m["eta"]
                 - (1.4 - 1.0 * courage) * m["danger_path"] - 0.35 * m["locked"] - 0.4 * m["unstable"] - 0.9 * m["denied"]
                 - (2.5 if m["followers"] >= 3 else 0.0) + 0.5 * m["on_the_way"])
            return s, (f"{m['name']} in {pretty_room(m['room'])}: eta {m['eta']:.0f}s, danger at destination {m['danger_dest']:.2f}"
                       f"{', door is locked' if m['locked'] else ''}.")
        if a == "abandon":
            courage = traits.get("courage", 0.6)
            s = -1.2 + 3.5 * max(0.0, m["danger_dest"] - 0.7) * (1.3 - courage) + 2.2 * max(0.0, m["danger_path"] - 0.7) * (1.3 - courage)
            return s, f"{m['name']} is behind fire (destination {m['danger_dest']:.2f}, route {m['danger_path']:.2f}); the odds of getting through are poor."
        if a == "persuade":
            fit = opt["meta"]["fits"]
            exp_err = 0.0 if (m["victim"] == "victim-child" and obs["memory"].get("cautious_briefing")) else 0.25
            informed = fit and rng.random() > exp_err
            s = 0.9 + (1.5 if informed else 0.0) - (1.0 if m["tried"] else 0.0)
            if m["tactic"] == "carry":
                s = 0.05 + 0.7 * m["urgency"] + 0.5 * min(m["refused"], 2) - (0.8 if m["victim"] == "victim-child" else 0.0)
            if m["tactic"] == "order":
                s -= 0.25
            return s, f"Trying '{m['tactic']}' on {m['name']}" + (" because their card says it works." if informed else ", the best I have so far.")
        if a == "evacuate":
            s = (0.2 + 0.6 * m["followers"] + (1.6 if m["others_waiting"] == 0 else 0.0) + 1.4 * (1 - m["min_health"])
                 - 0.8 * m["danger_path"] + 0.5 * (m["followers"] >= 3))
            return s, f"{m['followers']} with me; exit is {m['eta']:.0f}s away, weakest at {m['min_health']:.0%} health."
        if a == "evacuate_ladder":
            return 1.1 + 0.8 * m["followers"], "The ladder is up at this window, quicker than the stairs."
        return 0.1, "Default."

    def _score_assign(self, obs, opt):
        m = opt["meta"]
        t = m["task"]
        if t == "rescue":
            cw = obs["traits"].get("w", {"danger": 0.34, "vulnerable": 0.33, "near": 0.33})
            alert = 0.5 if any(m["name"].split()[0].lower() in al.lower() or m["room"] in al for al in obs.get("alerts", [])) else 0.0
            s = (0.55 + 4.5 * cw["danger"] * m["danger"] + 2.7 * cw["vulnerable"] * m["vulnerable"] + 2.4 * cw["near"] * m["near"]
                 + 0.3 * min(m["waiting"] / 30.0, 1.0) - 0.5 * m["covered"] + alert)
            return s, f"{m['name']} in {pretty_room(m['room'])} is the most exposed; danger {m['danger']:.2f}."
        if t == "sweep":
            s = 0.45 + 0.7 * m["unscanned"] + 0.45 * m["near_fire"] + 0.35 * m["unfound"]
            return s, f"Floor {m['floor']} is {m['unscanned']:.0%} unscanned; people are still unaccounted for."
        if t == "suppress":
            return 0.35 + 1.3 * m["fire"] + 0.5 * m["route"], f"Fire at {pretty_room(m['room'])} ({m['fire']:.2f}) threatens the route."
        if t == "ladder":
            return 0.2 + 1.8 * m["cut_victims"] + 0.4 * m["victim_here"], "Stairs are cut and people are above; the ladder is the way out."
        if t == "rescue_support":
            return 0.1 + 1.5 * m["pressure"] + (1.5 if m["rescue_down"] else 0.0), "More people are waiting than one rescuer can carry out."
        return 0.1, "Default."

    # ---- spoken lines for the chosen option --------------------------------
    def _utterance(self, agent_id, role, obs, opt, rng):
        a, m = opt["action"], opt["meta"]
        if a == "scan_room":
            return robot_line(rng, "scan_room", room=pretty_room(opt["target"]))
        if a == "assign":
            return _pick(rng, COMMANDER_LINES[m["task"]]).format(
                floor=m.get("floor"), name=m.get("name"), room=pretty_room(m["room"]) if m.get("room") else "")
        if a == "retreat":
            return _pick(rng, COMMANDER_LINES["retreat"])
        if a == "spray":
            return robot_line(rng, "spray", room=pretty_room(opt["target"]))
        if a == "spray_exterior":
            return robot_line(rng, "spray", room=pretty_room(opt["target"]))
        if a == "close_door":
            return robot_line(rng, "close_door", room=pretty_room(opt["target"]))
        if a == "vent":
            return robot_line(rng, "vent", room=pretty_room(opt["target"]))
        if a == "deploy_ladder":
            return robot_line(rng, "ladder", room=pretty_room(opt["target"]))
        if a == "persuade":
            line = _pick(rng, PERSUADE_LINES[m["tactic"]]).format(name=m["name"])
            if m["tactic"] == "bargain" and "cat" in m.get("goal", ""):
                line = f"{m['name']}, I'll look for your cat on the way out. Let's get you down first."
            return line
        if a == "evacuate":
            return robot_line(rng, "evacuate", n=m["followers"])
        return None

    # ---- victims -------------------------------------------------------
    def _victim(self, vid, obs, options, rng):
        kinds = {o["action"]: i for i, o in enumerate(options)}
        if "comply" in kinds:
            return self._victim_reply(vid, obs, options, kinds, rng)
        return self._victim_flee(vid, obs, options, rng)

    def _victim_reply(self, vid, obs, options, kinds, rng):
        c = obs["ctx"]
        t = obs["tactic"]
        mem = obs["memory"]
        refused = c["refused"]
        warm = min(0.3, 0.12 * refused) + 0.25 * c["panic"] + 0.15 * c["smoke"]
        bolt_p = 0.0
        if vid == "victim-elderly":
            p = {"bargain": 0.93, "carry": 0.55}.get(t, 0.1 + (0.2 if refused >= 2 else 0.0))
        elif vid == "victim-teen":
            p = {"stream_cutoff": 0.9, "social_proof": 0.55, "reassure": 0.35, "carry": 0.6}.get(t, 0.2)
            if c["robot_in_frame"]:
                p += 0.15
        elif vid == "victim-regular":
            p = 0.9
        elif vid == "victim-skeptic":
            if c["helped_before"]:
                p = 0.85 if t == "social_proof" else 0.6
            else:
                p = 0.55 if t == "carry" else 0.1
        elif vid == "victim-parent":
            if c["child_ok"]:
                p = 0.92 if t == "reunite" else 0.7
            else:
                p = 0.05 if t != "carry" else 0.4
        elif vid == "victim-child":
            bolt_p = mem.get("bolt_prob", 0.55) * (1.0 if t in ("order", "carry") else 0.15)
            if t == "promise_slow":
                p = 0.88
            elif t == "reassure":
                p = 0.62 if mem.get("cautious_briefing") else 0.3
            elif t == "reunite":
                p = 0.8 if c["parent_here"] else 0.15
            elif t == "carry":
                p = 0.25
            else:
                p = 0.4 * (1 - bolt_p)
            if c["parent_here"]:
                p += 0.15
        elif vid in ("victim-couple-a", "victim-couple-b"):
            p = (0.78 if t == "reassure" else 0.6) if c["partner_here"] else 0.05
        else:
            p = 0.5
        p = min(0.97, p + warm)
        u = rng.random()
        if u < p:
            key = "comply"
            why = f"{t.replace('_', ' ')} works on me ({p:.0%}); I'll go."
        elif u < p + bolt_p and "bolt" in kinds:
            key = "bolt"
            why = "That scared me. I'm running."
        elif rng.random() < 0.18 and "stall" in kinds:
            key = "stall"
            why = "I'm not ready yet."
        else:
            key = "refuse"
            why = f"'{t.replace('_', ' ')}' doesn't change my mind."
        lines = VICTIM_LINES.get(vid, {}).get(key) or ["..."]
        return Decision(index=kinds[key], utterance=_pick(rng, lines), reasoning=why, confidence=round(0.5 + 0.4 * rng.random(), 2), model=self.name)

    def _victim_flee(self, vid, obs, options, rng):
        scores = []
        for o in options:
            m = o["meta"]
            if o["action"] == "flee":
                scores.append(0.4 + 1.5 * (obs["ctx"]["danger_here"] - m["danger"]) - 0.1 * m["dist"] / 5)
            elif o["action"] == "hide":
                scores.append(0.4 + (0.8 if vid == "victim-child" else 0.0))
            else:
                scores.append(0.2)
        i = softmax_pick(scores, 0.3, rng)
        key = options[i]["action"]
        lines = VICTIM_LINES.get(vid, {}).get("help") or ["Help!"]
        return Decision(index=i, utterance=_pick(rng, lines) if key == "flee" else None,
                        reasoning=("Smoke and heat are building here, getting out of this room." if key == "flee"
                                   else "Staying put." if key == "stay" else "Hiding until it is quiet."),
                        confidence=0.6, model=self.name)

    # ---- director ------------------------------------------------------
    def _director(self, obs, options, rng):
        scores, why = [], []
        for o in options:
            m = o["meta"]
            if o["action"] == "none":
                scores.append(1.9)
                why.append("Let the agents' choices play out.")
            else:
                scores.append(m["score"] + rng.random() * 0.25)
                why.append(m["why"])
        i = softmax_pick(scores, 0.3, rng)
        return Decision(index=i, reasoning=why[i], confidence=0.65, model=self.name)


def pretty_room(room: str | None) -> str:
    if not room:
        return ""
    if room.startswith("exterior-"):
        return room.split("-", 1)[1]
    f, k = room.split("-", 1)
    return f"floor {f} {k.replace('-', ' ')}"
