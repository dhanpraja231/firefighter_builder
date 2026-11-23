# models

Character models for the Three.js scene (SPEC.md section 3).

## Firefighters

`scout-1`, `suppression-1`, `rescue-1` and `commander` all use `pmx/Firefighter.pmx`, loaded with `MMDLoader`
(see `runcycle/main.js`). Tell the four apart in the scene with a tint or a name tag.

## Victims (`victims/*.glb`)

Rigged low-poly humans from the Quaternius Ultimate Animated Character Pack. Each GLB contains its own clips:
`Idle`, `Walk`, `Run`, `Walk_Carry`, `Run_Carry`, `SitDown`, `StandUp`, `Defeat`, `Death`, `RecieveHit`, `Victory`,
`PickUp`, `Roll`, `Jump`, plus combat clips you can ignore. `Casual_Bald.glb` has no `Run`.

| Persona (SPEC.md section 4) | Model | Useful clips |
| --- | --- | --- |
| Elderly, walker, stubborn about her cat (Mrs. Okafor) | `OldClassy_Female.glb` | `Idle`, `Walk` at a slow `timeScale` |
| Panicked and moving | `Casual_Male.glb` | `Run`, `RecieveHit` (flinch), `Roll` |
| Injured and immobile | `Worker_Female.glb` | `SitDown` and hold the last frame, `Defeat`, `Death` for `lost` |
| Stubborn and arguing | `Suit_Male.glb` | `Idle`, `Defeat` (arguing gesture), `Walk` |
| Spares | `OldClassy_Male.glb`, `Casual_Female.glb`, `Casual_Bald.glb` | |

Load with `GLTFLoader`, then play clips through an `AnimationMixer`.

## Cat (`animals/Cat.fbx`)

The cat from the Quaternius Animal Pack Vol.2. It only comes as FBX, so load it with `FBXLoader`, or convert it to GLB
in Blender if you want one loader for everything.

## Sources and license

All files are CC0 1.0 (public domain) by [Quaternius](https://quaternius.com). Credit is not required, but please
include it in the film credits.

- Victims: Ultimate Animated Character Pack, downloaded as GLB from the
  [ghostname-3d-assets](https://github.com/Yametech12/ghostname-3d-assets) mirror because the official Google Drive
  link was rate-limited.
- Cat: [Animal Pack Vol.2 on OpenGameArt](https://opengameart.org/content/animated-animales-low-poly).
