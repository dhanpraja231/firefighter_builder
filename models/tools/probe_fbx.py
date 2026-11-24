# Blender probe: print armature, bone names, materials and images of an FBX.
# blender -b --factory-startup -P probe_fbx.py -- file.fbx [anim.fbx]
import sys
import bpy

args = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
for path in args:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=False)
    new = [o for o in bpy.data.objects if o not in before]
    print('==', path)
    for o in new:
        print('  obj', o.type, o.name, 'dims', tuple(round(d, 3) for d in o.dimensions))
        if o.type == 'ARMATURE':
            names = [b.name for b in o.data.bones]
            print('  bones', len(names), names[:12], '...')
            if o.animation_data and o.animation_data.action:
                a = o.animation_data.action
                print('  action', a.name, a.frame_range[:], 'fcurves', len(a.fcurves))
print('materials', [m.name for m in bpy.data.materials])
print('images', [(i.name, i.filepath) for i in bpy.data.images])
print('fps', bpy.context.scene.render.fps)
