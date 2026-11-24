"""Observations and legal-option enumeration for every agent role."""

from __future__ import annotations

import random

from policy import TACTICS, pretty_room, tactic_fit
from world import FLOORS, LADDER_MAX_FLOOR, LADDER_WINDOW, ROOMS, HOSE_MAX_FLOOR, floor_of, is_exterior, links, split_room

VULNERABLE = ("victim-elderly", "victim-child")


def _opt(action, target, label, meta=None, risky=False):
    return {"action": action, "target": target, "risky": risky, "label": label, "meta": meta or {}}


def _number(options):
    for i, o in enumerate(options):
        o["i"] = i
    return options


def roll_traits(seed, victims):
    """Per-run personality rolls. Seeded, so the same seed replays identically, but every seed is a
    different cast of characters: who is bold, who is gentle, who panics, who trusts the robots."""
    tr = random.Random(f"traits:{seed}")

    def weights(*names):
        raw = [tr.random() ** 1.5 + 0.05 for _ in names]
        s = sum(raw)
        return {n: round(x / s, 3) for n, x in zip(names, raw)}

    out = {
        "commander": {"caution": round(tr.uniform(0.1, 0.9), 2), "obedience": 0.5,
                      "w": weights("danger", "vulnerable", "near"), "sweep_bias": round(tr.uniform(0, 1), 2)},
        "scout-1": {"caution": round(tr.uniform(0.1, 0.9), 2), "sweep": weights("top_down", "bottom_up", "nearest", "fire_first")},
        "hose-1": {"caution": round(tr.uniform(0.1, 0.9), 2), "hose": weights("stairwell", "fire", "support")},
        "rescue-1": {"caution": round(tr.uniform(0.1, 0.9), 2), "courage": round(tr.uniform(0.15, 1.0), 2),
                     "empathy": round(tr.uniform(0.1, 1.0), 2), "obedience": round(tr.uniform(0.2, 0.9), 2)},
    }
    for vid in victims:
        out[vid] = {"panic": round(tr.uniform(0.05, 0.6), 2), "trust": round(tr.uniform(0.15, 0.95), 2),
                    "stubborn": round(tr.uniform(0.0, 1.0), 2)}
    return out


class OptionsMixin:
    def mem_view(self):
        m = self.memory
        return {"cautious_briefing": bool(m.get("cautious_briefing")),
                "bolt_prob": max(0.25, float(m.get("bolt_prob", 0.55))),
                "found_prob": min(0.8, float(m.get("found_prob", 0.75))),
                "child_losses": m.get("child_losses", 0), "runs": m.get("runs", 0)}

    def plen(self, a, dst, drone=False):
        hops = self.world.path(a.room, dst, drone=drone)
        if hops is None:
            return None, 1e9
        return hops, sum(h[1] for h in hops)

    def visible(self):
        vis = set(self.scanned) | {"3-kitchen"}
        for r in self.robots:
            if not r.disabled:
                vis.add(r.room)
                for n, _, _, _ in links(r.room):
                    vis.add(n)
        return {x for x in vis if not is_exterior(x)}

    def known_victims(self):
        return [v for v in self.victims.values() if v.known_room and not v.resolved]

    def observe(self, a):
        vis = self.visible()
        w = self.world
        return {
            "t": round(self.now, 1),
            "me": {"id": a.id, "role": a.role, "room": a.room, "integrity": round(a.integrity, 2),
                   "following_me": [v.id for v in a.followers], "task": a.task},
            "traits": a.traits, "memory": self.mem_view(), "radio": self.radio[-5:], "my_recent_actions": list(a.notes), "fire_age_s": {r: round(self.now - self.world.ignited_at[r]) for r in vis if r in self.world.ignited_at and w.fire[r] > 0.05}, "alerts": list(self.alerts),
            "fires": {r: round(w.fire[r], 2) for r in vis if w.fire[r] > 0.05},
            "smoke": {r: round(w.smoke[r], 2) for r in vis if w.smoke[r] > 0.1},
            "collapsed_flights": sorted(w.collapsed), "unstable_flights": sorted(w.unstable), "ladder_at": w.ladder_room,
            "robots": {r.id: {"room": r.room, "integrity": round(r.integrity, 2), "task": r.task, "down": r.disabled} for r in self.robots},
            "victims": [{"id": v.id, "name": v.name, "room": v.known_room, "status": v.status,
                         "danger": round(w.danger(v.known_room), 2), "waiting_s": round(self.now - v.found_t),
                         "persona": {k: v.persona.get(k) for k in ("temperament", "mobility", "goal", "fears", "compliance")}}
                        for v in self.known_victims()],
        }

    # -- commander --------------------------------------------------------
    def commander_options(self):
        w, c = self.world, self.commander
        vics = self.known_victims()
        opts = [_opt("hold", None, "keep the current plan")]
        unfound = sum(1 for v in self.victims.values() if v.status == "trapped") / len(self.victims)
        for v in vics:
            if not self.rescue.disabled and not (self.rescue.task and self.rescue.task.get("victim") == v.id):
                hops, length = self.plen(self.rescue, v.known_room)
                if hops is not None:
                    covered = 1.0 if (v in self.rescue.followers or (self.hose.task or {}).get("victim") == v.id) else 0.0
                    opts.append(_opt("assign", "rescue-1", f"rescue-1: get {v.name} out ({pretty_room(v.known_room)})", {
                        "task": "rescue", "victim": v.id, "name": v.name, "room": v.known_room, "danger": round(w.danger(v.known_room), 2),
                        "vulnerable": 1.0 if v.id in VULNERABLE else 0.0, "waiting": self.now - v.found_t, "covered": covered,
                        "near": round(1 / (1 + length / 15), 2)}))
            if not self.hose.disabled and (self.rescue.disabled or len(vics) >= 3) and not (self.hose.task or {}).get("victim") == v.id:
                opts.append(_opt("assign", "hose-1", f"hose-1: help extract {v.name}", {
                    "task": "rescue_support", "victim": v.id, "name": v.name, "room": v.known_room,
                    "pressure": min(1.0, (len(vics) - 1) / 3), "rescue_down": self.rescue.disabled}))
        if not self.scout.disabled:
            fire_floors = {floor_of(r) for r in ROOMS if w.fire[r] > 0.1}
            cur = (self.scout.task or {}).get("floor")
            cur_left = cur is not None and any(r not in self.scanned for r in ROOMS if floor_of(r) == cur)
            for f in FLOORS:
                rooms = [r for r in ROOMS if floor_of(r) == f]
                frac = sum(1 for r in rooms if r not in self.scanned) / len(rooms)
                if frac > 0 and cur != f and not (cur_left and not self.alerts):
                    near = 1.0 if (f in fire_floors or f - 1 in fire_floors) else 0.3
                    opts.append(_opt("assign", "scout-1", f"scout-1: sweep floor {f}", {
                        "task": "sweep", "floor": f, "unscanned": round(frac, 2), "near_fire": near, "unfound": round(unfound, 2)}))
        if not self.hose.disabled:
            burning = sorted((r for r in self.visible() if w.fire[r] > 0.2), key=lambda r: -w.fire[r])[:3]
            for r in burning:
                if (self.hose.task or {}).get("room") != r:
                    opts.append(_opt("assign", "hose-1", f"hose-1: attack the fire in {pretty_room(r)}", {
                        "task": "suppress", "room": r, "fire": round(w.fire[r], 2), "route": 1.0 if r.endswith("hall") else 0.4}))
            for r in self.ladder_candidates():
                opts.append(_opt("assign", "hose-1", f"hose-1: ladder to {pretty_room(r)}", {
                    "task": "ladder", "room": r, "cut_victims": self.cut_victims(), "victim_here": 1.0 if any(v.known_room == r for v in vics) else 0.0}))
        alive = [r for r in self.robots if not r.disabled]
        danger_mean = (sum(w.danger(v.known_room) for v in vics) / len(vics)) if vics else 0.0
        opts.append(_opt("retreat", None, "order every robot out of the building", {
            "danger_mean": round(danger_mean, 2), "min_integrity": round(min((r.integrity for r in alive), default=0.0), 2),
            "lost": sum(1 for v in self.victims.values() if v.status == "lost")}))
        return _number(opts)

    def cut_victims(self):
        n = 0
        for v in self.known_victims():
            if self.world.path("exterior-entry", v.known_room) is None:
                n += 1
        return min(1.0, n / 2)

    def ladder_candidates(self):
        out = []
        for v in self.known_victims():
            f = floor_of(v.known_room)
            if f > LADDER_MAX_FLOOR:
                continue
            for kind in LADDER_WINDOW:
                r = f"{f}-{kind}"
                if r != self.world.ladder_room and r not in out:
                    out.append(r)
        return out[:3]

    # -- scout ------------------------------------------------------------
    def scout_options(self):
        s = self.scout
        sw = s.traits["sweep"]
        task_floor = (s.task or {}).get("floor")
        fire_rooms = [r for r in ROOMS if self.world.fire[r] > 0.1]
        fire_floor = max((floor_of(r) for r in fire_rooms), default=3)
        cands = []
        for r in ROOMS:
            if self.scan_count.get(r, 0) > 0:
                continue
            hops, length = self.plen(s, r, drone=True)
            if hops is None:
                continue
            f = floor_of(r)
            style = (sw["top_down"] * f / 5 + sw["bottom_up"] * (1 - (f - 1) / 4) + sw["nearest"] / (1 + length / 8)
                     + sw["fire_first"] * (1 - min(1.0, abs(f - fire_floor) / 2)))
            prio = 1.0 if task_floor == f else (0.25 if task_floor else 0.5)
            cands.append((style + 0.6 * prio, r, length, style, prio))
        opts = [_opt("hold", None, "hold position")]
        if cands:
            cands.sort(reverse=True)
            for _, r, length, style, prio in cands[:5]:
                opts.append(_opt("scan_room", r, f"scan {pretty_room(r)}", {
                    "floor": floor_of(r), "dist": round(length, 1), "danger": round(self.world.danger(r), 2),
                    "priority": round(0.5 * prio + 0.9 * style, 2), "rescan": False}))
        elif any(v.status == "trapped" for v in self.victims.values()):
            again = [r for r in ROOMS if self.scan_count.get(r, 0) == 1 and not r.endswith(("hall", "landing"))]
            for r in s.rng.sample(again, min(3, len(again))):
                hops, length = self.plen(s, r, drone=True)
                if hops is not None:
                    opts.append(_opt("scan_room", r, f"re-scan {pretty_room(r)}", {
                        "floor": floor_of(r), "dist": round(length, 1), "danger": round(self.world.danger(r), 2), "priority": 0.5, "rescan": True}))
        return _number(opts)

    # -- hose -------------------------------------------------------------
    def hose_options(self):
        h = self.hose
        if (h.task or {}).get("task") == "rescue_support":
            return self.rescue_options(h)
        w = self.world
        hs = h.traits["hose"]
        vics = self.known_victims()
        vis = self.visible()
        opts = [_opt("hold", None, "stand by")]
        burning = sorted((r for r in vis if w.fire[r] > 0.15), key=lambda r: -w.fire[r])[:3]
        fire_floors = {floor_of(r) for r in burning}
        halls = [f"{f}-hall" for f in sorted(fire_floors | {f + 1 for f in fire_floors if f < 5}) if w.fire[f"{f}-hall"] < 0.6][:2]
        for r in burning + halls:
            hops, length = self.plen(h, r)
            if hops is None:
                continue
            f_ = floor_of(r)
            threat = min(1.0, sum(1 for v in vics if floor_of(v.known_room) in (f_, f_ + 1)) / 3)
            near = 1.0 if any(v.known_room == r or (v.known_room and any(n == v.known_room for n, *_ in links(r))) for v in vics) else 0.0
            is_hall = r.endswith("hall")
            opts.append(_opt("spray", r, f"{'hold the line at' if is_hall and w.fire[r] < 0.15 else 'spray'} {pretty_room(r)}", {
                "fire": round(w.fire[r], 2), "near_victim": near, "dist": round(length, 1), "threat": round(threat, 2),
                "route": round(hs["stairwell"] * (1.0 if is_hall else 0.2) * 2 + (0.3 if (h.task or {}).get("room") == r else 0.0), 2),
                "fire_w": hs["fire"]}))
            f = floor_of(r)
            if f <= HOSE_MAX_FLOOR and w.fire[r] > 0.15:
                opts.append(_opt("spray_exterior", r, f"spray {pretty_room(r)} from the street", {
                    "fire": round(w.fire[r], 2), "near_victim": near, "fire_w": hs["fire"]}))
            if w.fire[r] > 0.3 and any(k == "door" and w.door_open.get(d) for _, _, k, d in links(r)):
                opts.append(_opt("close_door", r, f"close the door on {pretty_room(r)}", {"fire": round(w.fire[r], 2)}))
            if w.fire[r] > 0.3 and not any(k == "door" and w.door_open.get(d) for _, _, k, d in links(r)) and r not in w.vented:
                opts.append(_opt("vent", r, f"vent {pretty_room(r)}", {
                    "fire": round(w.fire[r], 2), "smoke_route": round(max(w.smoke[n] for n, *_ in links(r) if not is_exterior(n)), 2)}, risky=True))
        for r in self.ladder_candidates():
            if r == w.ladder_room or self.now - self.last_ladder_t < 25:
                continue
            f = floor_of(r)
            above = sum(1 for v in vics if floor_of(v.known_room) >= f)
            opts.append(_opt("deploy_ladder", r, f"put the ladder on {pretty_room(r)}", {
                "floor": f, "victims_above": above, "stairs_cut": bool(w.collapsed),
                "cut_victims": self.cut_victims() * (1.0 if w.collapsed else 0.0),
                "victim_here": 1.0 if any(v.known_room == r for v in vics) else 0.0, "support_w": hs["support"]}))
        return _number(opts)

    # -- rescue -----------------------------------------------------------
    def rescue_options(self, a):
        w = self.world
        vics = self.known_victims()
        followers = [v for v in a.followers if not v.resolved]
        opts = [_opt("hold", None, "wait for orders")]
        waiting = [v for v in vics if v.leader is None]
        here = [v for v in waiting if v.room == a.room]
        seen_pairs = set()
        for v in here:
            if v.id.startswith("victim-couple") and "couple" in seen_pairs:
                continue
            if v.id.startswith("victim-couple"):
                seen_pairs.add("couple")
            fits = tactic_fit(v.persona)
            for t in TACTICS:
                if t == "carry" and v.refused < 1 and w.danger(a.room) < 0.5:
                    continue
                if t == "reunite" and v.id not in ("victim-parent", "victim-child") and not v.id.startswith("victim-couple"):
                    continue
                opts.append(_opt("persuade", v.id, f"{t.replace('_', ' ')} with {v.name}", {
                    "victim": v.id, "name": v.name, "tactic": t, "tried": t in a.tried.get(v.id, set()), "fits": t in fits,
                    "urgency": round(w.danger(a.room), 2), "refused": v.refused, "goal": v.persona.get("goal", "")}))
        far = []
        for v in waiting:
            if v.room == a.room:
                continue
            hops, length = self.plen(a, v.known_room)
            if hops is None:
                continue
            exit_hops, exit_len = self.plen(a, "exterior-entry")
            far.append((length, v, hops))
        far.sort(key=lambda x: x[0])
        for length, v, hops in far[:4]:
            room = v.known_room
            if a.denied.get(("abandon", v.id), 0) > self.now:
                continue
            dpath = max((w.danger(h[0]) for h in hops), default=0.0)
            if w.danger(room) > 0.75 or dpath > 0.75:
                opts.append(_opt("abandon", v.id, f"give up on {v.name} for now (fire)", {
                    "name": v.name, "danger_dest": round(w.danger(room), 2), "danger_path": round(dpath, 2)}))
            path_rooms = [h[0] for h in hops]
            unstable = any(self._flight(a.room, hops, i) in w.unstable for i in range(len(hops)))
            opts.append(_opt("fetch", v.id, f"go to {v.name} ({pretty_room(room)})", {
                "victim": v.id, "name": v.name, "room": room, "dist": round(length, 1), "eta": round(length / a.speed, 1),
                "danger_path": round(max((w.danger(r) for r in path_rooms), default=0.0), 2), "danger_dest": round(w.danger(room), 2),
                "locked": 1.0 if room in w.locked else 0.0, "unstable": 1.0 if unstable else 0.0,
                "assigned": 1.0 if (a.task or {}).get("victim") == v.id else 0.0,
                "vulnerable": 1.0 if v.id in VULNERABLE else 0.0, "followers": len(followers),
                "denied": 1.0 if a.denied.get(("breach_door", room), 0) > self.now else 0.0,
                "on_the_way": 1.0 if (followers and length / a.speed < 14) else 0.0}))
        if followers:
            hops, length = self.plen(a, "exterior-entry")
            if hops is not None:
                others = sum(1 for v in waiting if v.id not in {f.id for f in followers})
                opts.append(_opt("evacuate", None, f"take {len(followers)} out the front door", {
                    "followers": len(followers), "eta": round(length / min(a.speed, min(f.speed for f in followers)), 1),
                    "min_health": round(min(f.health for f in followers), 2), "danger_path": round(max((w.danger(h[0]) for h in hops), default=0.0), 2),
                    "others_waiting": others}))
            if w.ladder_room and w.ladder_room == a.room:
                opts.append(_opt("evacuate_ladder", w.ladder_room, f"lower {len(followers)} down the ladder", {"followers": len(followers)}))
        return _number(opts)

    @staticmethod
    def _flight(start, hops, i):
        from world import flight_of
        prev = start if i == 0 else hops[i - 1][0]
        return flight_of(prev, hops[i][0])

    # -- director ---------------------------------------------------------
    def director_options(self):
        if self.now < 14 or len(self.twists) >= 3 or self.now - self.last_twist_t < 12:
            return None
        w, vs = self.world, self.victims
        opts = [_opt("none", None, "no twist yet", {})]
        on_up = sum(1 for r in self.robots if not r.disabled and 2 <= floor_of(r.room) <= 4)
        up_vics = sum(1 for v in vs.values() if not v.resolved and floor_of(v.room) >= 3)
        free = [k for k in (1, 2, 3, 4) if k not in w.collapsed and w.fire[f"{k}-hall"] + w.fire[f"{k + 1}-hall"] >= 0.25]
        if "stair-collapse" not in self.twists and free and self.now > 28:
            opts.append(_opt("twist", "stair-collapse", "the stairwell gives way", {
                "score": 0.15 + 0.5 * (on_up > 0) + 0.15 * min(up_vics, 3) * 0.4, "why": "Robots are on the upper floors and the fire is in the stair core."}))
        c, p = vs["victim-child"], vs["victim-parent"]
        if "child-missing" not in self.twists and c.known_room and p.known_room and not c.resolved and c.leader is None:
            opts.append(_opt("twist", "child-missing", "the child slips away", {"score": 0.45, "why": "The child is found but not yet moving; the parent's grip loosens."}))
        if "power-loss" not in self.twists and self.now > 33:
            opts.append(_opt("twist", "power-loss", "the power goes out", {"score": 0.25, "why": "The building's grid fails; scans get unreliable."}))
        hot = [r for r in ROOMS if w.fire[r] >= 0.6 and any(w.smoke[n] > 0.5 for n, _, _, _ in links(r) if not is_exterior(n))]
        if hot and "flashover" not in self.twists:
            opts.append(_opt("twist", "flashover", "a room flashes over", {"score": 0.5, "why": "Heat and smoke have built up in an already blazing room."}))
        closed_burning = [r for r in self.robots if not r.disabled and any(
            w.fire[n] >= 0.5 and not w.door_between(r.room, n) is None and not w.door_open.get(w.door_between(r.room, n), True)
            for n, _, k, _ in links(r.room) if k == "door")]
        if closed_burning:
            opts.append(_opt("twist", "backdraft", "a sealed fire flashes over", {"score": 0.7, "why": "A robot is at the door of a sealed, burning room."}))
        panicked = [v for v in vs.values() if not v.resolved and v.leader is None and v.panic > 0.5 and v.status in ("trapped", "found")]
        if panicked and "victim-moves" not in self.twists:
            opts.append(_opt("twist", "victim-moves", "a panicked resident runs", {"score": 0.55, "why": "Someone's panic finally breaks."}))
        return _number(opts) if len(opts) > 1 else None
