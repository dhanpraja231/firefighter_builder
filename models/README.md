# models

Character models for the Three.js scene (SPEC.md section 3).

## Firefighters

`scout-1`, `suppression-1`, `rescue-1` and `commander` all use `pmx/Firefighter.pmx`, loaded with `MMDLoader`
(see `runcycle/main.js`). Tell the four apart in the scene with a tint or a name tag.

## People (`people/*.glb`), used by `runcycle/`

Realistic-proportion humans from [Microsoft Rocketbox](https://github.com/microsoft/Microsoft-Rocketbox) (MIT, see
`people/LICENSE-Rocketbox.md`), converted to GLB with motion-capture walk and run clips baked in. Heights are in meters
(1.73 to 1.82 m). Rebuild with `zsh models/tools/build_people.sh` (needs Blender in `/Applications`).

| Persona | File | Clips |
| --- | --- | --- |
| victim-1 (elderly) | `Female_Adult_01.glb` | `f_walk_slow_01`, `f_walk_neutral`, `f_run_neutral` |
| victim-2 (panicked) | `Male_Adult_01.glb` | `m_run_fast_01`, `m_run_neutral`, `m_walk_neutral` |
| victim-3 (injured) | `Female_Adult_02.glb` | `f_walk_injured`, `f_run_injured`, `f_walk_neutral` |
| victim-4 (stubborn) | `Business_Male_01.glb` | `m_walk_neutral`, `m_run_slow_01`, `m_run_neutral` |
| spare | `Male_Adult_02.glb`, `Business_Female_01.glb` | walk and run |

The clips move the root bone (`Bip01`) forward. For in-place playback, flatten the Z of the `Bip01.position` track,
as `inPlace()` in `runcycle/main.js` does. Rocketbox doesn't label ages, so the avatar for the elderly persona was
picked without seeing it and may need swapping.

## Chibi victims (`victims/*.glb`), no longer used by `runcycle/`

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
