#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT

mkdir -p "$temp_dir/instructions" "$temp_dir/scripts" "$temp_dir/presets/developer" "$temp_dir/presets/general" "$temp_dir/src/clear_korean/presets"
cp -R "$project_dir/instructions/." "$temp_dir/instructions/"
cp "$project_dir/scripts/build.sh" "$temp_dir/scripts/build.sh"
chmod +x "$temp_dir/scripts/build.sh"
"$temp_dir/scripts/build.sh"

for variant in developer general; do
  for tone in plain polite; do
    for filename in AGENTS.md CLAUDE.md INSTRUCTIONS.md; do
      diff -u "$temp_dir/presets/$variant/$tone/$filename" "$project_dir/presets/$variant/$tone/$filename"
    done
  done
  for filename in AGENTS.md CLAUDE.md INSTRUCTIONS.md; do
    diff -u "$temp_dir/presets/$variant/$filename" "$project_dir/presets/$variant/$filename"
  done

  line_count="$(wc -l < "$project_dir/presets/$variant/AGENTS.md")"
  if (( line_count > 200 )); then
    echo "$variant preset exceeds 200 lines: $line_count" >&2
    exit 1
  fi

  if rg -n '^---$|keep-coding-instructions|force-for-plugin' "$project_dir/presets/$variant"; then
    echo "$variant preset contains host-specific frontmatter" >&2
    exit 1
  fi
done

for variant in developer general; do
  for tone in plain polite; do
    diff -u "$project_dir/presets/$variant/$tone/INSTRUCTIONS.md" "$project_dir/src/clear_korean/presets/$variant-$tone.md"
  done
done

test -s "$project_dir/tests/cases.tsv"
test -s "$project_dir/tests/README.md"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$project_dir/src" python3 -m unittest discover -s "$project_dir/tests/unit"
echo "All checks passed."
