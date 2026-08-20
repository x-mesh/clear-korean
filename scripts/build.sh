#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

render() {
  local variant="$1"
  local tone="$2"
  local title="$3"
  local tone_title="$4"
  local target_dir="$project_dir/presets/$variant/$tone"
  local temp_file

  mkdir -p "$target_dir"
  temp_file="$(mktemp)"
  {
    printf '# Clear Korean: %s · %s\n\n' "$title" "$tone_title"
    cat "$project_dir/instructions/core.md"
    printf '\n'
    cat "$project_dir/instructions/tone-$tone.md"
    printf '\n'
    cat "$project_dir/instructions/$variant.md"
  } > "$temp_file"

  for filename in AGENTS.md CLAUDE.md INSTRUCTIONS.md; do
    cp "$temp_file" "$target_dir/$filename"
  done
  rm -f "$temp_file"
}

for variant in developer general; do
  if [[ "$variant" == developer ]]; then
    variant_title="개발자용"
  else
    variant_title="일반 사용자용"
  fi
  render "$variant" plain "$variant_title" "간결한 평서형"
  render "$variant" polite "$variant_title" "정중한 존댓말"
done

# 기존 공개 경로는 평서형 preset을 유지한다.
for variant in developer general; do
  mkdir -p "$project_dir/presets/$variant"
  for filename in AGENTS.md CLAUDE.md INSTRUCTIONS.md; do
    cp "$project_dir/presets/$variant/plain/$filename" "$project_dir/presets/$variant/$filename"
  done
done

mkdir -p "$project_dir/src/clear_korean/presets"
rm -f "$project_dir/src/clear_korean/presets/developer.md" "$project_dir/src/clear_korean/presets/general.md"
for variant in developer general; do
  for tone in plain polite; do
    cp "$project_dir/presets/$variant/$tone/INSTRUCTIONS.md" "$project_dir/src/clear_korean/presets/$variant-$tone.md"
  done
done
