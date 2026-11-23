# ruff: noqa: F821
# Vulture baseline (Task 5). Generated once with:
#   vulture ai-dnd --min-confidence 80 --make-whitelist
# Run by the gate as:
#   vulture ai-dnd ai-dnd/scripts/quality_gate/vulture_whitelist.py --min-confidence 80
# Only entries that MATCH a finding may stay. Removing an entry is always allowed; ADDING one needs an approval-list row and Kadir.
# Dead-code deletion is NOT done here (debt row, test and commit; that is 4c).
#
# --- Section A: dynamic use (game.X re-exports; tests patch them as game.X) ---
adventure_director  # unused import (ai-dnd/game.py:28)
roll_initiative_npc  # unused import (ai-dnd/game.py:79)
_SHOP_CREATION_ACTION_PATTERN  # unused import (ai-dnd/game.py:175)
_existing_local_tavern  # unused import (ai-dnd/game.py:275)
_filter_unsupported_lore_paragraphs  # unused import (ai-dnd/game.py:293)
#
# --- Section B: frozen real findings (not deleted here; owner = 4c) ---
expected_failure  # unused variable (ai-dnd/acceptance_test.py:104)
generate_random_2024_character  # unused import (ai-dnd/api/character_creation.py:10)
tz  # unused variable (ai-dnd/api/tests/test_http_acceptance_evidence.py:385)
exc_type  # unused variable (ai-dnd/api/tests/test_persistence_idempotency.py:3762)
exc_value  # unused variable (ai-dnd/api/tests/test_persistence_idempotency.py:3762)
resume_campaign_id  # unused variable (ai-dnd/api/tests/test_roadmap_r08.py:49)
fmt  # unused variable (ai-dnd/reports/wave3-local-live-20261006/local_dev_proxy.py:45)
# Not whitelistable (no name): unreachable code after 'try' (ai-dnd/class_progression/barbarian.py:206)
