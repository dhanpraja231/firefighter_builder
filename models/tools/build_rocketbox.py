# Convert a Microsoft Rocketbox avatar (FBX + TGA textures) and some Rocketbox
# in-place animations into one web-ready GLB.
#
# blender -b --factory-startup -P build_rocketbox.py -- \
#   <avatar.fbx> <textures_dir> <out.glb> <anim1.fbx> [anim2.fbx ...]
#
# Clip names in the GLB are the anim file names without ".max.fbx"/".fbx".
import os
import sys
import bpy

TEX_SIZE = 1024

argv = sys.argv[sys.argv.index('--') + 1:]
avatar_path, tex_dir, out_path, *anim_paths = argv

bpy.ops.wm.read_factory_settings(use_empty=True)


def import_fbx(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=False, use_anim=True)
    return [o for o in bpy.data.objects if o not in before]


# --- avatar ---------------------------------------------------------------
objs = import_fbx(avatar_path)
arm = next(o for o in objs if o.type == 'ARMATURE')
meshes = [o for o in objs if o.type == 'MESH']
for o in objs:
    if o.type == 'EMPTY':
        bpy.data.objects.remove(o)
# drop the 2-frame bind "take" that comes with the avatar
if arm.animation_data and arm.animation_data.action:
    junk = arm.animation_data.action
    arm.animation_data.action = None
    bpy.data.actions.remove(junk)

# --- materials: rebuild from the real texture files -----------------------
tex_files = {f.lower(): os.path.join(tex_dir, f) for f in os.listdir(tex_dir)}


def load_image(name):
    path = tex_files.get(name.lower())
    if not path:
        return None
    img = bpy.data.images.load(path, check_existing=True)
    if max(img.size) > TEX_SIZE:
        img.scale(TEX_SIZE, TEX_SIZE)
    return img


for mat in {s.material for m in meshes for s in m.material_slots if s.material}:
    prefix = mat.name  # e.g. f001_body, f001_head, f001_opacity
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.75
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

    color = load_image(prefix + '_color.tga')
    if color:
        tn = nt.nodes.new('ShaderNodeTexImage')
        tn.image = color
        nt.links.new(tn.outputs['Color'], bsdf.inputs['Base Color'])
        if prefix.endswith('_opacity'):
            # eyelashes / hair cards: colour + alpha in one RGBA texture
            nt.links.new(tn.outputs['Alpha'], bsdf.inputs['Alpha'])
            mat.surface_render_method = 'BLENDED'
    normal = load_image(prefix + '_normal.tga')
    if normal:
        normal.colorspace_settings.name = 'Non-Color'
        tn = nt.nodes.new('ShaderNodeTexImage')
        tn.image = normal
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nt.links.new(tn.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])

# --- animations: retarget onto the avatar's rig ----------------------------
# The animation FBXs have a different rest pose from the avatars, so their keys
# (which are relative to the rest pose) can't be copied across: the legs come out
# twisted and the knees bend backwards. Instead, constrain every avatar bone to the
# source bone's orientation in armature space and bake that into new keys.
arm.animation_data_create()
scene = bpy.context.scene
for path in anim_paths:
    clip = os.path.basename(path).replace('.max.fbx', '').replace('.fbx', '')
    new = import_fbx(path)
    src = next(o for o in new if o.type == 'ARMATURE')
    src_action = src.animation_data.action
    f0, f1 = (int(round(x)) for x in src_action.frame_range)

    for pb in arm.pose.bones:
        if pb.name not in src.pose.bones:
            continue
        c = pb.constraints.new('COPY_ROTATION')
        c.target, c.subtarget = src, pb.name
        c.owner_space = c.target_space = 'POSE'
        if pb.parent is None or pb.name == 'Bip01 Pelvis':
            c = pb.constraints.new('COPY_LOCATION')
            c.target, c.subtarget = src, pb.name
            c.owner_space = c.target_space = 'POSE'

    bpy.ops.object.mode_set(mode='OBJECT')
    for o in bpy.data.objects:
        o.select_set(o == arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.pose.select_all(action='SELECT')
    bpy.ops.nla.bake(frame_start=f0, frame_end=f1, only_selected=False, visual_keying=True,
                     clear_constraints=True, use_current_action=False, bake_types={'POSE'})
    bpy.ops.object.mode_set(mode='OBJECT')

    action = arm.animation_data.action
    action.name = clip
    action.use_fake_user = True
    # Root motion is on the armature object itself in these files. Copy those curves
    # over unchanged; the web app strips the forward travel (runcycle/main.js, inPlace()).
    for fc in src_action.fcurves:
        if fc.data_path in ('location', 'rotation_euler', 'rotation_quaternion'):
            dst = action.fcurves.new(fc.data_path, index=fc.array_index)
            for kp in fc.keyframe_points:
                dst.keyframe_points.insert(kp.co[0], kp.co[1], options={'FAST'})
    arm.animation_data.action = None

    for o in new:
        bpy.data.objects.remove(o)
    track = arm.animation_data.nla_tracks.new()
    track.name = clip
    track.strips.new(clip, f0, action)
    track.mute = True
for a in list(bpy.data.actions):
    if '|' in a.name:  # helper/footstep takes from the imported files
        bpy.data.actions.remove(a)
print('clips', [a.name for a in bpy.data.actions])

# --- export ---------------------------------------------------------------
for o in bpy.data.objects:
    o.select_set(o in meshes or o == arm)
bpy.ops.export_scene.gltf(
    filepath=out_path,
    export_format='GLB',
    use_selection=True,
    export_animations=True,
    export_animation_mode='NLA_TRACKS',
    export_image_format='WEBP',
    export_morph=False,
    export_apply=False,
)
print('wrote', out_path)
