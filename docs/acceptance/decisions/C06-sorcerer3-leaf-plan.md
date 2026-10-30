# C06 Sorcerer 3: reviewed dependency and execution record

Status: leaf1 implemented and accepted by independent static review; broader regression tracked below. Leaf2 remains PROPOSED. Original full C06 acceptance stays OPEN.
Source entry: phb2024:class:sorcerer, PHB2024 Sorcerer Features PDF139 and subclass choice PDF140; source packages C06 release_v1 and Sorcerer release_v1 matched current acceptance-index checksum identities. Five C06 and four Sorcerer text/metadata members verified locally. Full spell definitions remain external.

## Dependency ruling
Original common contract lines78/82 requires dependency leaf IDs and says the first playable class slice needs necessary verified leaves. C06 plan lines131/139 keeps C01/K07 dependencies and selected feature/spell leaves, not whole unrelated catalogues. K07 parent is not execution unit. Therefore no blanket K07 waiver: this preparatory slot-schema leaf consumes existing C01 separation infrastructure, K07.proficiency_bonus_by_level, K07.long_rest_hp_exhaustion_duration and K07.hit_dice_short_and_long_rest regressions, plus existing C09 spell owner. Unrelated charm/fear effects are not consumed. Selected C19 subclass features and C05 higher-slot casting remain mandatory before declaring Sorcerer3 playable.

## Leaf 1: C06.sorcerer.slot_map_encoding
One behavior: preserve a validated spell-slot level map rather than truncating to level1.
Existing owners: spells.validate_saved_spell_fields(player), game.load_game, spell_scope.validate(state,character), character_progression.capacity.
Final minimal files: ai-dnd/spells.py; ai-dnd/game.py (writer, validator, loader); ai-dnd/api/serializers.py::_overlay_live_spell_fields; ai-dnd/api/tests/test_roadmap_c06_slot_maps.py.
Fixtures: literal Sorcerer3 table capacity {"1":4,"2":2}, counters below capacity; invalid key0/10/01/int, bool/negative counters, unsupported extra levels in actual low-level state.
Expected: syntactic map validation admits canonical numeric spell-level keys; actual class/level capacity and progression gates continue to reject unearned state. Legacy level1 maps remain unchanged. Load restores every validated key without aliasing. Do NOT raise MAX_SUPPORTED_LEVEL or claim end-to-end level3 roundtrip/playability in this leaf.
RED/PASS: verified guarded runner with api.tests.test_roadmap_c06_slot_maps; related C06, spells, spell_scope, sessions and save migration.
Save/level interaction: structural preparation only; full actual level3 load test remains required in leaf2. Any test-only capacity premise must be labeled as such, not production level3 acceptance.
Rollback: preserve pre-change snapshot; no personal-save migration or downgrade compatibility claim.
Reviewer/evidence: required before implementation; completion binds actual fresh run separately.

## Leaf 2: C06.sorcerer.level3_choice_and_state
Only after leaf1: actual preview/apply of level3, subclass selection recorded and validated from four sourced IDs, six prepared spell choices from eligible existing catalogue, capacities {"1":4,"2":2}, and save/load/rest/retry behavior. Missing subclass refuses atomically; XP-granted but unapplied level3 retains applied-level2 resources.
Do not implement arbitrary subclass feature effects inside progression. List exact C19/C05 effects pending and keep playability/wholeC06 OPEN until real selected features and higher-slot casting pass. Review this leaf's concrete cases before implementation.

## Remaining gate, not waived
Level3 subclass features and always-prepared spell grants, selected spell rules/upcasting, Font of Magic/Metamagic effects, other classes and levels4–20, HTTP/UI and fullfamily acceptance remain separate obligations. A level counter is not completion.

## Leaf1 review refinement: explicit entitlement boundary
The generic encoding validator must not authorize slot levels. Add game._validate_saved_multilevel_slots(player) after class identity validation: derive capacity from existing character_progression.slot_capacity or current class definition; if either saved map or capacity is multilevel, require exact allowed keys and counters within that capacity. Current MAX_SUPPORTED_LEVEL stays2, so unpatched real saves with extra level2 keys are rejected both with ordinary world slots and with worldspellstate absent. Preserve existing level1-only compatibility in this preparatory step; do not silently tighten unrelated legacy paths.

Tests must include these unpatched negative cases. A clearly labeled patched future-capacity fixture may exercise actual serializer/loader copying of {"1":4,"2":2} and spent counters, but is only encoding evidence, NOT proof of real level3 support. Actual production level3 transition and castability remain leaf2/subsequent gates.

Legacy player spell counters and world spellcasting state are separate existing representations. This leaf must preserve all validated keys and avoid silently granting slots by normalization. Mirror synchronization semantics require explicit coverage during actual transition/save/rest integration; no claim of complete rest/level3 behavior from a patched fixture.

## Final proposed executable leaf1 contract (supersedes prior guard sketch)
Signature: game._validate_saved_multilevel_slots(player: dict, saved_world: dict) -> None, called in game._validate_save_payload immediately after existing spell_scope.validate and character_progression.validate_saved. Any player map other than legacy {"1": n} requires real saved_world.spellcasting_v1 and a non-None character_progression.slot_capacity(player), exact capacity keys, and counters within capacity. Missing world/unsupported capacity/extra or missing keys/overcapacity reject before mutation. Preserve legacy {"1": n} behavior, and do not require player mirror counters to equal world counters. Generic spells.validate_saved_spell_fields remains syntax-only: nonempty string-keyed map, canonical levels1..9, exact integer counters0..20. Loader deep-copies the whole validated map.

Qualified tests in api.tests.test_roadmap_c06_slot_maps.SlotMapTests:
- test_slot_map_syntax_accepts_canonical_multiple_levels
- test_slot_map_syntax_rejects_noncanonical_keys_and_counts
- test_expanded_player_slots_rejected_with_low_level_world
- test_expanded_player_slots_rejected_without_world_state
- test_storage_roundtrip_with_explicit_future_capacity_fixture_only
- test_expanded_map_requires_exact_capacity_and_bounded_counts
- test_production_level_three_remains_blocked

Runnable RED command (from workspace root):
env -i PATH=/usr/bin:/bin HOME=/tmp/ai-dnd-takeover-harness/home TMPDIR=/tmp/ai-dnd-takeover-harness/tmp /workspace/scratch/a1b372df36be/ai-dnd-takeover/.venv/bin/python -I -B ai-dnd-takeover-work/run_guarded.py c06-slotmap-red api.tests.test_roadmap_c06_slot_maps
PASS repeats with label c06-slotmap-green and adds api.tests.test_roadmap_c06, api.tests.test_spells_v1, test_spells_v1, api.tests.test_spell_scope, test_save_migration and relevant approved session selectors (verify actual module names before run).

Source/right decision: user-provided PHB2024 reference packages under private development authorization. Current SOURCE_ACCEPTANCE_INDEX identifies bounded visual source acceptance; it is not a third-party redistribution license. Raw book text remains outside repository. Source values/page references only. Redistribution rights remain UNVERIFIED, no publish/push/merge authorized here. C06 checksum9b0598057487300723cafa286849c42937b96fe3496ca4cd0bc8aa8ec13e5128; Sorcerer checksumeccc86783af59355156f64db652c36b98cc9e204356151b433ecef30cea8cfd1.

Fixture boundary: real level2 Sorcerer with real chosen options, then explicitly patched capacity owner supplies a two-level slot map for storage-contract tests only. No patch is used in injection negatives or production level3-blocked tests. This is NOT an applied level3 proof. Independent review completion and B02evidence required. Leaf2's prepared count is SIX TOTAL, before separately granted always-prepared subclass spells, not six additions.

## Implementation ruling: existing write/projection callers
The related suite exposed two existing regressions after syntax widening: api.tests.test_spells_v1.SpellApiTests.test_fresh_v4_projection_uses_validated_saved_spell_fields and test_v3_projection_reads_live_spell_fields_only. Their unchanged expectations reject/hide unearned level9 slots. Therefore the same entitlement guard also runs in game._player_state_for_save and api.serializers._overlay_live_spell_fields (invalid legacy overlay omitted, preserving prior behavior). This is required integration of the existing validator's callers, not a new capability or weakened expectation. api/serializers.py is added to the bounded delta. Capacity remains owned by character_progression; MAX_SUPPORTED_LEVEL remains2.

Implementation evidence: c06-slotmap-red-confirmed7methods/5assertionfailures; intermediate capacity-red6failures proves injection negatives; final boundary-green89relatedexecutionsPASS. Post-implementation review pending; no claim of productionlevel3 readiness.
