import type { FloorId } from "./types";

export const palette = {
  /** Mid-night blue — used for fog / clearColor so the sky isn't a black void. */
  sky: "#152038",
  fog: "#1a2438",
  horizon: "#4a3f32",
  brick: "#7d4a44",
  plaster: "#f2e7d7",
  plasterDeep: "#e2d2bc",
  fascia: "#2a2624",
  slab: "#efe4d4",
  woodTrim: "#6b4a34",
  door: "#7c4e32",
  doorDark: "#5c3a28",
  rail: "#3c4652",
  tread: "#c4beb4",
  stringer: "#6a5346",
  glass: "#1a3348",
  windowGlow: "#ffbf84",
  fireGlow: "#ff6a2a",
  bulb: "#fff1d2",
  metal: "#c5ccd4",
  engine: "#c42828",
  engineDark: "#8e1c1c",
  cab: "#f2efe9",
  street: "#2a2e36",
  sidewalk: "#4c515a",
  curb: "#6a645c",
  lane: "#d8d2c4",
  hydrant: "#d23b32",
  moon: "#e7eefc",
  tree: "#1e3a34",
  grass: "#2a3f28",
  grassLit: "#355a32",
} as const;

export interface FloorAccent {
  wood: string;
  tile: string;
  sofa: string;
  bed: string;
  rug: string;
  cabinet: string;
}

export const FLOOR_ACCENTS: Record<FloorId, FloorAccent> = {
  1: { wood: "#c6a376", tile: "#c5cec9", sofa: "#8d4b3c", bed: "#ddd6cf", rug: "#6e3b3b", cabinet: "#5c676e" },
  2: { wood: "#c4956a", tile: "#c9d0c8", sofa: "#5c6a78", bed: "#ead8cb", rug: "#7a3e2e", cabinet: "#6a5a52" },
  3: { wood: "#b9996e", tile: "#d0d5d2", sofa: "#3e6b5e", bed: "#d5ddd8", rug: "#2f4a44", cabinet: "#5a6560" },
  4: { wood: "#d1b48a", tile: "#c8d0d4", sofa: "#6d5278", bed: "#e4d7c8", rug: "#4a3a58", cabinet: "#655868" },
  5: { wood: "#bfa37a", tile: "#d2d0c6", sofa: "#8a5a32", bed: "#ddd6ea", rug: "#5a3a28", cabinet: "#5e564c" },
};
