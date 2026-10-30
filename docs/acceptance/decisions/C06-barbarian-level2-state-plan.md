# C06 Barbarian 1→2 noncaster progression state

Status: PROPOSED for independent preimplementation review. No product or test changes authorized by this document itself. Browser acceptance of the existing Sorcerer UI remains separate and OPEN.

## Single behavior and acceptance boundary

Advance an existing, actually configured single-class Barbarian from applied level 1 to applied level 2 through the existing pure preview / atomic apply / canonical save and fresh restore path. Both direct apply and XP-first pending advancement are exercised. No spells or spellcasting state are manufactured. This is a generic noncaster progression proof, not a playable or complete Barbarian, C10, C06, or whole-release claim.

Do not add Barbarian higher-level creation, HTTP/catalog/UI choices, level 3, subclasses, feature resolution, multiclass, or unrelated K07 work. Preserve Sorcerer levels 1–3 and the accepted starting-XP repair. Existing level-1 creation is fixture setup, not newly source-certified equipment/feature completion.

## Source binding and dependencies

Original approved plan `plans/05-Tam_PHB_2024.md`, C06: C01/K07 dependencies; selected class-table leaves may establish bounded progression without completing all class/spell catalogs. C10 owns Barbarian feature effects. No parallel state, resource, or receipt owner.

Verified external source root: `/workspace/scratch/a1b372df36be/phb-source-recovered-20261029/`; receipt `TRANSFER_VERIFICATION.json`. Raw source remains outside this repository.

- Barbarian release_v1 checksum identity: `9246e9535518317315bbe43b6e29144c34ec9dd4200257385520fa9114a88f18`. Six registered text/metadata/correction members byte-verified against it; source acceptance index identifies this exact release. Not a new visual audit or complete 37-member transfer.
- `barbarian.md` / `features_table.csv`, PDF51 / printed52: levels 1 and 2 PB +2, Rages 2, Rage damage +2, weapon masteries 2. Level 2 features: Danger Sense and Reckless Attack. Neither adds a build-time selection; Reckless Attack's attack-time decision is not a progression choice.
- Barbarian PDF50 / printed51: d12 per class level. Existing creation AC formula already has a Barbarian Unarmored Defense branch; preserve it, do not claim its full lifecycle freshly accepted.
- C06 release_v1 checksum identity: `9b0598057487300723cafa286849c42937b96fe3496ca4cd0bc8aa8ec13e5128`; `advancement.md` SHA256 `3609211d94a1690f1aeab1f6c2c9e9677af49f9e238b796b83a9be67ceab1410`. PDF40 / printed41: 300 XP reaches level 2. PDF41 / printed42: one additional Hit Die, fixed HP gain max(1, 7 + Constitution modifier), before separately owned species/feat additions.
- Consume existing K07 proficiency, HP/Hit Dice/rest leaves and C01 honest capability separation. The existing C09/spell validation boundary is a preservation dependency, not a requirement to implement new spell leaves. Full K07, C07, and class catalog closure are not prerequisites for this state-only proof.

## Minimal owner changes proposed

1. Add only source values/provenance for Barbarian levels 1–2 in `content/rules/phb2024/classes/barbarian.json`; no raw book prose and no fabricated caster columns. State support is explicit by class: Sorcerer 3, Barbarian 2. Table existence alone must not advertise arbitrary levels or new higher-level creation. Keep `MAX_SUPPORTED_LEVEL` compatibility for existing Sorcerer tests/catalog while checking the per-class ceiling in preview and saved-state validation.
2. `ai-dnd/character_progression.py` remains the progression owner. `capacity` / `slot_capacity` must return None for noncaster Barbarian, not zero-valued fake Sorcerer resources. Preview returns `choices_required: {}` and `capacity: None` for this leaf, with source feature names and explicit pending effects. Add a noncaster branch in `_check_choices` and `apply_level_choices` accepting exactly `{}`; reject foreign spell, Metamagic, subclass and unknown choices. Preserve pure preview, current-preview comparison, stale/replay rejection, trusted snapshot behavior, HP and proficiency updates.
3. Noncaster apply must not index or insert `world_state['spellcasting_v1']`, set caster mirrors, or mutate unrelated world/character data. Validate the resulting character against the actual existing world, including absence of spellcasting state, before committing. Do not bypass `spell_scope.validate`; it already rejects noncaster spell access. Do not suppress malformed-state exceptions into successful mutation.
4. In `validate_saved`, branch by explicit class capability after common level/type checks. Barbarian applied level 1 or 2 does not require `metamagic_options`, prepared spells or spell state. Reject positive/foreign Metamagic and any subclass selection; require no noncaster spellcasting state. Applied level 3+ rejects, even if numerical character level is XP-ahead. Existing unsupported classes stay fail-closed.
5. Protect the creation boundary explicitly: adding a table must not silently enable `create_at_level(... Barbarian, level=2)`. Retain higher-level creation restricted to the currently accepted Sorcerer path until a separate creation leaf; level-1 setup remains unchanged. HTTP/catalog already restrict higher starts to Sorcerer and must stay unchanged.

## Persistence, HP and Hit Dice implications

- Existing `api/character_creation.py::configure_character` plus `spell_scope.initialize` creates the real noncaster fixture and removes `spellcasting_v1`. Preserve existing legacy spell-field encoding rather than introducing a new empty slot-map representation: `game._validate_saved_multilevel_slots` treats non-legacy maps as requiring real spell entitlement.
- `game._player_state_for_save`, `_validate_save_payload`, `load_game`, and `api.persistence.campaign_validation::{serialize_campaign_payload,restore_campaign_session}` already carry `progression_level` and Hit Dice; retain these owners. Real roundtrip is required; a dict-only encoding test is insufficient. Ordinary saved level/XP/PB validation remains intact.
- `xp.hit_point_gain` already supplies fixed Barbarian 7 + Constitution, minimum 1, plus existing species/feat effects. Direct apply pays one increment; XP-first apply pays none. Do not award XP or create reward receipts inside apply. Direct state application may be ahead of earned XP under the existing C06 contract; it is not higher-level creation.
- `hit_dice.total` uses applied progression level and `die_size` uses existing class d12. A pending XP-only level retains one die; applying level 2 exposes two dice automatically. Preserve spent count; one spent die stays spent, no extra restoration, RNG draw or new resource owner. Save validation bounds spent dice by applied level. Short/long rest ownership stays unchanged. Test normal state plus a spent-die fixture and existing rest regressions; no rest code rewrite planned.

## Pending effects, not silently completed

Return explicit C10/C04 obligations for Rage activation/counters/rest renewal/damage/resistance/duration, mastery selection/effects, Danger Sense and Reckless Attack. The table's unchanged Rage/mastery values are metadata, not newly tracked resources. Preserve existing Unarmored Defense computation but do not promote it to fully accepted lifecycle coverage. Existing equipment mismatch is a separate open creation/content issue and must not be corrected opportunistically here.

## Test-first contract

Proposed `ai-dnd/api/tests/test_roadmap_c06_barbarian.py`, real configured Human Barbarian fixture with valid existing choices and no bonus spellcasting origin:

1. Source literal oracle: class ceiling 2; level 2 PB2, Danger Sense/Reckless Attack, unchanged Rage/mastery metadata. Pure preview, empty choices, no caster capacity.
2. Actual 1→2 apply `{}` preserves equipment, skills, AC, conditions and unrelated world state; produces no spellcasting state, usable spell slots, Metamagic or subclass grant. Preserve the existing noncaster legacy mirror `spell_slots_remaining: {"1": 0}` rather than removing or replacing it. Pending effects are explicit.
3. Direct versus 300-XP-first paths pay HP exactly once. Duplicate/stale/tampered preview, non-dict/unknown/caster choices and level 3 reject without mutation.
4. Hit Dice total 1→2, d12 unchanged, spent count preserved; XP pending does not unlock the new die. Canonical serialize → fresh restore preserves progression, absence of spell state, and spent dice.
5. Saved injection negatives: applied3, foreign subclass/Metamagic, spellcasting state, invalid applied/character level types, spent dice above applied total. Check rejection before target-session mutation through actual restore.
6. No accidental Barbarian higher-level creation or HTTP/catalog advertisement; accepted Sorcerer creation1/2/3 and XP0/300/900 unchanged.

Run assertion RED then minimal GREEN under the external reviewed guard, fresh synthetic environment, unique evidence labels. Exact module command: external `.venv/bin/python -I -B .../run_guarded.py <label> api.tests.test_roadmap_c06_barbarian`. Related regressions: C06 core/level3/starting-XP/slot maps/HTTP/catalog, XP, Hit Dice/rest, spell scope and canonical save/restore. Confirm actual module/selectors before execution. No failed import/harness error counts as RED. Independent postimplementation review and bounded evidence required.

## Blockers and rollback

No missing source fact blocks this narrowly defined level2 state leaf. First obtain independent approval of this exact owner/API boundary, especially the noncaster preview capacity and creation gate. Full feature behavior and external weapon mastery rules remain unaccepted/externally dependent; they are explicitly excluded, not assumed PASS.

Rollback is the bounded file delta using a preserved prechange candidate snapshot. Older code rejects applied Barbarian2 saves because it lacks the table; no downgrade compatibility or personal-save migration claim. No commit, push, merge, deployment, authentication/access change or browser acceptance is part of this leaf.
