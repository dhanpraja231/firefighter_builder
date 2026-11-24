import casualBald from "../../../../models/victims/Casual_Bald.glb?url";
import casualFemale from "../../../../models/victims/Casual_Female.glb?url";
import casualMale from "../../../../models/victims/Casual_Male.glb?url";
import oldClassyFemale from "../../../../models/victims/OldClassy_Female.glb?url";
import oldClassyMale from "../../../../models/victims/OldClassy_Male.glb?url";
import suitMale from "../../../../models/victims/Suit_Male.glb?url";
import workerFemale from "../../../../models/victims/Worker_Female.glb?url";

/**
 * The rigged Quaternius characters the `character` branch added under `models/victims/`.
 * Each GLB carries its own animation clips (Idle, Walk, Run, Walk_Carry, Run_Carry,
 * RecieveHit, Death, Victory, PickUp, SitDown, Defeat, ...).
 */
export const MODEL_URLS = {
  casualBald,
  casualFemale,
  casualMale,
  oldClassyFemale,
  oldClassyMale,
  suitMale,
  workerFemale,
} as const;

export type ModelKey = keyof typeof MODEL_URLS;
export type CharacterKind = "robot" | "victim";

export interface CharacterVisual {
  label: string;
  kind: CharacterKind;
  /** Accent color: tints the shirt (and vest/hat where the rig has them). */
  color: string;
  /** Standing height in meters; the rig is scaled to this. */
  height?: number;
  model: ModelKey;
  /** Adds a helmet in the accent color (the firefighter robots). */
  helmet?: boolean;
}
