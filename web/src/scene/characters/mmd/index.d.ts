// Minimal types for the vendored three r171 MMD modules (see README.md in this folder).
declare module "*/mmd/MMDLoader.js" {
  import { Loader, SkinnedMesh } from "three";
  export class MMDLoader extends Loader<SkinnedMesh> {
    load(url: string, onLoad: (mesh: SkinnedMesh) => void, onProgress?: (e: ProgressEvent) => void, onError?: (e: unknown) => void): void;
  }
}

declare module "*/mmd/MMDAnimationHelper.js" {
  import { AnimationClip, AnimationMixer, SkinnedMesh } from "three";
  export class MMDAnimationHelper {
    constructor(params?: { afterglow?: number; sync?: boolean; pmxAnimation?: boolean });
    meshes: SkinnedMesh[];
    objects: WeakMap<SkinnedMesh, { mixer: AnimationMixer }>;
    add(mesh: SkinnedMesh, params?: { animation?: AnimationClip | AnimationClip[]; physics?: boolean }): this;
    remove(mesh: SkinnedMesh): this;
    update(delta: number): this;
  }
}

declare module "*/runCycle.js" {
  import { AnimationClip, SkinnedMesh } from "three";
  export const RUN: { period: number; stance: number; strideHalf: number; [k: string]: number };
  export function groundSpeed(p?: typeof RUN): number;
  export function createRunClip(mesh: SkinnedMesh, p?: typeof RUN): AnimationClip;
}
