import type { NavGraph } from "./types";

/**
 * Shortest path (Dijkstra, edges are undirected) between two nav graph node
 * ids, by meters. Returns node ids from `from` to `to` inclusive, or `null`
 * if there is no route. This is routing geometry only: it does not decide
 * who should go where or when.
 */
export function findPath(graph: NavGraph, from: string, to: string): string[] | null {
  if (!graph.nodes[from] || !graph.nodes[to]) return null;
  if (from === to) return [from];

  const adjacency = new Map<string, Array<{ to: string; weight: number }>>();
  const addEdge = (a: string, b: string, weight: number) => {
    if (!adjacency.has(a)) adjacency.set(a, []);
    adjacency.get(a)!.push({ to: b, weight });
  };
  for (const edge of graph.edges) {
    const weight = edge.distance ?? straightLine(graph, edge.a, edge.b);
    addEdge(edge.a, edge.b, weight);
    addEdge(edge.b, edge.a, weight);
  }

  const dist = new Map<string, number>([[from, 0]]);
  const prev = new Map<string, string>();
  const visited = new Set<string>();
  const unvisited = new Set(Object.keys(graph.nodes));

  while (unvisited.size > 0) {
    let current: string | null = null;
    let currentDist = Infinity;
    for (const id of unvisited) {
      const d = dist.get(id) ?? Infinity;
      if (d < currentDist) {
        currentDist = d;
        current = id;
      }
    }
    if (current === null) break;
    unvisited.delete(current);
    visited.add(current);
    if (current === to) break;

    for (const { to: neighbor, weight } of adjacency.get(current) ?? []) {
      if (visited.has(neighbor)) continue;
      const alt = currentDist + weight;
      if (alt < (dist.get(neighbor) ?? Infinity)) {
        dist.set(neighbor, alt);
        prev.set(neighbor, current);
      }
    }
  }

  if (!dist.has(to)) return null;
  const path = [to];
  let node = to;
  while (node !== from) {
    const previous = prev.get(node);
    if (!previous) return null;
    path.push(previous);
    node = previous;
  }
  return path.reverse();
}

function straightLine(graph: NavGraph, a: string, b: string): number {
  const na = graph.nodes[a];
  const nb = graph.nodes[b];
  if (!na || !nb) return 0;
  return Math.hypot(na.position[0] - nb.position[0], na.position[1] - nb.position[1], na.position[2] - nb.position[2]);
}

/** Total length of a resolved path, in meters. */
export function pathLength(graph: NavGraph, path: string[]): number {
  let total = 0;
  for (let i = 1; i < path.length; i += 1) {
    total += straightLine(graph, path[i - 1], path[i]);
  }
  return total;
}

/** World-space waypoints for a resolved path, in order. */
export function pathWaypoints(graph: NavGraph, path: string[]): Array<[number, number, number]> {
  return path.map((id) => graph.nodes[id].position);
}
