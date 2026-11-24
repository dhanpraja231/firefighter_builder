"""Tick-based fire rescue sim. One tick = 1 s of sim time.

The world runs on its own clock: fire grows and spreads room to room, smoke
rises up the stairwell, victims lose air, and the building collapses at
SPREAD["collapse_s"]. Agents only change the outcome through the choices they
make at decision points, so a run can be lost.

Decision points (each one calls `decide(...)`, which is the LLM or a rule):
- commander: when the rescue robot or the ladder truck is free, which found victim unit to go for
- rescue-1: on reaching a unit, how to approach them (options depend on the persona)
- hose-1: every HOSE_EVERY seconds, which room to fight, or ask the human to vent a floor

Events use the same shape as orchestrator.EventLog, so the 3D scene, the API
and Bruin need no changes.
"""

import heapq
import random
from concurrent.futures import ThreadPoolExecutor

SPREAD = {
    "origin": "3-kitchen",
    "origin_fire": 0.35,
    "grow": 0.05,            # fire growth per second in a burning room
    "ignite_at": 0.3,        # a room spreads fire once it is this hot
    "ignite_side": 0.12,     # chance per second to ignite each same-floor neighbor
    "ignite_up": 0.20,       # chance per second to ignite the room directly above
    "ignite_down": 0.02,     # fire rarely spreads down the stairs
    "smoke_from_fire": 0.04, # smoke pushed into neighbors per second, scaled by fire
    "smoke_up": 0.03,        # smoke carried up each stair flight per second, scaled by hall smoke
    "bedroom_door": 0.5,     # bedrooms (closed doors) take in smoke at this fraction
    "spray": 0.15,           # fire removed per second by the hose robot
    "impassable": 0.8,       # rooms hotter than this can't be walked through
    "collapse_s": 150,
}
AIR_DRAIN = {"base": 0.3, "smoke": 2.2, "fire": 7.0}
EDGE_S, STAIR_S, ESCORT = 3.0, 5.0, 1.5
SCOUT_EDGE_S, SCOUT_STAIR_S, SCOUT_SCAN_S = 1.0, 2.0, 2.0
LADDER_S = 24.0
HOSE_EVERY = 15
FLOORS = range(1, 6)
KINDS = ["living", "kitchen", "bedroom-w", "bedroom-e", "hall", "landing"]
EXIT = "exit"

# Starting rooms (from the scripted version and story/characters.md). Pairs move as one unit.
UNITS = {
    "victim-teen": {"members": ["victim-teen"], "room": "1-living", "label": "the teen"},
    "victim-elderly": {"members": ["victim-elderly"], "room": "2-bedroom-w", "label": "Mrs. Okafor"},
    "victim-couple": {"members": ["victim-couple-a", "victim-couple-b"], "room": "2-bedroom-e", "label": "the couple"},
    "victim-skeptic": {"members": ["victim-skeptic"], "room": "3-bedroom-w", "label": "the skeptic"},
    "victim-family": {"members": ["victim-parent", "victim-child"], "room": "4-bedroom-e", "label": "the parent and child"},
    "victim-regular": {"members": ["victim-regular"], "room": "5-living", "label": "the neighbor"},
}
# How the rescue robot can approach each unit: option id -> (description, extra seconds before they move).
APPROACHES = {
    "victim-teen": {"order": ("Tell them firmly to leave now", 8), "stream": ("Point out the stream dies with the router; film on the way out", 3)},
    "victim-elderly": {"order": ("Order her out now", 12), "promise_cat": ("Promise to look for the cat after she is out", 4),
                       "carry": ("Pick her up and carry her (slower walk out)", 2)},
    "victim-couple": {"together": ("Take them out together", 3), "hurry": ("Rush them, separate if needed", 1)},
    "victim-skeptic": {"order": ("Order them out", 4), "explain": ("Explain calmly what is happening and why", 8),
                       "show_rescues": ("Tell them who the robots already got out", 2)},
    "victim-family": {"order": ("Tell the family to move now", 2), "gentle": ("Go slow with the child, hold their hand", 6)},
    "victim-regular": {"guide": ("Give directions and walk them out", 1)},
}
LADDER_ROOMS = {"living": "window-living-w", "bedroom-w": "window-bed-w", "bedroom-e": "window-bed-e-n", "landing": "window-landing-n"}


def rid(f, k):
    return f"{f}-{k}"


def floor_of(room):
    return int(room.split("-", 1)[0]) if room != EXIT else 0


def kind_of(room):
    return room.split("-", 1)[1]


def build_graph():
    g = {}

    def link(a, b, s):
        g.setdefault(a, {})[b] = s
        g.setdefault(b, {})[a] = s

    for f in FLOORS:
        for a, b in [("hall", "living"), ("hall", "kitchen"), ("living", "bedroom-w"), ("kitchen", "bedroom-e"),
                     ("bedroom-w", "landing"), ("bedroom-e", "landing")]:
            link(rid(f, a), rid(f, b), EDGE_S)
        if f < 5:
            link(rid(f, "hall"), rid(f + 1, "hall"), STAIR_S)
    link(EXIT, "1-hall", EDGE_S)
    return g


class World:
    def __init__(self, seed, decide, lessons_by_role, history_line, log, pos, ext, stairs=None):
        self.stairs = stairs  # orchestrator._stair_climb: waypoints along the switchback between two floors
        self.rng = random.Random(seed)
        self.decide = decide
        self.lessons = lessons_by_role
        self.history = history_line
        self.log, self.pos, self.ext = log, pos, ext
        self.g = build_graph()
        self.blocked = set()
        self.fire = {r: 0.0 for r in self.g if r != EXIT}
        self.smoke = {r: 0.0 for r in self.g if r != EXIT}
        self.fire[SPREAD["origin"]] = SPREAD["origin_fire"]
        self.emitted = {}
        self.t = 0
        self.units = {u: {**d, "status": "trapped", "found": False, "air": {m: 100.0 for m in d["members"]},
                          "lost": {}, "busy": False} for u, d in UNITS.items()}
        self.rescued_any = False
        self.robot = {"at": EXIT, "task": None}
        self.ladder = {"busy_until": None, "unit": None}
        self.hose = {"at": EXIT, "target": None, "next_decision": 4}
        self.scout_plan = self._scout_plan()
        self.collapse_t = self.rng.randint(50, 90) if self.rng.random() < 0.65 else None
        self.decisions = []  # (t, agent, choice, options) for the debrief
        self.pending_vent = None

    # ---------- geometry ----------
    def room_pos(self, room):
        return self.ext("entry") if room == EXIT else self.pos(floor_of(room), kind_of(room))

    def path(self, a, b):
        dist, prev, pq = {a: 0.0}, {}, [(0.0, a)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == b:
                break
            if d > dist.get(u, 1e9):
                continue
            for v, w in self.g[u].items():
                if frozenset((u, v)) in self.blocked:
                    continue
                if v not in (a, b) and v != EXIT and self.fire[v] > SPREAD["impassable"]:
                    continue
                nd = d + w
                if nd < dist.get(v, 1e9):
                    dist[v], prev[v] = nd, u
                    heapq.heappush(pq, (nd, v))
        if b not in dist:
            return None, None
        p = [b]
        while p[-1] != a:
            p.append(prev[p[-1]])
        return list(reversed(p)), dist[b]

    def walk_stairs(self, a, b, step, agents):
        """Emit move waypoints along the visible stair flight for a hall-to-hall edge, spread over its travel time."""
        if not self.stairs or EXIT in (a, b) or kind_of(a) != "hall" or kind_of(b) != "hall" or floor_of(a) == floor_of(b):
            return
        pts = self.stairs(min(floor_of(a), floor_of(b)))
        if floor_of(b) < floor_of(a):
            pts = list(reversed(pts))
        for i, pt in enumerate(pts):
            for agent_id, role in agents:
                self.log._push(agent_id, role, "move", {"position": pt}, None, llm=False, dt=0)
                self.log.events[-1]["t_sim"] = round(self.t + step * (i + 1) / (len(pts) + 1), 1)

    # ---------- fire, smoke, air ----------
    def step_fire(self):
        S = SPREAD
        new_fire = dict(self.fire)
        for r, fv in self.fire.items():
            if fv <= 0:
                continue
            new_fire[r] = min(1.0, fv + S["grow"])
            if fv >= S["ignite_at"]:
                for n in self.g[r]:
                    if n == EXIT or self.fire[n] > 0:
                        continue
                    df = floor_of(n) - floor_of(r)
                    chance = S["ignite_up"] if df > 0 else S["ignite_down"] if df < 0 else S["ignite_side"]
                    if self.rng.random() < chance * fv:
                        new_fire[n] = 0.15
            for n in self.g[r]:
                if n != EXIT:
                    k = S["bedroom_door"] if kind_of(n).startswith("bedroom") else 1.0
                    self.smoke[n] = min(1.0, self.smoke[n] + S["smoke_from_fire"] * fv * k)
            self.smoke[r] = min(1.0, self.smoke[r] + S["smoke_from_fire"] * fv)
        for f in range(1, 5):  # smoke rises through the stair core
            lo, hi = rid(f, "hall"), rid(f + 1, "hall")
            self.smoke[hi] = min(1.0, self.smoke[hi] + S["smoke_up"] * self.smoke[lo])
            for k in ("landing", "living", "kitchen"):
                self.smoke[rid(f + 1, k)] = min(1.0, self.smoke[rid(f + 1, k)] + 0.01 * self.smoke[hi])
        tgt = self.hose["target"]
        if tgt and self.hose["at"] == rid(floor_of(tgt), "hall"):
            new_fire[tgt] = max(0.0, new_fire[tgt] - S["spray"])
        self.fire = new_fire
        for r in self.fire:
            for kind, val in (("fire", self.fire[r]), ("smoke", self.smoke[r])):
                last = self.emitted.get((kind, r), 0.0)
                if abs(val - last) >= 0.1 or (val == 0 and last > 0):
                    self.emitted[(kind, r)] = val
                    self.log.world({"type": kind, "roomId": r, "intensity": round(val, 2)}, None, dt=0)

    def step_air(self):
        for uid, u in self.units.items():
            if u["status"] in ("rescued", "lost"):
                continue
            room = u["room"]
            if room == EXIT:
                continue
            drain = AIR_DRAIN["base"] + AIR_DRAIN["smoke"] * self.smoke[room] + AIR_DRAIN["fire"] * self.fire[room]
            for m in u["members"]:
                if m in u["lost"]:
                    continue
                u["air"][m] -= drain
                if u["air"][m] <= 0:
                    cause = "fire" if self.fire[room] > 0.3 else "air"
                    u["lost"][m] = cause
                    self.log.status(m, "lost", "rescue-1", dt=0)
                    self.log.events[-1]["payload"]["cause"] = cause
            if len(u["lost"]) == len(u["members"]):
                u["status"] = "lost"

    # ---------- scout ----------
    def _scout_plan(self):
        plan, t = [], 0.0
        prev = EXIT
        for f in FLOORS:
            hall = rid(f, "hall")
            t += SCOUT_EDGE_S if prev == EXIT else SCOUT_STAIR_S
            plan.append((t, "move", hall))
            t += SCOUT_SCAN_S
            plan.append((t, "scan", f))
            prev = hall
        plan.append((t + 6, "move", EXIT))
        return plan

    def step_scout(self):
        while self.scout_plan and self.scout_plan[0][0] <= self.t:
            _, what, arg = self.scout_plan.pop(0)
            if what == "move":
                self.log.move("scout-1", "scout", self.room_pos(arg), dt=0)
                continue
            found = [u for uid, u in self.units.items() if floor_of(u["room"]) == arg and u["status"] == "trapped"]
            self.log.act("scout-1", "scout", "scan_floor", rid(arg, "hall"),
                         f"Thermal scan of floor {arg}: {len(found)} heat signature(s) that look like people.", dt=0)
            for u in found:
                u["found"] = True
                for m in u["members"]:
                    if m not in u["lost"]:
                        self.log.status(m, "found", "scout-1", dt=0)
            if found:
                self.log.speak("scout-1", "scout", f"Floor {arg}: " + ", ".join(f"{u['label']} in {u['room']}" for u in found) + ".",
                               None, dt=0)

    # ---------- observations ----------
    def secs_left(self):
        return SPREAD["collapse_s"] - self.t

    def unit_obs(self, uid, frm):
        u = self.units[uid]
        p, d = self.path(frm, u["room"])
        back, d2 = self.path(u["room"], EXIT)
        air = min(a for m, a in u["air"].items() if m not in u["lost"])
        trip = (d or 0) + (d2 or 0) * ESCORT
        return (f"{uid} ({u['label']}): room {u['room']}, lowest air {air:.0f}/100, fire {self.fire[u['room']]:.2f}, "
                f"smoke {self.smoke[u['room']]:.2f}, robot round trip about {trip:.0f}s"
                + (" (no path right now)" if p is None or back is None else "")
                + (f", ladder possible ({LADDER_S:.0f}s)" if kind_of(u["room"]) in LADDER_ROOMS and floor_of(u['room']) <= 4 else ""))

    def open_units(self):
        return [uid for uid, u in self.units.items() if u["found"] and u["status"] == "trapped" and not u["busy"]]

    def building_line(self):
        burning = [r for r, v in self.fire.items() if v > 0.2]
        smoky = sorted({floor_of(r) for r, v in self.smoke.items() if v > 0.4})
        blocked = " Stairs between floors 2 and 3 have collapsed." if self.blocked else ""
        return (f"t={self.t}s, {self.secs_left()}s until the building is unsafe. Burning rooms: {', '.join(burning) or 'none'}. "
                f"Heavy smoke on floors: {smoky or 'none'}.{blocked}")

    # ---------- decisions ----------
    def commander_requests(self):
        reqs = []
        units = self.open_units()
        if not units:
            return reqs
        if self.robot["task"] is None:
            # only units the robot can reach and bring down the stairs
            opts = [{"id": f"robot:{u}", "label": f"Send rescue-1 for {self.units[u]['label']}"} for u in units
                    if self.path(self.robot["at"], self.units[u]["room"])[0] is not None
                    and self.path(self.units[u]["room"], EXIT)[0] is not None]
            if opts:
                obs = self.building_line() + "\nrescue-1 is free at " + self.robot["at"] + ". Found and waiting:\n" + \
                      "\n".join(self.unit_obs(u, self.robot["at"]) for u in units)
                reqs.append(("commander", "commander", obs, opts, "robot"))
        if self.ladder["busy_until"] is None:
            opts = [{"id": f"ladder:{u}", "label": f"Ladder truck to {self.units[u]['label']}'s window"} for u in units
                    if kind_of(self.units[u]["room"]) in LADDER_ROOMS and floor_of(self.units[u]["room"]) <= 4]
            if opts:
                opts.append({"id": "ladder:hold", "label": "Keep the ladder truck in reserve"})
                obs = self.building_line() + "\nThe ladder truck is free (one window rescue takes about 24s). Found and waiting:\n" + \
                      "\n".join(self.unit_obs(u, EXIT) for u in units)
                reqs.append(("commander", "commander", obs, opts, "ladder"))
        return reqs

    def hose_request(self):
        if self.t < self.hose["next_decision"]:
            return []
        self.hose["next_decision"] = self.t + HOSE_EVERY
        burning = sorted((r for r, v in self.fire.items() if v > 0.1), key=lambda r: -self.fire[r])[:4]
        opts = [{"id": f"spray:{r}", "label": f"Fight the fire in {r} (fire {self.fire[r]:.2f})"} for r in burning]
        for f in FLOORS:
            if self.smoke[rid(f, "hall")] > 0.45 and self.pending_vent is None:
                opts.append({"id": f"vent:{f}", "label": f"Ask the human to approve venting floor {f} (clears smoke, may backdraft)"})
        if not opts:
            return []
        trapped = ", ".join(f"{u['label']} in {u['room']}" for u in self.units.values() if u["status"] == "trapped" and u["found"])
        obs = self.building_line() + f"\nhose-1 is at {self.hose['at']}, currently on {self.hose['target'] or 'nothing'}. People still inside: {trapped or 'none known'}."
        return [("hose-1", "suppression", obs, opts, "hose")]

    def run_decisions(self, reqs):
        if not reqs:
            return []
        with ThreadPoolExecutor(len(reqs)) as pool:
            outs = list(pool.map(lambda r: self.decide(r[0], r[1], r[2], r[3], self.lessons.get(r[1], []), self.history), reqs))
        return list(zip(reqs, outs))

    def push_decision(self, agent, role, type_, payload, out):
        seq = self.log._push(agent, role, type_, payload, out.get("reasoning"), dt=0, confidence=out.get("confidence"))
        e = self.log.events[-1]
        for k in ("model", "latency_ms", "tokens_in", "tokens_out"):
            e[k] = out.get(k)
        if out.get("error"):
            e["payload"]["llm_error"] = out["error"]
        if out.get("utterance"):
            self.log.speak(agent, role, out["utterance"], None, dt=0)
            self.log.events[-1]["model"] = None
            self.log.events[-1]["payload"]["voiced"] = True  # already written by the deciding LLM call
        return seq

    def apply_commander(self, req, out):
        _, _, _, opts, which = req
        choice = out["choice"]
        self.decisions.append((self.t, "commander", choice, [o["id"] for o in opts]))
        kind, uid = choice.split(":", 1)
        self.push_decision("commander", "commander", "decide",
                           {"action": "assign", "target": "rescue-1" if kind == "robot" else "ladder", "choice": choice,
                            "options": [o["id"] for o in opts]}, out)
        if uid == "hold":
            self.ladder["busy_until"] = self.t + 15
            return
        u = self.units[uid]
        u["busy"] = True
        if kind == "ladder":
            self.ladder.update(busy_until=self.t + LADDER_S, unit=uid)
            win = rid(floor_of(u["room"]), LADDER_ROOMS[kind_of(u["room"])])
            self.log.world({"type": "ladder", "deployed": 1, "targetWindowId": win}, f"Ladder to {win} for {u['label']}.", dt=0)
            for m in u["members"]:
                if m not in u["lost"]:
                    self.log.status(m, "moving", "ladder", dt=0)
        else:
            p, _ = self.path(self.robot["at"], u["room"])
            first = self.g[p[0]][p[1]] if len(p) > 1 else 0
            if len(p) > 1:
                self.walk_stairs(p[0], p[1], first, [("rescue-1", "rescue")])
            self.robot["task"] = {"unit": uid, "phase": "to", "path": p[1:], "next_t": self.t + first}

    def apply_hose(self, req, out):
        _, _, _, opts, _ = req
        choice = out["choice"]
        self.decisions.append((self.t, "hose-1", choice, [o["id"] for o in opts]))
        kind, arg = choice.split(":", 1)
        if kind == "spray":
            hall = rid(floor_of(arg), "hall")
            self.push_decision("hose-1", "suppression", "act", {"action": "spray", "target": arg, "choice": choice,
                                                                 "options": [o["id"] for o in opts]}, out)
            if self.hose["at"] != hall:
                p, _ = self.path(self.hose["at"], hall)
                if p:
                    self.hose["at"] = hall
                    self.log.move("hose-1", "suppression", self.room_pos(hall), dt=0)
            self.hose["target"] = arg
            self.log.world({"type": "hose", "active": True, "targetWindowId": None}, None, dt=0)
        else:
            f = int(arg)
            seq = self.push_decision("hose-1", "suppression", "request_approval",
                                     {"action": "vent", "target": rid(f, "hall"), "actor": "hose-1", "choice": choice,
                                      "options": [o["id"] for o in opts]}, out)
            ok = self.rng.random() < 0.6
            self.log.approval("approve" if ok else "deny", seq, dt=0)
            if ok:
                self.log.act("hose-1", "suppression", "vent", rid(f, "hall"), "Operator approved, venting.", risky=True,
                             extra={"approval_of_seq": seq}, dt=0)
                self.log.world({"type": "door", "doorId": f"{f}-door-kitchen-hall", "openness": 0.9}, None, dt=0)
                self.log.world({"type": "window", "windowId": f"{f}-window-living-w", "broken": True},
                               f"West window on floor {f} broken to let the smoke out.", dt=0)
                for k in KINDS:
                    self.smoke[rid(f, k)] *= 0.3
                if self.rng.random() < 0.3:
                    hot = max((rid(f, k) for k in KINDS), key=lambda r: self.fire[r])
                    self.fire[hot] = min(1.0, self.fire[hot] + 0.3)
                    self.log.world({"type": "fire", "roomId": hot, "intensity": round(self.fire[hot], 2)},
                                   "Backdraft: fresh air fed the fire.", dt=0)
                    self.log.events[-1]["payload"]["twist"] = "backdraft"

    def approach(self, uid):
        u = self.units[uid]
        opts = [{"id": k, "label": v[0]} for k, v in APPROACHES[uid].items()]
        obs = (self.building_line() + f"\nrescue-1 has reached {u['label']} in {u['room']}. "
               + ("Someone has already been brought out alive." if self.rescued_any else "Nobody has been brought out yet."))
        out = self.decide("rescue-1", "rescue", obs, opts, self.lessons.get("rescue", []), self.history)
        choice = out["choice"]
        self.decisions.append((self.t, "rescue-1", f"{uid}:{choice}", [o["id"] for o in opts]))
        self.push_decision("rescue-1", "rescue", "act", {"action": choice, "target": uid, "choice": choice,
                                                         "options": [o["id"] for o in opts]}, out)
        delay = APPROACHES[uid][choice][1]
        refused = False
        if uid == "victim-skeptic":
            if choice == "order" and not self.rescued_any:
                refused = True
                self.log.speak("victim-skeptic", "victim", "I'm not taking orders from a machine. I'll wait for a real firefighter.", None, dt=0)
            elif choice == "show_rescues" and not self.rescued_any:
                delay = 10
        if uid == "victim-family":
            bolt = self.rng.random() < (0.15 if choice == "gentle" else 0.5)
            if bolt:
                hide = rid(floor_of(u["room"]), "landing")
                self.log.speak("victim-child", "victim", "No! I don't want to go with the robot!", None, dt=0)
                self.log.move("victim-child", "victim", self.room_pos(hide), dt=0)
                self.log.world({"type": "smoke", "roomId": hide, "intensity": round(self.smoke[hide], 2)},
                               "The child ran off and hid. The parent won't leave without them.", dt=0)
                self.log.events[-1]["payload"]["twist"] = "child-missing"
                delay += 10
        if uid == "victim-elderly" and choice == "carry":
            u["carry"] = True
        return delay, refused

    # ---------- rescue robot movement ----------
    def step_robot(self):
        task = self.robot["task"]
        if not task or self.t < task["next_t"]:
            return
        uid = task["unit"]
        u = self.units[uid]
        if task["phase"] in ("to", "back") and task["path"]:
            nxt = task["path"].pop(0)
            prev = self.robot["at"]
            self.robot["at"] = nxt
            self.log.move("rescue-1", "rescue", self.room_pos(nxt), dt=0)
            if task["phase"] == "back":
                u["room"] = nxt
                for m in u["members"]:
                    if m not in u["lost"]:
                        self.log.move(m, "victim", self.room_pos(nxt), dt=0)
            if task["path"]:
                step = self.g[nxt][task["path"][0]] * (ESCORT * (1.5 if u.get("carry") else 1) if task["phase"] == "back" else 1)
                if frozenset((nxt, task["path"][0])) in self.blocked or (task["path"][0] != EXIT and self.fire[task["path"][0]] > SPREAD["impassable"]):
                    target = EXIT if task["phase"] == "back" else u["room"]
                    p, _ = self.path(nxt, target)
                    if p is None:
                        self.log.speak("rescue-1", "rescue", "Route is cut off. Pulling back.", None, dt=0)
                        u["busy"] = False
                        self.robot["task"] = None
                        return
                    task["path"] = p[1:]
                    step = self.g[nxt][task["path"][0]]
                walkers = [("rescue-1", "rescue")] + ([(m, "victim") for m in u["members"] if m not in u["lost"]]
                                                      if task["phase"] == "back" else [])
                self.walk_stairs(nxt, task["path"][0], step, walkers)
                task["next_t"] = self.t + step
                return
        if task["phase"] in ("to", "back"):
            if task["phase"] == "to":
                if u["status"] == "lost":
                    u["busy"] = False
                    self.robot["task"] = None
                    return
                delay, refused = self.approach(uid)
                if refused:
                    u["busy"] = False
                    self.robot["task"] = None
                    return
                for m in u["members"]:
                    if m not in u["lost"]:
                        self.log.status(m, "moving", "rescue-1", dt=0)
                task.update(phase="wait", next_t=self.t + delay)
                return
            # arrived at the exit with the unit
            self.finish_unit(uid, "rescue-1")
            self.robot["task"] = None
            return
        if task["phase"] == "wait":
            p, _ = self.path(self.robot["at"], EXIT)
            if p is None:
                self.log.speak("rescue-1", "rescue", "No way down from here.", None, dt=0)
                u["busy"] = False
                self.robot["task"] = None
                return
            task.update(phase="back", path=p[1:], next_t=self.t + self.g[p[0]][p[1]] * ESCORT)

    def finish_unit(self, uid, helper):
        u = self.units[uid]
        alive = [m for m in u["members"] if m not in u["lost"]]
        for m in alive:
            self.log.move(m, "victim", self.ext("engine") if helper == "ladder" else self.ext("entry"), dt=0)
            self.log.status(m, "rescued", helper, dt=0)
        u["status"] = "rescued" if alive else "lost"
        u["room"] = EXIT
        if alive:
            self.rescued_any = True

    def step_ladder(self):
        if self.ladder["busy_until"] is not None and self.t >= self.ladder["busy_until"]:
            uid = self.ladder["unit"]
            if uid and self.units[uid]["status"] == "trapped":
                self.finish_unit(uid, "ladder")
                self.log.world({"type": "ladder", "deployed": 0, "targetWindowId": None}, None, dt=0)
            self.ladder = {"busy_until": None, "unit": None}

    def step_twist(self):
        if self.collapse_t is not None and self.t == self.collapse_t and not self.blocked:
            self.blocked.add(frozenset(("2-hall", "3-hall")))
            self.log.world({"type": "smoke", "roomId": "2-hall", "intensity": 0.9},
                           "The stair flight between floors 2 and 3 collapses. Anyone above floor 2 needs another way down.", dt=0)
            self.log.events[-1]["payload"]["twist"] = "stair-collapse"

    def done(self):
        return all(u["status"] in ("rescued", "lost") for u in self.units.values())

    def run(self):
        self.log.world({"type": "fire", "roomId": SPREAD["origin"], "intensity": SPREAD["origin_fire"]},
                       "Grease fire on the floor 3 stove.", dt=0)
        self.log.world({"type": "engine_lights", "on": True}, None, dt=0)
        self.log.move("rescue-1", "rescue", self.ext("entry"), dt=0)
        self.log.move("hose-1", "suppression", self.ext("hydrant"), dt=0)
        self.log.move("scout-1", "scout", self.ext("engine"), dt=0)
        for uid, u in self.units.items():
            for m in u["members"]:
                self.log.move(m, "victim", self.room_pos(u["room"]), dt=0)
        while self.t < SPREAD["collapse_s"] and not self.done():
            self.log.t = float(self.t)
            self.step_twist()
            self.step_fire()
            self.step_air()
            self.step_scout()
            self.step_ladder()
            self.step_robot()
            reqs = self.commander_requests() + self.hose_request()
            # the robot and the ladder must not be sent for the same unit in one tick
            outs = self.run_decisions(reqs)
            for req, out in outs:
                if req[4] == "hose":
                    self.apply_hose(req, out)
                    continue
                uid = out["choice"].split(":", 1)[1]
                if uid == "hold" or not self.units[uid]["busy"]:
                    self.apply_commander(req, out)
            self.t += 1
        self.log.t = float(self.t)
        for uid, u in self.units.items():
            if u["status"] == "trapped":
                for m in u["members"]:
                    if m not in u["lost"]:
                        u["lost"][m] = "collapse"
                        self.log.status(m, "lost", "rescue-1", dt=0)
                        self.log.events[-1]["payload"]["cause"] = "collapse"
                u["status"] = "lost"
        if self.t >= SPREAD["collapse_s"]:
            self.log.world({"type": "fire", "roomId": "3-hall", "intensity": 1.0}, "The building is no longer safe. Everyone still inside is lost.", dt=0)
        return self.summary()

    def summary(self):
        out = {}
        for uid, u in self.units.items():
            for m in u["members"]:
                out[m] = ("lost", u["lost"][m]) if m in u["lost"] else ("rescued", None)
        return out


def run(seed, decide, lessons_by_role, history_line, log, pos, ext, stairs=None):
    w = World(seed, decide, lessons_by_role, history_line, log, pos, ext, stairs)
    outcomes = w.run()
    return outcomes, w.decisions, w.t
