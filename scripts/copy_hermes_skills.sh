#!/usr/bin/env bash
# Copy all Hermes skills into joyjoy's global (read-only) skills dir, flattened
# by leaf skill-dir name. Collisions get the parent category prefixed.
set -uo pipefail
src=/home/gourangasatapathy/.hermes/hermes-agent/skills
dst=/home/gourangasatapathy/joyjoy/skills/global
mkdir -p "$dst"
total=0; copied=0; coll=0
while IFS= read -r md; do
  total=$((total+1))
  d=$(dirname "$md")
  name=$(basename "$d")
  target="$dst/$name"
  if [ -e "$target" ]; then
    cat=$(basename "$(dirname "$d")")
    name="${cat}--${name}"
    target="$dst/$name"
    coll=$((coll+1))
    i=2
    while [ -e "$target" ]; do target="$dst/${name}-$i"; i=$((i+1)); done
  fi
  cp -r "$d" "$target" && copied=$((copied+1))
done < <(find "$src" -name SKILL.md)
echo "RESULT total_src=$total copied=$copied collisions=$coll"
echo "GLOBAL_SKILLS_NOW=$(find "$dst" -maxdepth 2 -name SKILL.md | wc -l)"
