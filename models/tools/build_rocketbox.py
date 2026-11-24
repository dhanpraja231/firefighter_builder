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

# --- animations: import, move the action onto the avatar's rig ------------
arm.animation_data_create()
for path in anim_paths:
    clip = os.path.basename(path).replace('.max.fbx', '').replace('.fbx', '')
    new = import_fbx(path)
    src = next(o for o in new if o.type == 'ARMATURE')
    action = src.animation_data.action
    action.name = clip
    action.use_fake_user = True
    # The root bone (Bip01) still carries the forward travel; the web app strips it
    # at load time (see runcycle/main.js, inPlace()).
    for o in new:
        bpy.data.objects.remove(o)
    track = arm.animation_data.nla_tracks.new()
    track.name = clip
    start = int(action.frame_range[0])
    strip = track.strips.new(clip, start, action)
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
