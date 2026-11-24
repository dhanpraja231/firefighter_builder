import { buildExteriorLayout, buildNavGraph, createBuildingLayout } from "../scene/layout";
import { findPath, pathWaypoints } from "../scene/nav";
import type { NavGraph } from "../scene/types";

export type Vec3 = [number, number, number];

/** A walkable polyline with cumulative lengths, so a fraction of the trip maps to a point and a heading. */
export interface Route {
  points: Vec3[];
  /** cumulative[i] = meters from points[0] to points[i]. */
  cumulative: number[];
  total: number;
}

let graph: NavGraph | null = null;
const cache = new Map<string, Route>();

function navGraph(): NavGraph {
  if (!graph) graph = buildNavGraph(createBuildingLayout(), buildExteriorLayout());
  return graph;
}

function dist(a: Vec3, b: Vec3): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

/** Closest nav node; vertical distance is weighted so a point on floor 3 never snaps to floor 2. */
function nearestNode(p: Vec3): string {
  let best = "";
  let bestScore = Infinity;
  for (const node of Object.values(navGraph().nodes)) {
    const q = node.position;
    const score = Math.hypot(p[0] - q[0], (p[1] - q[1]) * 4, p[2] - q[2]);
    if (score < bestScore) {
      bestScore = score;
      best = node.id;
    }
  }
  return best;
}

function makeRoute(points: Vec3[]): Route {
  const kept: Vec3[] = [];
  for (const p of points) {
    if (kept.length === 0 || dist(kept[kept.length - 1], p) > 1e-3) kept.push(p);
  }
  if (kept.length === 1) kept.push(kept[0]);
  const cumulative = [0];
  for (let i = 1; i < kept.length; i++) cumulative.push(cumulative[i - 1] + dist(kept[i - 1], kept[i]));
  return { points: kept, cumulative, total: cumulative[cumulative.length - 1] };
}

/**
 * Route between two world positions through the building's nav graph (doors, halls, stairs), so
 * characters walk through doorways and up the stairs instead of cutting straight through walls
 * and floors. Events only carry the endpoints; this supplies the path between them.
 */
export function planRoute(a: Vec3, b: Vec3): Route {
  const key = `${a.map((n) => n.toFixed(2)).join(",")}>${b.map((n) => n.toFixed(2)).join(",")}`;
  const hit = cache.get(key);
  if (hit) return hit;

  const from = nearestNode(a);
  const to = nearestNode(b);
  const ids = from === to ? [from] : findPath(navGraph(), from, to);
  const interior = ids ? pathWaypoints(navGraph(), ids) : [];
  // Same-room hops stay a straight line; longer trips follow the graph between the two end points.
  const route = makeRoute(from === to || !ids ? [a, b] : [a, ...interior, b]);
  cache.set(key, route);
  return route;
}

export interface RouteSample {
  position: Vec3;
  /** Yaw (radians) of the segment being walked, matching the scene's `atan2(dx, dz)` convention. */
  heading: number;
}

/** Position and facing `frac` (0..1) of the way along the route. */
export function sampleRoute(route: Route, frac: number): RouteSample {
  const f = Math.min(1, Math.max(0, frac));
  const target = f * route.total;
  let i = 1;
  while (i < route.points.length - 1 && route.cumulative[i] < target) i++;
  const a = route.points[i - 1];
  const b = route.points[i];
  const segLen = route.cumulative[i] - route.cumulative[i - 1];
  const s = segLen > 1e-6 ? (target - route.cumulative[i - 1]) / segLen : 1;
  const position: Vec3 = [a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s, a[2] + (b[2] - a[2]) * s];
  return { position, heading: segmentHeading(a, b) };
}

/** Heading of the last segment of a route (what a character is facing when it arrives). */
export function arrivalHeading(route: Route): number {
  const n = route.points.length;
  return segmentHeading(route.points[n - 2], route.points[n - 1]);
}

function segmentHeading(a: Vec3, b: Vec3): number {
  const dx = b[0] - a[0];
  const dz = b[2] - a[2];
  return dx * dx + dz * dz > 1e-6 ? Math.atan2(dx, dz) : 0;
}
