import casualBald from "../../../../models/victims/Casual_Bald.glb?url";
import casualFemale from "../../../../models/victims/Casual_Female.glb?url";
import casualMale from "../../../../models/victims/Casual_Male.glb?url";
import oldClassyFemale from "../../../../models/victims/OldClassy_Female.glb?url";
import oldClassyMale from "../../../../models/victims/OldClassy_Male.glb?url";
import suitMale from "../../../../models/victims/Suit_Male.glb?url";
import workerFemale from "../../../../models/victims/Worker_Female.glb?url";

/**
 * Rigged Quaternius characters (`models/victims/`). Each GLB carries its own animation clips
 * (Idle, Walk, Run, Walk_Carry, RecieveHit, Death, Victory, PickUp, SitDown, Defeat, ...), which is
 * what lets residents visibly react: plead when found, flinch in smoke, collapse when lost,
 * celebrate when rescued. `RiggedCharacter` plays them.
 */
export const RIG_URLS = {
  casualBald,
  casualFemale,
  casualMale,
  oldClassyFemale,
  oldClassyMale,
  suitMale,
  workerFemale,
} as const;

export type RigKey = keyof typeof RIG_URLS;
export type CharacterKind = "robot" | "victim";

/** One agent's look. Shared by both body implementations (see `Character.tsx` and `RiggedCharacter.tsx`). */
export interface CharacterVisual {
  label: string;
  kind: CharacterKind;
  /** Accent color: name tag, shirt tint, helmet. */
  color: string;
  /** Real-world height in meters the body is scaled to. */
  height?: number;
  /** Victims (Character.tsx fallback): Rocketbox model file in `public/people/` (no extension). */
  model?: string;
  /** Victims (Character.tsx fallback): walk clip to use from that model. */
  walkClip?: string;
  /** Victims: which Quaternius rig `RiggedCharacter` plays. Robots use the firefighter PMX in `Character.tsx`. */
  rig?: RigKey;
  /** Adds a hard hat in the accent color on a Quaternius rig. */
  helmet?: boolean;
}
