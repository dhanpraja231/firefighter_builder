"""Action handlers: every `do_<action>` is a generator process step (yield = wait sim seconds)."""

from __future__ import annotations

from policy import pretty_room, robot_line
from world import (
    EXTERIOR, LADDER_WINDOW, SAFE_SPOTS, floor_of, flight_of, is_exterior, links, split_room, xyz,
)

WINDOW_OF_ROOM = {"living": "window-living-w", "bedroom-w": "window-bed-w", "landing": "window-landing-n", "bedroom-e": "window-bed-e-n"}
EFFECT_VOCAB = ("fire_surge", "smoke_surge", "stair_collapse", "power_loss", "backdraft", "victim_bolts", "door_jams", "flashover")


class ActionsMixin:
    # -- processes --------------------------------------------------------
    def options_for(self, a):
        if a is self.scout:
            return self.scout_options()
        if a is self.hose:
            return self.hose_options()
        return self.rescue_options(a)

    def robot_proc(self, a, start):
        yield start
        while not a.disabled:
            opts = self.options_for(a)
            if len(opts) <= 1:
                yield a.rng.uniform(1.5, 3.0)
                continue
            dec = self.policy.decide(a.id, a.role, self.observe(a), opts, a.rng)
            yield from getattr(self, "do_" + opts[dec.index]["action"])(a, opts[dec.index], dec)
            yield 0.3

    def commander_proc(self):
        yield 2.0
        last = -99.0
        while True:
            if self.dirty or self.now - last >= 9.0:
                self.dirty = False
                last = self.now
                opts = self.commander_options()
                if len(opts) > 1:
                    obs = self.observe(self.commander)
                    obs["alerts"] = list(self.alerts)
                    dec = self.policy.decide("commander", "commander", obs, opts, self.commander.rng)
                    yield from getattr(self, "do_" + opts[dec.index]["action"])(self.commander, opts[dec.index], dec)
            yield 1.0

    def director_proc(self):
        yield 12.0
        while True:
            opts = self.director_options()
            if opts:
                if getattr(self.policy, "free_director", False) and self.policy.available():
                    free = self.policy.director_free(self.director_obs(), self.director.rng)
                    if free and self.apply_free_twist(free):
                        yield 5.0
                        continue
                dec = self.policy.decide("director", "director", {"t": round(self.now, 1)}, opts, self.director.rng)
                opt = opts[dec.index]
                if opt["action"] == "twist":
                    self.apply_twist(opt["target"], dec)
            yield 5.0

    # -- movement ---------------------------------------------------------
    def open_door(self, a, door, to_room):
        self.world.door_open[door] = True
        self.world_event({"type": "door", "doorId": door, "openness": 1}, f"{a.id} opens the door to {pretty_room(to_room)}.")
        if self.world.fire[to_room] >= 0.5 and to_room not in self.world.vented and self.rng.random() < 0.4:
            self.backdraft(to_room, a.id)

    def travel(self, a, hops, anim, group=()):
        drone = a is self.scout
        group = [g for g in group if not g.resolved]
        for room, dist, kind, door in hops:
            if a.disabled:
                return False
            if self.world.blocked(a.room, room, drone):
                self.say(a, "The route is cut. Re-planning.")
                self.adapt["reroute"] += 1
                return False
            fl = flight_of(a.room, room)
            if fl is not None and fl in self.world.unstable and fl not in a.cleared and not drone:
                ok = yield from self.approve_unstable(a, fl)
                if not ok:
                    return False
                if a.rng.random() < 0.25:
                    self.collapse(fl, f"The weakened flight gives way under {a.id}.")
                    a.integrity -= 0.3
                    yield 6.0
                    return False
            if door and not self.world.door_open.get(door, False):
                self.open_door(a, door, room)
            speed = min([a.speed] + [g.speed for g in group])
            if any(g.carried for g in group):
                speed = min(speed, 1.6)
            yield max(0.1, dist / speed)
            if a.disabled:
                return False
            group = [g for g in group if g.leader is a and not g.resolved]
            self.emit_move(a, room, anim)
            for g in group:
                self.emit_move(g, room, "carry" if g.carried else "walk")
            self.hazard_entry(a, group, room)
        return True

    # -- human approval ---------------------------------------------------
    def ask_human(self, a, action, target, reasoning, dec, urgency, key):
        req = self.emit(a, "request_approval", {"action": action, "target": target, "risky": True, "urgency": round(urgency, 2)},
                        reasoning, None, dec)
        self.say(a, robot_line(a.rng, key, room=pretty_room(target)))
        verdict, delay = self.approver.decide(action, urgency)
        yield delay
        self.emit(self.human, "approval", {"action": verdict, "approval_of_seq": req, "note": f"{action} on {target}"})
        ok = verdict == "approve"
        if not ok:
            a.denied[(action, target)] = self.now + 30
            self.say(a, "Understood. Standing down on that.")
            self.dirty = True
        return ok, req

    def approve_unstable(self, a, fl):
        ok, _ = yield from self.ask_human(a, "enter_unstable", f"{fl}-hall", f"The flight between floors {fl} and {fl + 1} is weakened but it is the way to people above.",
                                          None, 0.5, "unstable")
        if ok:
            a.cleared.add(fl)
        return ok

    # -- small actions ----------------------------------------------------
    def do_hold(self, a, opt, dec):
        yield a.rng.uniform(2.0, 4.0)

    def decide_event(self, a, action, target, dec, **extra):
        return self.emit(a, "decide", {"action": action, "target": target, "risky": False, **extra}, dec.reasoning, None, dec)

    def do_scan_room(self, a, opt, dec):
        room = opt["target"]
        self.decide_event(a, "scan_room", room, dec, anim="run")
        self.say(a, dec.utterance, dec)
        hops = self.world.path(a.room, room, drone=True)
        if hops is None:
            yield 1.0
            return
        if not (yield from self.travel(a, hops, "run")):
            return
        self.emit(a, "act", {"action": "scan_room", "target": room, "risky": False, "anim": "idle"},
                  f"Thermal and visual sweep of {pretty_room(room)}.", None, dec)
        yield 1.0
        self.scan_count[room] = self.scan_count.get(room, 0) + 1
        self.scanned.add(room)
        fp = self.mem_view()["found_prob"] * (1.0 if self.world.power else 0.6)
        adjacent = {n for n, _, k, _ in links(room) if k == "door"}
        found = []
        for v in self.victims.values():
            if v.resolved or (v.room != room and v.room not in adjacent):
                continue
            chance = fp if v.room == room else 0.45 * fp  # thermal imaging sees through the wall less well
            if v.status == "trapped":
                if a.rng.random() < chance:
                    v.found_t = self.now
                    v.known_room = v.room
                    self.victim_status(v, "found", a.id, "plead")
                    found.append(v)
            elif v.known_room != v.room and v.leader is None and v.room == room:
                v.known_room = room
                found.append(v)
        self.say(a, robot_line(a.rng, "found" if found else "clear", room=pretty_room(room)))
        if found or self.world.fire[room] > 0.1:
            self.dirty = True
        yield 0.5

    def do_spray(self, a, opt, dec):
        room = opt["target"]
        self.decide_event(a, "spray", room, dec, anim="run")
        self.say(a, dec.utterance, dec)
        stand = room
        if self.world.fire[room] > 0.45:
            nbrs = [n for n, _, _, _ in links(room) if not is_exterior(n) and not self.world.blocked(room, n)]
            if nbrs:
                stand = min(nbrs, key=lambda n: self.world.fire[n])
        hops = self.world.path(a.room, stand)
        if hops is None or not (yield from self.travel(a, hops, "run")):
            return
        self.emit(a, "act", {"action": "spray", "target": room, "risky": False, "anim": "spray"}, f"Water on {pretty_room(room)}.", None, dec)
        self.world.spraying[room] = (self.now + 9, 0.035 + 0.03 * a.rng.random())
        yield 9.0

    def do_spray_exterior(self, a, opt, dec):
        room = opt["target"]
        self.decide_event(a, "spray_exterior", room, dec, anim="run")
        hops = self.world.path(a.room, "exterior-engine")
        if hops is None or not (yield from self.travel(a, hops, "run")):
            return
        f, k = split_room(room)
        win = f"{f}-{WINDOW_OF_ROOM.get(k, 'window-living-w')}"
        self.emit(a, "act", {"action": "spray_exterior", "target": room, "risky": False, "anim": "spray"}, f"Streaming water in through {win}.", None, dec)
        self.world_event({"type": "hose", "active": True, "targetWindowId": win}, None)
        self.world.spraying[room] = (self.now + 10, 0.02)
        yield 10.0
        self.world_event({"type": "hose", "active": False}, None)

    def do_close_door(self, a, opt, dec):
        room = opt["target"]
        cands = [(n, d) for n, _, k, d in links(room) if k == "door" and self.world.door_open.get(d)]
        if not cands:
            return
        nbr, door = min(cands, key=lambda c: self.world.fire[c[0]])
        self.decide_event(a, "close_door", room, dec, anim="run")
        self.say(a, dec.utterance, dec)
        hops = self.world.path(a.room, nbr)
        if hops is None or not (yield from self.travel(a, hops, "run")):
            return
        self.emit(a, "act", {"action": "close_door", "target": room, "risky": False, "anim": "pickup"}, f"Closing {door} to starve the fire.", None, dec)
        self.world.door_open[door] = False
        self.world_event({"type": "door", "doorId": door, "openness": 0}, f"{a.id} closes the door to slow the fire.")
        yield 2.0

    def do_vent(self, a, opt, dec):
        room = opt["target"]
        self.decide_event(a, "vent", room, dec, risky=True, anim="run")
        ok, req = yield from self.ask_human(a, "vent", room, dec.reasoning, dec, 0.4 + 0.4 * self.world.fire[room], "vent")
        if not ok:
            return
        nbrs = [n for n, _, k, _ in links(room) if k == "door" and not is_exterior(n)]
        hops = self.world.path(a.room, min(nbrs, key=lambda n: self.world.fire[n])) if nbrs else None
        if hops is None or not (yield from self.travel(a, hops, "run")):
            return
        self.emit(a, "act", {"action": "vent", "target": room, "risky": True, "approval_of_seq": req, "anim": "pickup"}, "Approved. Venting.", None, dec)
        f, k = split_room(room)
        if self.rng.random() < 0.35 + 0.5 * self.world.fire[room]:
            self.backdraft(room, a.id)
        else:
            self.world.vented.add(room)
            self.world.smoke[room] *= 0.5
            if k in WINDOW_OF_ROOM:
                self.world_event({"type": "window", "windowId": f"{f}-{WINDOW_OF_ROOM[k]}", "broken": True}, "The window goes out and the smoke pours free.")
        yield 3.0

    def do_deploy_ladder(self, a, opt, dec):
        room = opt["target"]
        self.decide_event(a, "deploy_ladder", room, dec, anim="run")
        self.say(a, dec.utterance, dec)
        hops = self.world.path(a.room, "exterior-engine")
        if hops is None or not (yield from self.travel(a, hops, "run")):
            return
        f, k = split_room(room)
        self.emit(a, "act", {"action": "deploy_ladder", "target": room, "risky": False, "anim": "pickup"}, f"Aerial ladder to {pretty_room(room)}.", None, dec)
        yield 5.0
        self.world.ladder_room = room
        self.last_ladder_t = self.now
        self.world_event({"type": "ladder", "deployed": 1.0, "targetWindowId": f"{f}-{LADDER_WINDOW[k]}"}, f"The ladder is on {pretty_room(room)}.")
        self.dirty = True

    # -- rescue -----------------------------------------------------------
    def do_abandon(self, a, opt, dec):
        v = self.victims[opt["target"]]
        self.decide_event(a, "abandon", v.id, dec)
        self.say(a, f"I can't reach {v.name}. The way is burning. Marking as unreachable.", dec)
        a.denied[("abandon", v.id)] = self.now + 28
        self.adapt["abandon"] += 1
        self.alerts.append(f"rescue abandoned {v.name}")
        self.dirty = True
        yield 1.0

    def do_fetch(self, a, opt, dec):
        v = self.victims[opt["target"]]
        room = v.known_room
        if room is None or v.resolved:
            return
        self.decide_event(a, "fetch", v.id, dec, anim="run")
        courage = a.traits.get("courage", 0.6)
        hops = self.world.path(a.room, room, avoid=1.8 - courage)
        direct = self.world.path(a.room, room, avoid=0.0)
        if hops and direct and [h[0] for h in hops] != [h[0] for h in direct]:
            self.adapt["reroute"] += 1
            self.say(a, "Fire on the direct route. Going around.")
        if hops is None:
            yield 1.5
            return
        locked = room in self.world.locked
        if not (yield from self.travel(a, hops[:-1] if locked and hops else hops, "run")):
            return
        if locked:
            ok, req = yield from self.ask_human(a, "breach_door", room, dec.reasoning, dec, 1 - v.health, "breach")
            if not ok:
                return
            self.emit(a, "act", {"action": "breach_door", "target": room, "risky": True, "approval_of_seq": req, "anim": "pickup"},
                      f"Approved. Breaching the door to {pretty_room(room)}.", None, dec)
            self.world.locked.discard(room)
            door = self.world.door_between(a.room, room)
            if door:
                self.open_door(a, door, room)
            v.panic = min(1.0, v.panic + 0.2)
            if not (yield from self.travel(a, hops[-1:], "run")):
                return
        if v.room != a.room:
            if any(n == v.room for n, *_ in links(a.room)):
                v.known_room = v.room
                self.say(a, f"{v.name} moved. I have a visual next door.")
            else:
                v.known_room = None
                self.say(a, f"Lost {v.name}. They are not where the scout saw them.")
                self.dirty = True

    def do_persuade(self, a, opt, dec):
        v = self.victims[opt["target"]]
        tactic = opt["meta"]["tactic"]
        a.tried.setdefault(v.id, set()).add(tactic)
        self.emit(a, "act", {"action": "persuade", "target": v.id, "tactic": tactic, "risky": False,
                             "anim": "plead" if tactic != "carry" else "pickup"}, dec.reasoning, None, dec)
        self.say(a, dec.utterance, dec, target=v.id)
        yield 1.6
        group = [v] + [g for g in self.victims.values() if g is not v and g.room == v.room and not g.resolved and g.leader is None
                       and v.id.startswith("victim-couple") and g.id.startswith("victim-couple")]
        outcomes = {}
        for g in group:
            outcomes[g.id] = yield from self.victim_reply(a, g, tactic)
            yield 1.0
        couple = [g for g in group if g.id.startswith("victim-couple")]
        if len(couple) == 2 and len({outcomes[g.id] for g in couple}) == 2:
            for g in couple:
                if g.leader is a:
                    a.followers.remove(g)
                    self.release(g, a)
            self.say(couple[0], "Not unless we go together.", None, anim="plead")
            for g in couple:
                g.refused += 1

    def victim_reply(self, a, v, tactic):
        w = self.world
        parent, child = self.victims["victim-parent"], self.victims["victim-child"]
        partner = next((g for g in self.victims.values() if g is not v and v.id.startswith("victim-couple")
                        and g.id.startswith("victim-couple") and g.room == v.room and not g.resolved), None)
        opts = [{"action": "comply", "target": None, "risky": False, "label": "agree to go with the robot", "meta": {}},
                {"action": "refuse", "target": None, "risky": False, "label": "refuse", "meta": {}},
                {"action": "stall", "target": None, "risky": False, "label": "stall for time", "meta": {}}]
        if v.id == "victim-child" or v.panic > 0.7:
            opts.insert(2, {"action": "bolt", "target": None, "risky": False, "label": "bolt out of the room", "meta": {}})
        for i, o in enumerate(opts):
            o["i"] = i
        ctx = {"refused": v.refused, "panic": round(v.panic, 2), "smoke": round(w.smoke[v.room], 2), "robot_in_frame": True,
               "helped_before": len(self.rescued_order) > 0, "partner_here": partner is not None,
               "child_ok": bool(child.known_room) or child.status in ("moving", "rescued") or child.room == parent.room,
               "parent_here": parent.room == v.room and not parent.resolved and v.id == "victim-child"}
        obs = {"t": round(self.now, 1), "tactic": tactic, "ctx": ctx, "persona": v.persona, "traits": v.traits, "memory": self.mem_view(),
               "radio": self.radio[-3:]}
        dec = self.policy.decide(v.id, "victim", obs, opts, v.rng)
        key = opts[dec.index]["action"]
        arg = "argue" if v.id in ("victim-skeptic", "victim-teen", "victim-parent") else "plead"
        if key == "comply":
            v.leader = a
            v.carried = tactic == "carry"
            a.followers.append(v)
            self.say(v, dec.utterance, dec)
            self.victim_status(v, "moving", a.id, "carry" if v.carried else "walk")
        elif key == "bolt":
            self.flags["child_bolted"] = self.flags.get("child_bolted", False) or v.id == "victim-child"
            self.say(v, dec.utterance, dec, anim="run")
            nbrs = [n for n, _, k, _ in links(v.room) if k == "door" and not is_exterior(n)]
            if nbrs:
                v.hiding_until = self.now + v.rng.uniform(9, 16)
                self.emit_move(v, min(nbrs, key=lambda n: w.danger(n) + v.rng.random() * 0.2), "run")
                v.known_room = None
                self.dirty = True
        elif key == "refuse":
            v.refused += 1
            self.say(v, dec.utterance, dec, anim=arg)
        else:
            self.say(v, dec.utterance, dec, anim=arg)
        return key
        yield  # pragma: no cover - makes this a generator

    def do_evacuate(self, a, opt, dec):
        followers = [v for v in a.followers if not v.resolved]
        if not followers:
            return
        self.decide_event(a, "evacuate", "exterior-entry", dec, anim="walk")
        self.say(a, dec.utterance, dec)
        hops = self.world.path(a.room, "exterior-entry", avoid=1.8 - a.traits.get("courage", 0.6))
        direct = self.world.path(a.room, "exterior-entry", avoid=0.0)
        if hops and direct and [h[0] for h in hops] != [h[0] for h in direct]:
            self.adapt["reroute"] += 1
            self.say(a, "Hall is burning. Taking the long way out.")
        if hops is None:
            self.say(a, "No way out from here. Looking for another route.")
            yield 2.0
            return
        if not (yield from self.travel(a, hops, "carry" if any(v.carried for v in followers) else "walk", group=followers)):
            return
        if a.room == "exterior-entry":
            self.deliver(a)

    def deliver(self, a):
        group = [v for v in a.followers if not v.resolved]
        for v in group:
            a.followers.remove(v)
            v.leader = None
            v.carried = False
            self.rescued_order.append(v.id)
            self.victim_status(v, "rescued", a.id, "celebrate")
            self.emit_move_xyz(v, SAFE_SPOTS[(len(self.rescued_order) - 1) % len(SAFE_SPOTS)], "walk")
            v.room = "exterior-entry"
        if group:
            self.say(a, robot_line(a.rng, "out", n=len(group)))
            self.dirty = True

    def do_evacuate_ladder(self, a, opt, dec):
        followers = [v for v in a.followers if not v.resolved]
        self.decide_event(a, "evacuate_ladder", a.room, dec, anim="pickup")
        for v in followers:
            self.emit(a, "act", {"action": "lower_to_ladder", "target": v.id, "risky": False, "anim": "pickup"}, "Handing them onto the ladder.", None, dec)
            yield 3.0 + 1.2 * floor_of(a.room)
            if v.resolved:
                continue
            a.followers.remove(v)
            v.leader = None
            v.carried = False
            self.rescued_order.append(v.id)
            self.victim_status(v, "rescued", a.id, "celebrate")
            self.emit_move_xyz(v, SAFE_SPOTS[(len(self.rescued_order) - 1) % len(SAFE_SPOTS)], "walk")
            v.room = "exterior-engine"
        self.dirty = True

    # -- commander --------------------------------------------------------
    def do_assign(self, a, opt, dec):
        m = opt["meta"]
        robot = self.robots_by_id[opt["target"]]
        robot.task = {k: m[k] for k in ("task", "floor", "victim", "room") if k in m}
        reasoning = dec.reasoning
        if self.alerts:
            self.adapt["reprioritize"] += 1
            reasoning += f" (re-planned after: {self.alerts[-1]})"
            self.alerts.clear()
        self.emit(a, "decide", {"action": "assign", "target": robot.id, "task": m["task"], "risky": False,
                                "utterance": dec.utterance}, reasoning, None, dec)
        self.say(a, dec.utterance, dec)
        yield 1.0

    def do_retreat(self, a, opt, dec):
        self.emit(a, "decide", {"action": "retreat", "target": "all", "risky": False, "utterance": dec.utterance}, dec.reasoning, None, dec)
        self.say(a, dec.utterance, dec)
        yield 0.5
        self.finish("commander_retreat")

    # -- director twists --------------------------------------------------
    def director_obs(self):
        w = self.world
        return {"t": round(self.now, 1), "twists_so_far": list(self.twists),
                "fires": {r: round(w.fire[r], 2) for r in w.fire if w.fire[r] > 0.05},
                "victims": [{"id": v.id, "room": v.room, "status": v.status, "panic": round(v.panic, 2)} for v in self.victims.values() if not v.resolved],
                "robots": {r.id: r.room for r in self.robots}, "effect_vocabulary": list(EFFECT_VOCAB)}

    def apply_twist(self, name, dec):
        w = self.world
        self.last_twist_t = self.now
        if name == "stair-collapse":
            free = [k for k in (1, 2, 3, 4) if k not in w.collapsed]
            k = max(free, key=lambda k: w.fire[f"{k}-hall"] + w.fire[f"{k + 1}-hall"] + self.rng.random() * 0.3)
            self.collapse(k, "The fire has eaten into the stair core and a flight gives way.", dec)
        elif name == "child-missing":
            c = self.victims["victim-child"]
            nbrs = [n for n, _, kk, _ in links(c.room) if kk == "door" and not is_exterior(n)]
            if nbrs:
                self.flags["child_bolted"] = True
                self.world_event({"type": "twist", "twist": "child-missing"}, "The child slips out while nobody is looking.", dec, room=c.room, anim="flinch")
                self.say(c, "I want mom!", None, anim="run")
                self.emit_move(c, self.rng.choice(nbrs), "run")
                c.hiding_until = self.now + self.rng.uniform(10, 18)
                c.known_room = None
                self.victims["victim-parent"].panic = 0.95
                self.twists.append("child-missing")
                self.dirty = True
        elif name == "power-loss":
            w.power = False
            self.power_back = self.now + 25.0
            self.world_event({"type": "power", "on": False}, "The grid fails. Scans get unreliable.", dec)
            self.twists.append("power-loss")
        elif name == "backdraft":
            rooms = [n for r in self.robots if not r.disabled for n, _, k, _ in links(r.room) if k == "door" and w.fire[n] >= 0.5]
            if rooms:
                self.backdraft(rooms[0], "the director")
        elif name == "flashover":
            hot = [r for r in w.fire if w.fire[r] >= 0.6]
            if hot:
                r = max(hot, key=lambda r: w.fire[r] + self.rng.random() * 0.2)
                w.fire[r] = 1.0
                for n, _, _, _ in links(r):
                    if not is_exterior(n):
                        w.ignite(n, 0.3, self.now)
                self.world_event({"type": "fire", "roomId": r, "intensity": 1.0}, f"Flashover in {pretty_room(r)}: everything in the room ignites at once.", dec, room=r, anim="flinch")
                self.twists.append("flashover")
                self.dirty = True
        elif name == "victim-moves":
            pan = [v for v in self.victims.values() if not v.resolved and v.leader is None and v.panic > 0.5]
            if pan:
                v = max(pan, key=lambda v: v.panic)
                self.twists.append("victim-moves")
                self.flee(v, forced=True)

    def apply_free_twist(self, free):
        """LLM director: free-text twist + one structured effect from the fixed vocabulary, validated against the real fire state."""
        w = self.world
        text = str(free.get("twist") or "").strip()
        eff = free.get("effect") or {}
        kind, target = eff.get("kind"), eff.get("target")
        if kind not in EFFECT_VOCAB or not text:
            return False
        reason = text[:200]
        ok = False
        if kind in ("fire_surge", "backdraft", "flashover") and target in w.fire and w.fire[target] >= 0.25:
            if kind == "backdraft":
                self.backdraft(target, "the director")
            else:
                w.fire[target] = min(1.0, w.fire[target] + 0.35)
                if kind == "flashover":
                    for n, _, _, _ in links(target):
                        if not is_exterior(n):
                            w.ignite(n, 0.25, self.now)
                self.world_event({"type": "fire", "roomId": target, "intensity": round(w.fire[target], 2)}, reason, None, anim="flinch", room=target)
            ok = True
        elif kind == "smoke_surge" and target in w.smoke:
            w.smoke[target] = min(1.0, w.smoke[target] + 0.4)
            self.world_event({"type": "smoke", "roomId": target, "intensity": round(w.smoke[target], 2)}, reason)
            ok = True
        elif kind == "stair_collapse" and isinstance(target, int) and target in (1, 2, 3, 4) and target not in w.collapsed \
                and w.fire[f"{target}-hall"] + w.fire[f"{target + 1}-hall"] >= 0.25:
            self.collapse(target, reason)
            ok = True
        elif kind == "power_loss":
            w.power = False
            self.power_back = self.now + 25.0
            self.world_event({"type": "power", "on": False}, reason)
            ok = True
        elif kind == "victim_bolts" and target in self.victims and not self.victims[target].resolved and self.victims[target].leader is None:
            self.flee(self.victims[target], forced=True)
            ok = True
        elif kind == "door_jams" and target in w.fire and not any(r.room == target for r in self.robots):
            w.locked.add(target)
            self.world_event({"type": "twist", "twist": "door_jams", "room": target}, reason, None, room=target)
            ok = True
        if ok:
            self.last_twist_t = self.now
            self.twists.append(f"free:{kind}")
            self.dirty = True
            self.world_event({"type": "twist", "twist": text[:120], "effect": kind}, None)
        return ok
