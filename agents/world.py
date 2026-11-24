"""Building map and fire physics for the story engine.

Mirrors web/src/scene/layout.ts: same room ids ('{floor}-{kind}'), same door
ids, same connectivity (hall <-> living/kitchen <-> bedroom <-> landing, one
stair flight per floor gap between the halls). Positions are meters, y-up,
origin at the south-west corner of story 1.
"""

from __future__ import annotations

import math
from heapq import heappop, heappush

FLOORS = (1, 2, 3, 4, 5)
FLOOR_Y = {1: 0.0, 2: 3.0, 3: 6.0, 4: 9.0, 5: 12.0}
KINDS = ("living", "bedroom-w", "kitchen", "bedroom-e", "hall", "landing")

# Room centers, local to each floor (same numbers as layout.ts).
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
# Where rescued people wait, on the sidewalk next to the entry.
SAFE_SPOTS = [(-3.0 - 0.9 * (i % 4), 0.0, 0.6 + 0.9 * (i // 4)) for i in range(10)]
STAIR_LEN = 7.0  # walking distance of one switchback flight

LOCAL_EDGES = (
    ("hall", "living", "door-living-hall"),
    ("hall", "kitchen", "door-kitchen-hall"),
    ("living", "bedroom-w", "door-living-bed"),
    ("kitchen", "bedroom-e", "door-kitchen-bed"),
    ("bedroom-w", "landing", "door-bed-w-landing"),
    ("bedroom-e", "landing", "door-bed-e-landing"),
)

# Rooms with a window the aerial ladder can reach (west facade, floors 1-4).
LADDER_WINDOW = {"living": "window-living-w", "bedroom-w": "window-bed-w"}
LADDER_MAX_FLOOR = 4
HOSE_MAX_FLOOR = 3


def room_id(floor: int, kind: str) -> str:
    return f"{floor}-{kind}"


def is_exterior(room: str) -> bool:
    return room.startswith("exterior-")


def split_room(room: str) -> tuple[int, str]:
    f, k = room.split("-", 1)
    return int(f), k


def floor_of(room: str) -> int:
    return 0 if is_exterior(room) else split_room(room)[0]


def xyz(room: str) -> tuple[float, float, float]:
    if is_exterior(room):
        return EXTERIOR[room.split("-", 1)[1]]
    f, k = split_room(room)
    x, z = ROOM_XZ[k]
    return (x, FLOOR_Y[f], z)


def position_payload(room: str) -> dict:
    x, y, z = xyz(room)
    return {"x": x, "y": y, "z": z, "floor": -1 if is_exterior(room) else floor_of(room) - 1}


def pretty(room: str) -> str:
    if is_exterior(room):
        return room.split("-", 1)[1].replace("-", " ")
    f, k = split_room(room)
    return f"floor {f} {k.replace('-', ' ')}"


ROOMS = [room_id(f, k) for f in FLOORS for k in KINDS]
ALL_NODES = ROOMS + ["exterior-engine", "exterior-entry"]


def _dist(a: str, b: str) -> float:
    ax, ay, az = xyz(a)
    bx, by, bz = xyz(b)
    return math.hypot(ax - bx, az - bz)


# Static adjacency: room -> list of (neighbor, distance, kind, door_id or None).
# kind in {"door", "stairs", "exit", "street"}.
_LINKS: dict[str, list[tuple[str, float, str, str | None]]] = {n: [] for n in ALL_NODES}
for _f in FLOORS:
    for _a, _b, _d in LOCAL_EDGES:
        ra, rb = room_id(_f, _a), room_id(_f, _b)
        _w = _dist(ra, rb)
        _LINKS[ra].append((rb, _w, "door", f"{_f}-{_d}"))
        _LINKS[rb].append((ra, _w, "door", f"{_f}-{_d}"))
    if _f < FLOORS[-1]:
        lo, hi = room_id(_f, "hall"), room_id(_f + 1, "hall")
        _LINKS[lo].append((hi, STAIR_LEN, "stairs", None))
        _LINKS[hi].append((lo, STAIR_LEN, "stairs", None))
_LINKS["1-hall"].append(("exterior-entry", _dist("exterior-entry", "1-hall"), "exit", None))
_LINKS["exterior-entry"].append(("1-hall", _dist("exterior-entry", "1-hall"), "exit", None))
_LINKS["exterior-entry"].append(("exterior-engine", _dist("exterior-entry", "exterior-engine"), "street", None))
_LINKS["exterior-engine"].append(("exterior-entry", _dist("exterior-entry", "exterior-engine"), "street", None))


def links(room: str):
    return _LINKS[room]


def flight_of(a: str, b: str) -> int | None:
    """Lower floor of the stair flight between two halls, else None."""
    if is_exterior(a) or is_exterior(b):
        return None
    fa, ka = split_room(a)
    fb, kb = split_room(b)
    if ka == "hall" and kb == "hall" and abs(fa - fb) == 1:
        return min(fa, fb)
    return None


class World:
    """Fire, smoke, doors, and structure. All randomness comes from the rng passed in.

    Fire model: every room has fuel. A burning room grows toward 1.0 (faster with open doors =
    more oxygen), burns its fuel down, and dies back once the fuel is gone. Flame ignites
    neighbors stochastically (open door >> closed door; up the stair core >> down). Smoke
    relaxes toward local fire and leaks further and faster than flame, through closed doors
    too, and rises up the stairs."""

    def __init__(self, rng):
        self.fire = {r: 0.0 for r in ROOMS}
        self.smoke = {r: 0.0 for r in ROOMS}
        self.fuel = {r: (1.3 if r.endswith("kitchen") else rng.uniform(0.45, 1.0)) for r in ROOMS}
        self.door_open = {f"{f}-{d}": rng.random() < 0.3 for f in FLOORS for _, _, d in LOCAL_EDGES}
        self.collapsed: set[int] = set()  # lower floor of a collapsed flight
        self.unstable: set[int] = set()  # flights weakened by a collapse next to them
        self.locked: set[str] = set()  # rooms whose door a victim locked
        self.spraying: dict[str, tuple[float, float]] = {}  # room -> (until, strength)
        self.vented: set[str] = set()
        self.ladder_room: str | None = None
        self.power = True
        self.ignitions: list[tuple[str, str, str, bool]] = []  # (room, from_room, link kind, door open) this step
        self.ignited_at: dict[str, float] = {}
        self._rep_fire: dict[str, float] = {}
        self._rep_smoke: dict[str, float] = {}

    # -- queries ----------------------------------------------------------
    def door_between(self, a: str, b: str) -> str | None:
        for nbr, _, kind, door in links(a):
            if nbr == b and kind == "door":
                return door
        return None

    def danger(self, room: str) -> float:
        if is_exterior(room):
            return 0.0
        return min(1.0, self.fire[room] + 0.35 * self.smoke[room])

    def blocked(self, a: str, b: str, drone: bool = False) -> bool:
        fl = flight_of(a, b)
        return fl is not None and fl in self.collapsed and not drone

    def path(self, src: str, dst: str, drone: bool = False, avoid: float = 1.0):
        """Dijkstra over the room graph. Returns [(room, dist, kind, door)] or None.
        `avoid` scales how much fire/smoke inflates a hop's cost (robots detour when they can)."""
        if src == dst:
            return []
        best = {src: 0.0}
        prev: dict[str, tuple[str, float, str, str | None]] = {}
        heap = [(0.0, src)]
        while heap:
            cost, node = heappop(heap)
            if node == dst:
                break
            if cost > best.get(node, 1e9):
                continue
            for nbr, d, kind, door in links(node):
                if self.blocked(node, nbr, drone):
                    continue
                c = cost + d + avoid * 22.0 * self.danger(nbr) ** 1.5
                if c < best.get(nbr, 1e9):
                    best[nbr] = c
                    prev[nbr] = (node, d, kind, door)
                    heappush(heap, (c, nbr))
        if dst not in prev:
            return None
        hops = []
        node = dst
        while node != src:
            p, d, kind, door = prev[node]
            hops.append((node, d, kind, door))
            node = p
        hops.reverse()
        return hops

    # -- mutations --------------------------------------------------------
    def ignite(self, room: str, level: float = 0.1, now: float = 0.0) -> None:
        if self.fire[room] < 0.02:
            self.ignited_at[room] = now
        self.fire[room] = max(self.fire[room], level)

    def step(self, now: float, rng) -> list[dict]:
        """Advance one second. Returns world events whose value moved >= 0.08 since last reported."""
        spread = 0.05
        self.ignitions = []
        for room in ROOMS:
            lvl = self.fire[room]
            if lvl < 0.02:
                continue
            spray = self.spraying.get(room)
            openings = sum(1 for _, _, k, d in links(room) if k == "door" and self.door_open.get(d, False))
            growth = (0.012 + 0.07 * lvl * (1.0 - lvl)) * (0.5 + 0.4 * min(openings, 2))
            if spray and spray[0] > now:
                lvl = max(0.0, min(1.0, lvl + 0.5 * growth - spray[1]))
                self.fuel[room] -= 0.0016 * lvl
            elif self.fuel[room] > 0:
                lvl = min(1.0, lvl + growth)
                self.fuel[room] -= 0.0032 * lvl
            else:
                lvl = max(0.0, lvl - 0.02)  # burned out: dying back
            self.fire[room] = lvl if lvl >= 0.02 else 0.0
            if lvl < 0.02:
                continue
            for nbr, _, kind, door in links(room):
                if is_exterior(nbr) or self.fire[nbr] >= 0.02 or self.fuel[nbr] <= 0:
                    continue
                p = spread * lvl
                is_open = True
                if kind == "door":
                    is_open = self.door_open.get(door, False)
                    p *= 1.0 if is_open else 0.2
                elif kind == "stairs":
                    p *= 0.9 if floor_of(nbr) > floor_of(room) else 0.2
                sp = self.spraying.get(nbr)
                if sp and sp[0] > now:
                    p *= 0.25
                if rng.random() < p:
                    self.fire[nbr] = 0.1
                    self.ignited_at[nbr] = now
                    self.ignitions.append((nbr, room, kind, is_open))
        # smoke relaxes toward a target set by local fire and leaking neighbors; it outruns flame
        for room in ROOMS:
            target = self.fire[room]
            for nbr, _, kind, door in links(room):
                if is_exterior(nbr):
                    continue
                leak = 1.0 if (kind == "stairs" or self.door_open.get(door, False)) else 0.45
                if kind == "stairs" and floor_of(nbr) < floor_of(room):
                    leak *= 0.6
                target = max(target, self.smoke[nbr] * 0.82 * leak)
            if room in self.vented:
                target *= 0.5
            cur = self.smoke[room]
            self.smoke[room] = cur + (target - cur) * (0.2 if target > cur else 0.035)
        out: list[dict] = []
        for room in ROOMS:
            f = round(self.fire[room], 2)
            if abs(f - self._rep_fire.get(room, 0.0)) >= 0.08 or (f < 0.02 and self._rep_fire.get(room, 0.0) > 0.0):
                self._rep_fire[room] = f if f >= 0.02 else 0.0
                out.append({"type": "fire", "roomId": room, "intensity": self._rep_fire[room]})
            s = round(self.smoke[room], 2)
            if abs(s - self._rep_smoke.get(room, 0.0)) >= 0.08 or (s < 0.03 and self._rep_smoke.get(room, 0.0) > 0.0):
                self._rep_smoke[room] = s if s >= 0.03 else 0.0
                out.append({"type": "smoke", "roomId": room, "intensity": self._rep_smoke[room]})
        return out
