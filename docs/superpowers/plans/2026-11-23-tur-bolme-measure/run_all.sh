#!/bin/bash
# Re-run the turn-split inventory on any git ref (read-only; nothing in ai-dnd/ is imported).
#   bash run_all.sh <ref> <tag> [<sub line> ...]
# e.g. Task 0:  bash run_all.sh origin/main base 2824 2958 2984 1664 2541
# Writes <target>_<tag>.txt next to this script.  Sub lines are start lines of compound
# statements inside _run_player_turn_internal whose body is measured one level deeper;
# they shift when turn.py changes, so take them from the new run_internal_<tag>.txt first.
set -euo pipefail
ref=$1; tag=$2; shift 2
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
git show "$ref:ai-dnd/game_parts/turn.py" > "$tmp/turn.py"
git show "$ref:ai-dnd/game.py" > "$tmp/game.py"
git show "$ref:ai-dnd/game_parts/narration_safety.py" > "$tmp/narration_safety.py"
cd "$here"
python -I block_io.py "$tmp/turn.py" _run_player_turn_internal --label "turn.py@$tag" > "run_internal_$tag.txt"
python -I block_io.py "$tmp/turn.py" _run_player_turn_internal finish_turn --label "turn.py@$tag" > "finish_turn_$tag.txt"
python -I block_io.py "$tmp/turn.py" _dispatch_player_turn --label "turn.py@$tag" > "dispatch_$tag.txt"
python -I block_io.py "$tmp/game.py" _narrate_resolved_turn --label "game.py@$tag" > "narrate_resolved_$tag.txt" 2>/dev/null \
  || echo "_narrate_resolved_turn not in game.py at $ref (moved?)"
python -I block_io.py "$tmp/narration_safety.py" _narration_safety_decision --label "narration_safety.py@$tag" > "safety_decision_$tag.txt"
for line in "$@"; do
  python -I block_io.py "$tmp/turn.py" _run_player_turn_internal --sub "$line" --label "turn.py@$tag" > "run_internal_${tag}_sub$line.txt"
done
grep -H '^CUTSUM' ./*_"$tag"*.txt
rm -rf "$tmp"
