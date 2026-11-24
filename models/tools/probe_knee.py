# Knee hinge check: for each frame, the bend axis (thigh_dir x calf_dir) should point
# the same way relative to the pelvis's lateral axis. A sign flip = knee bent backwards.
# blender -b --factory-startup -P probe_knee.py -- file.fbx|file.glb [clip]
import sys
import bpy

args = sys.argv[sys.argv.index('--') + 1:]
path = args[0]
clip = args[1] if len(args) > 1 else None
bpy.ops.wm.read_factory_settings(use_empty=True)
if path.endswith('.glb'):
    bpy.ops.import_scene.gltf(filepath=path)
else:
    bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=False)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
if clip:
    arm.animation_data.action = bpy.data.actions[clip]
act = arm.animation_data.action
f0, f1 = (int(round(x)) for x in act.frame_range)


def name(side, part):
    for n in (f'Bip01 {side} {part}', f'Bip01_{side}_{part}'):
        if n in arm.pose.bones:
            return arm.pose.bones[n]


pel = arm.pose.bones.get('Bip01 Pelvis') or arm.pose.bones.get('Bip01_Pelvis')
mw = arm.matrix_world
for side in ('L', 'R'):
    th, ca, ft = name(side, 'Thigh'), name(side, 'Calf'), name(side, 'Foot')
    signs = []
    for f in range(f0, f1 + 1):
        bpy.context.scene.frame_set(f)
        h, k, a = (mw @ b.head for b in (th, ca, ft))
        lr = (mw @ name('L', 'Thigh').head) - (mw @ name('R', 'Thigh').head)  # pelvis lateral axis (L-R)
        axis = (k - h).normalized().cross((a - k).normalized())
        bend = (k - h).angle(a - k)
        if bend > 0.15:
            signs.append(1 if axis.dot(lr) > 0 else -1)
    print(f'{path.split("/")[-1]} {act.name} {side}: +{signs.count(1)} -{signs.count(-1)}')
