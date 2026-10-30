# C06 Barbarian create-at-2 — bounded core orchestration

Status: PROPOSED for independent preimplementation review. This document changes no product behavior and is not execution authorization by itself.

## Behavior and boundary

Permit the existing direct core call `create_at_level(session, barbarian_spec, 2, {'2': {}})`. It must configure the actual existing level-1 character, reuse accepted Barbarian 1→2 preview/apply, initialize canonical starting XP300 through the accepted XP fix, and return a character that survives canonical serialization and fresh restore.

HTTP requests, published schema, catalog and UI higher starts remain **Sorcerer-only**. Barbarian3+, other newly unsupported classes, feature mechanics, equipment corrections and browser acceptance are excluded. This is numeric creation/state orchestration, not source-complete Barbarian creation or class playability. C06 and C10 remain OPEN.

Original approved `plans/05-Tam_PHB_2024.md` C06 owns preview/apply/create and source-backed class-table expansion; this leaf consumes selected existing dependencies, not the whole class or C07 catalog. No formal “Stage A/B” names are attributed to that original document.

## Verified source and owner dependencies

- External `/workspace/scratch/a1b372df36be/phb-source-recovered-20261029/TRANSFER_VERIFICATION.json` binds the received source members. Barbarian release_v1 checksum `9246e9535518317315bbe43b6e29144c34ec9dd4200257385520fa9114a88f18`: PDF50/51 gives d12, level2 PB2, Danger Sense/Reckless Attack, unchanged Rage/mastery columns. No new build-time level2 feature choice.
- C06 release_v1 checksum `9b0598057487300723cafa286849c42937b96fe3496ca4cd0bc8aa8ec13e5128`: advancement PDF40/42 requires starting level2 XP300; PDF41 gives one additional Hit Die and fixed HP max(1, 7 + Constitution modifier), before existing species/feat additions. Raw source stays outside repository.
- Existing `api.character_creation.configure_character` owns actual level1 configuration. It clears noncaster cantrips/spells and invokes `spell_scope.initialize`, which removes `spellcasting_v1`.
- Existing `character_progression.create_at_level` owns capture/restore, stale progression/Metamagic/subclass/Hit Dice clearing, step application and starting XP initialization. Existing `preview_level_up`, `apply_level_choices`, `validate_saved` own the accepted Barbarian2 state. Existing XP, Hit Dice, persistence and spell validation owners remain unchanged.

## Exact proposed product delta

Only `ai-dnd/character_progression.py::create_at_level` is expected to change.

1. Replace the current Sorcerer-only direct-core higher-start gate with an explicit bounded creation capability: Sorcerer through3, Barbarian through2. Keep the applied-state support ceiling as an additional guard; do not use global MAX3 alone to authorize Barbarian3. Unsupported class/level rejects before the runtime snapshot or configuration mutation.
2. For the new Barbarian2 path require an actual dict with exactly the step key `'2'`, whose value is an actual empty dict. Reject absent/null, list, integer/zero-padded/extra keys, extra steps and all spell/Metamagic/subclass/unknown choices before configuration. This exactness is specific to the new capability; do not opportunistically alter accepted Sorcerer request semantics.
3. Reuse the unchanged snapshot/try/except path: clear stale class progression metadata, configure at1, call existing preview/apply once, set `progression_level`, and perform the already accepted `dict(xp.LEVEL_THRESHOLDS)[level]` assignment. Never call `apply_xp` for starting XP, mint a reward receipt, roll for HP, restore spent resources through a second owner or fabricate spellcasting state.
4. Preserve existing noncaster legacy `spell_slots_remaining: {'1': 0}` and no world spell-state key, including no key with None. Pending Rage/mastery/Danger Sense/Reckless Attack obligations remain available through the existing pending-effects function; no mechanically complete feature flag is set.

Any need to change creation, spell, Hit Dice, persistence, HTTP, schema, catalog or UI owners must be reported before widening this delta.

## Test-first implementation contract

Proposed new `ai-dnd/api/tests/test_roadmap_c06_barbarian_creation.py`, importing real fixtures without importing TestCase classes. Use literal source values, not expected results calculated from the function under test.

1. **Actual core creation:** default1 stays XP0; explicit2 with exact `{'2': {}}` reaches `(level, applied, XP, PB) = (2, 2, 300, 2)`. Fixture Constitution14 yields HP23 (initial14 +9), two d12 Hit Dice, no spent dice. Verify equipment/skills/AC are preserved relative to the same real level1 fixture, without claiming its package is source-complete.
2. **Canonical roundtrip:** serialize actual created2, restore into a fresh session, assert level/applied/XP/HP/Hit Dice, empty caster selections, zero legacy slot mirror, no world spell state and explicit pending-effects projection. This is not a patched future-capability fixture.
3. **Exact input boundaries:** missing/null/wrong-type choices, noncanonical step keys, extra step1/3, extra choice fields and Barbarian3–20 reject before `configure_character` is invoked; full snapshot, container identity and RNG unchanged. Invalid level types/range retain existing guards.
4. **Populated-session recreation:** start with actual Sorcerer3, chosen Metamagic/subclass, nonzero spent Hit Dice and spell state. Successful Barbarian2 creation removes old caster/class-specific state, resets spent Hit Dice under the existing creation contract, has HP23/XP300 and no new reward event. Existing unrelated world/reward history must not be opportunistically erased; compare event history before/after rather than requiring a populated world's history to become empty.
5. **Late failure rollback:** wrap the real apply call so it first performs the level2 mutation then raises a synthetic failure. Creation must restore complete preexisting character/world/messages/narration/RNG snapshot and top-level container identities, including old XP and caster state. Label this as fault-injection atomicity evidence, not normal rule behavior. Also verify ordinary invalid-level2-choice rejection without a fault hook.
6. **No second payment:** newly created2 starts with XP300 and no award receipt. Earn599 → XP899/level2/unchanged HP; earn1 → XP900/rawlevel3/one HP increment. Applied level remains2, Hit Dice total remains2 and Barbarian3 choices remain blocked. Replaying either reward changes nothing. No acceptance of Barbarian3 is implied by XP-ahead raw level.
7. **Surface remains closed:** real HTTP higher-start Barbarian2 request rejects before store/session registration; published schema/catalog and Sorcerer HTTP1–3 regression remain unchanged. Direct-core acceptance must not silently expand user-facing support.

Existing `test_roadmap_c06_barbarian.py::test_higher_start_creation_and_http_schema_stay_blocked` must retain an actual unsupported direct counterexample by changing that one direct target from2 to3; retain its Barbarian2 schema rejection and add the new direct2 positive in the new module. Do not merely delete the negative or weaken ceilings. Rename the old test to describe its remaining boundary if appropriate.

Run genuine assertion RED before product edits using the external frozen `.venv/bin/python -I -B` and reviewed `run_guarded.py`, fresh synthetic environment and unique labels. Existing guard permissions stay unchanged. GREEN then related Barbarian state, C06 starting-XP/core/level3/HTTP/catalog/slots, XP/receipt, Hit Dice and canonical persistence regressions. Independent implementation review binds actual final code and evidence; no earlier overlapping test counts are summed as unique methods.

## Source limitations, rollback and stopping condition

No missing source fact blocks this numeric core leaf. Existing Barbarian equipment differs from PHB source; Rage/mastery and new level2 effects remain pending. Do not fix those incidentally or call the created character fully source-complete/playable. General higher-level equipment guidance does not license inventing extra items.

Capture the current accepted candidate before product change. Rollback restores only this leaf's bounded delta; previous accepted Barbarian2 state reader can read the resulting same-shape save, but actual downgrade compatibility must not be promised without testing. No personal-save migration, commit/push/merge/deployment, access/authentication change or browser claim. Stop after narrow GREEN, regression and independent review; do not proceed to Barbarian HTTP/UI without a separate scoped plan.
