# C06.sorcerer.level3_choice_and_state — proposed implementation leaf

Scope: actual unpatched progression infrastructure 2→3 (and create-at-level3), not fully playable Sorcerer3 or C19 subclass-effect acceptance. C06 remains OPEN.

Source: verified Sorcerer release_v1 table PDF139: level3 PB2, four cantrips, SIX TOTAL normally prepared spells, slots {"1":4,"2":2}, SorceryPoints3, subclass choice. PDF140 lists four subclasses; manifest already provides stable source IDs. Subclass feature effects and always-prepared grants remain separate C19 leaves, explicitly pending. Full selected MagicMissile slot2 casting is subsequent C05 dependency using official2024BasicRules; no fullspellcatalogue requirement.

## Dependencies / owners
C01 reviewed leaf-record gate; accepted C06.sorcerer.slot_map_encoding; existingK07 PB/HP/rest/HitDice/sourceoracles; existingC09 spellstate owner and C06 level1→2. UnrelatedK07 conditions not required. Actual class effects, selectedupcast, optionalreplacement choices, UI remain OPEN.
Files: character_progression.py; content/rules/phb2024/classes/sorcerer.json; game.py save/load subclass_id; api/tests/test_roadmap_c06_level3.py; existing C06 tests only to move explicitly unsupported upper bound from3 to4 and preserve unearned/missing-choice rejection.

## Contract
- MAX_SUPPORTED_LEVEL becomes3 only after actual state tests pass; levels4+ stillblocked.
- Source table gets four stable subclass IDs/names/sourcepages and level3 feature-name obligations, no raw book text or invented effects.
- preview_level_up(session,3) pure: requires two new normally prepared spells whenfrom2, one subclass_id, capacities4/2, preserves priorcantrips/metamagic; pendingeffects explicitly include all stillunimplemented FontofMagic/Metamagic/subclass effects and optionalreplacement-choice limits.
- _check_choices: exact valid subclass_id mandatory whencrossing3; invalid/missing/extrachoices reject with no mutation. Existing eligible level1 spells may fill six-total preparation list (classsource permits any combination within accessible levels); unsupportedlevel2 definitions are not fabricated.
- apply_level_choices: copy existingcharacter/spellstate only; slotdelta preserves spentslots, adds secondlevel capacity; store subclass_id once. Duplicate/stalepreview rejects. Existing HP already awardedbyXP must not be paid twice.
- validate_saved: explicit appliedlevel exactint in supportedrange and <=characterlevel; level3 requires valid subclass_id and sixnormallyprepared spells plus priorvalidmetamagic choices. No subclass_id below3. Optionallegacyabsence remainscompatible. Rejectedload leaves runtimeunchanged.
- game._player_state_for_save and load_game: preserve optional subclass_id; restore-or-pop so priorcharacter subclass cannot leak. No UI/HTTP feature claim.
- create_at_level: reuse creation+apply in one existing trusted runtime snapshot/rollback boundary. Validate levelchoices presence before mutation, clear progression-owned priorfields before newcreation; semanticfailure atlevel3 restores originalcharacter/world/RNG/messages, not a halfcreatedlevel2. Existingconfigure_character remains its owner; no new worldstate authority.

## Qualified test matrix
api.tests.test_roadmap_c06_level3.LevelThreeTests:
- test_preview_level_three_is_pure_and_requires_subclass
- test_apply_preserves_spent_slots_choices_and_opens_second_bucket
- test_missing_invalid_or_replayed_choices_never_mutate
- test_xp_pending_level_three_keeps_level_two_until_choices_apply
- test_real_level_three_roundtrip_and_rest_keep_both_slot_levels
- test_missing_invalid_or_unearned_subclass_save_is_rejected
- test_old_save_clears_stale_subclass
- test_create_at_three_uses_same_choices_and_rolls_back_invalid_final_choice
- test_no_level_four_or_full_subclass_effect_support_is_claimed
Expected literal tablevalues independent of implementation. Actuallevel3 tests are UNPATCHED; no futurecapacitymock acceptance.

RED/PASS from workspace root:
env -i PATH=/usr/bin:/bin HOME=/tmp/ai-dnd-takeover-harness/home TMPDIR=/tmp/ai-dnd-takeover-harness/tmp /workspace/scratch/a1b372df36be/ai-dnd-takeover/.venv/bin/python -I -B ai-dnd-takeover-work/run_guarded.py c06-level3-red api.tests.test_roadmap_c06_level3
PASS uses unique greenlabel and adds C06 existing+slotmap, spells/save/migration/rest/XP regressions and approvedsession suite. Independent review and B02binding required.

## Boundaries / rollback
Rights: user-provided private reference, source acceptance index verified; redistribution license UNVERIFIED, no rawbook commit or publication. Keep prechange snapshots. PreviousMAX2 reader rejects new appliedlevel3 saves; rollback requires matching oldsnapshot, not silentdowngrade. No personal-save migration, push, merge or deploy.
The selected subclass feature records are NOT marked supported merely because an ID is stored. All four choices identify pending C19 obligations. First playable class gate still waits selected actualfeature effects and castability. Six normallyprepared spells excludes futurealways-prepared subclassgrants.

## Pre-TDD review refinements
- Source pending list also includes still-unimplemented Innate Sorcery (level1), not only newly crossed features. Advancing2→3 must not hide prior missing effects.
- test_all_four_subclass_ids_apply_and_roundtrip uses literal existing manifest IDs: phb2024:subclass:sorcerer:aberrant-sorcery, :clockwork-sorcery, :draconic-sorcery, :wild-magic-sorcery. Save negatives include wrong-class ID, ID without appliedprogression, and IDbelow3.
- create rollback starts from a populated/reused session and checks character/world/RNG/messages/recent_dm_narrations/_xp_level_up and top-level container identity after a genuinely late invalidlevel3choice. Successful recreationat1 clears old progression/metamagic/subclass fields and resets ownedHitDice state, not oldcharacter leftovers. The existing trusted snapshot owner is reused; no fabricated save/load rollback.
- Subclass effects and always-prepared grants remain visible pending obligations even when corechoice/state storage succeeds. This leaf must not close C19 or first-playable-class acceptance.

## HP partial-XP ruling (required before implementation)
Support an explicit applied1→target3 jump with all intervening choices, but pay only HP levels not already granted by XP. Preview gain = fixed class/CON gain times max(0,target_level - authoritative character.level), after validating character.level as exactint1..20. The existing already_applied flag remains true when character.level>=target. This prevents paying level2 twice when XP already raised the character to2 but choices are still applied1.
Add qualified test test_partial_xp_jump_to_three_pays_only_one_remaining_hp_gain: sourcefixture CON14, Sorcerer fixedgain4+2=6; XP300 raisesrawlevel2 andpays6; preview1→3 withallchoices must propose6, apply adds6only, replayadds0. Othercase fullyXP900 rawlevel3/applied1 pays0HP while applyingchoices. This is bounded jump support, not a blanket level20 implementation.

## Required catalogue-membership dependency discovered before TDD
Current Sorcerer level1 selection catalogue contains only six names, one being legacy Chaos Bolt (not in verified PHB2024 Sorcerer list). Do NOT force that legacy entry to satisfy six-total PHBchoices, and do NOT delete existinglegacy support. Add only Detect Magic's Sorcerer level1 membership, verified explicitly in Sorcerer PDF138 recommendation and PDF142 level1list (printed label UNKNOWN). Existing source entry phb2024:spell:detect-magic is inventoried. This adds selection metadata in api/dnd_2024_rules.py, not its resolver or a complete C05 spell claim.
Tests use explicit PHB choices: initialMagicMissile/Shield; level2BurningHands/ChromaticOrb; level3DisguiseSelf/DetectMagic. Add test_level_three_has_six_source_list_choices_without_forcing_legacy_chaos_bolt. Existing ChaosBolt entry stays separatelegacy compatibility. No fullspellcatalogue or DetectMagic effects accepted by this membership change.
