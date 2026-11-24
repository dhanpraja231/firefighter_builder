#!/bin/zsh
# Build models/people/*.glb from Microsoft Rocketbox (MIT).
# Downloads the avatar FBX + textures and the in-place animations, then converts with Blender.
#   zsh models/tools/build_people.sh
set -e
HERE=${0:A:h}
OUT=$HERE/../people
CACHE=${ROCKETBOX_CACHE:-/tmp/rocketbox}
BLENDER=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
RAW=https://raw.githubusercontent.com/microsoft/Microsoft-Rocketbox/master/Assets
ANIM=$RAW/Animations/all_animations_max_motextr_xy
mkdir -p $OUT $CACHE/anim

fetch() { [[ -s $2 ]] || curl -sfL -o $2 $1; }

# name  rocketbox-dir  texture-prefix  clips...
build() {
  local name=$1 dir=$2 tex=$3; shift 3
  local av=$CACHE/$name; mkdir -p $av/Textures
  fetch $RAW/Avatars/$dir/Export/$name.fbx $av/$name.fbx
  for t in body_color body_normal head_color head_normal opacity_color; do
    fetch $RAW/Avatars/$dir/Textures/${tex}_$t.tga $av/Textures/${tex}_$t.tga
  done
  local anims=()
  for a in $@; do fetch $ANIM/$a.max.fbx $CACHE/anim/$a.fbx; anims+=$CACHE/anim/$a.fbx; done
  $BLENDER -b --factory-startup -P $HERE/build_rocketbox.py -- $av/$name.fbx $av/Textures $OUT/$name.glb $anims \
    2>&1 | grep -E '^(clips|wrote)|Error|Traceback'
}

build Female_Adult_01    Adults/Female_Adult_01          f001 f_walk_slow_01 f_walk_neutral f_run_neutral
build Male_Adult_01      Adults/Male_Adult_01            m002 m_run_fast_01 m_run_neutral m_walk_neutral
build Female_Adult_02    Adults/Female_Adult_02          f002 f_walk_injured f_run_injured f_walk_neutral
build Business_Male_01   Professions/Business_Male_01    m005 m_walk_neutral m_run_slow_01 m_run_neutral
build Male_Adult_02      Adults/Male_Adult_02            m003 m_walk_neutral m_run_neutral
build Business_Female_01 Professions/Business_Female_01  f014 f_walk_neutral f_run_neutral
