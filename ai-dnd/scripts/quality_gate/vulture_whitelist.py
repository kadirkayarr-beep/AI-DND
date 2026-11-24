# ruff: noqa: F821
# Vulture baseline (Task 5). Generated once with:
#   vulture ai-dnd --min-confidence 80 --make-whitelist
# Run by the gate as:
#   vulture ai-dnd ai-dnd/scripts/quality_gate/vulture_whitelist.py --min-confidence 80
# Only entries that MATCH a finding may stay. Removing an entry is always allowed; ADDING one needs an approval-list row and Kadir.
# Grow-guard: CI step 'Vulture whitelist may only shrink' (ratchet check-names-shrink) fails when a name is new versus origin/main.
# Dead-code deletion is NOT done here (debt row, test and commit; that is 4c).
#
# --- Section A: game.py imports. Spot check 2026-11-24: only roll_initiative_npc has dynamic use (tests patch game.X); the other 4 are real unused imports. Owner = 4c. ---
adventure_director  # unused import (ai-dnd/game.py:28)
roll_initiative_npc  # unused import (ai-dnd/game.py:79)
_existing_local_tavern  # unused import (ai-dnd/game.py:275)
_filter_unsupported_lore_paragraphs  # unused import (ai-dnd/game.py:293)
