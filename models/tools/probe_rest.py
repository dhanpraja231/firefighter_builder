# Compare rest poses of leg bones between an avatar FBX and an animation FBX.
# blender -b --factory-startup -P probe_rest.py -- avatar.fbx anim.fbx
import sys
import bpy

args = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
BONES = ['Bip01 Pelvis', 'Bip01 L Thigh', 'Bip01 L Calf', 'Bip01 L Foot', 'Bip01 R Thigh', 'Bip01 R Calf']

for path in args:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=False)
    arm = next(o for o in bpy.data.objects if o not in before and o.type == 'ARMATURE')
    print('==', path.split('/')[-1], 'obj rot', [round(x, 3) for x in arm.rotation_euler], 'scale', [round(x, 3) for x in arm.scale])
    for n in BONES:
        b = arm.data.bones.get(n)
        if not b:
            print('  missing', n)
            continue
        q = b.matrix_local.to_quaternion()
        print(f'  {n:16s} head', [round(x, 3) for x in b.head_local], 'q', [round(x, 3) for x in q])
