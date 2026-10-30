# C06.sorcerer.starting_level_http — bounded review draft

Status: proposed adapter leaf, not implemented or tested here. Read-only inspection only; no product files edited. C06 and full Sorcerer3 playability remain OPEN. Original authority: `ai-dnd-takeover-plan/plans/05-Tam_PHB_2024.md`, C06 lines 129–145; existing accepted core choice/state leaf and selected Magic Missile slot2 dependency are prerequisites, not reimplemented here.

## Result and boundary

Use existing `POST /api/game/campaigns` and its `/api/campaigns` alias. Adapt custom creation to existing `character_progression.create_at_level`; no new endpoint, live level-up HTTP operation, UI implementation, catalog expansion, broad K07, auth/access change, data migration, or deployment. Other classes retain their existing level1 creation. Higher creation levels are explicitly Sorcerer-only and bounded to 2–3.

## Exact proposed request contract

Add only these fields to existing `CharacterCreateInput`:

- `starting_level`: strict integer, default `1`, minimum1, maximum3. Reject bool, float, numeric string and null. Omission preserves level1.
- `level_choices`: optional nullable typed object. Only external keys `"2"` and `"3"`; nested objects forbid additional fields.
- Key `"2"`: `SorcererLevel2Choices`, required `prepared_spells: list[str]` of length2 and `metamagic: list[str]` of length2. Strings strict; membership and duplicate checks remain core-owned.
- Key `"3"`: `SorcererLevel3Choices`, required `prepared_spells: list[str]` of length2 and `subclass_id: str`. No metamagic field here. Strings strict; membership remains core-owned.
- Use named Pydantic fields `level_2`, `level_3` aliased to `"2"`, `"3"`; set nested validate_by_name=False; only external numeric aliases are accepted. Reject explicitly null level entries. Never expose an unconstrained `dict[str, Any]` as this new input.
- Custom level1: choices absent/null or empty object only. Custom level2: exact keyset `{"2"}`. Custom level3: exact keyset `{"2","3"}`. Reject missing, surplus, future, `"02"`, `"1"`, or unexpected per-level fields. Reject any starting_level>1 if class is not exactly `Sorcerer`, independent of future table additions.
- Random mode remains the existing random level1 path: starting_level omitted or1 is accepted; any non-null level_choices or starting_level2/3 is rejected. Existing custom-field prohibition remains unchanged.

Example additions to an otherwise valid existing Sorcerer custom request:

```json
{
  "starting_level": 3,
  "level_choices": {
    "2": {
      "prepared_spells": ["Burning Hands", "Chromatic Orb"],
      "metamagic": ["Quickened Spell", "Twinned Spell"]
    },
    "3": {
      "prepared_spells": ["Disguise Self", "Detect Magic"],
      "subclass_id": "phb2024:subclass:sorcerer:aberrant-sorcery"
    }
  }
}
```

Top-level `spells` still means the two level1 initial selections (fixture: Magic Missile, Shield); per-level prepared_spells are additions, NOT final full lists. Four starting cantrips remain unchanged. Current core permits these additions only from its existing Sorcerer level1 selection catalog, not arbitrary level2 spell definitions. No new default choices or fabricated spell effects.

## Minimal owner wiring

1. `ai-dnd/api/schemas.py` (`CharacterCreateInput`, currently around512): add typed models/fields and structural/mode/keyset validation. Keep semantic catalog membership and existing-spell exclusion in `character_progression._check_choices`.
2. `ai-dnd/api/session_manager.py` (`create_campaign`, around156): revalidate supplied character mapping through the shared schema so direct manager callers cannot silently bypass new fields. Normalize the base creation spec with internal `character_class` name; remove `starting_level` and `level_choices`. Normalize only nested choices with `model_dump(by_alias=True, exclude_none=True)` to get exact core keys `"2"`, `"3"`. Do not use whole-character `by_alias=True` because core expects `character_class`, not `class`.
   - For omitted character, random mode, and custom level1, keep current factory/configure_character behavior; remove new adapter-only fields before configure_character. This preserves old default/random behavior exactly.
   - For custom level2/3, remove `mode` from the copied base spec, then call `create_at_level(session, spec, starting_level, choices)`. Core itself supplies mode="custom"; leaving mode would produce duplicate keyword failure.
   - Convert validation/domain errors only around this creation adapter to existing `CharacterCreationError`; do not broadly catch errors from the rest of campaign creation. Schema-level HTTP errors remain standard422; valid-shaped but semantically rejected choices map to existing `422 {detail:{code:"invalid_character",message:...}}`.
   - Finish all creation/progression before journal/opening/store/registry publication. Do not introduce a second transaction, new manager, or alternate save path.
3. `ai-dnd/api/main.py` (`create_campaign`, around818): retain existing CharacterCreationError mapping, but forward request.character.model_dump(by_alias=True, exclude_none=True) so absent nested choice steps are not transformed into explicitly null invalid steps. Manager schema revalidation then normalizes base character_class by internal names and nested choice keys by aliases.
4. `ai-dnd/api/serializers.py` (`_PLAYER_FIELDS`, around30): add optional projection of `progression_level`, `metamagic`, `subclass_id` from canonical saved player fields. No client-derived progression or resource values. Keep spell slot projection from world.spellcasting_v1 unchanged.
5. `lib/api-spec/openapi.yaml`: mirror new typed request components/fields and optional GameCharacter projection fields. Explicit descriptions: metamagic/subclass fields are selected IDs/options, not implemented effects. Both canonical and alias requests use the same contract.
6. Regenerate, never hand-edit generated outputs: `pnpm --filter @workspace/api-spec run codegen`. Expected changes in `lib/api-client-react/src/generated/api.schemas.ts`, generated `api.ts` as needed, and `lib/api-zod/src/generated/api.ts` plus generated type files. Existing Orval config uses clean:true, so serialize this operation after current accepted leaf edits and inspect all generated diffs.

No expected product changes to `game.py`, campaign store/serializer, core progression, source tables, combat, XP or rests: these existing owners already save, restore, validate and roll back the required state. If a new failing test proves otherwise, return a precise scope revision rather than silently enlarging this leaf.

## Existing rollback / saved-state authority

- `character_progression.py:create_at_level` (~233) snapshots runtime, configures level1, then sequentially previews/applies each higher step; any exception restores runtime. Remove mode before passing spec.
- Its preflight checks required level entries but currently ignores surplus entries; exact adapter keyset validation is therefore mandatory, not optional cleanup.
- `_check_choices` (~144) rejects unsupported fields, wrong counts, duplicates, unknown/already-prepared spells, invalid metamagic/subclass selections. `apply_level_choices` (~176) performs canonical state validation before mutation.
- `game.py:_capture_runtime_snapshot/_restore_runtime_snapshot` (~19140) preserve character/world/messages/narrations/RNG/pending XP and top-level container identities. Do not replace this with save-load rollback.
- `SessionManager.create_campaign` stores before registering session. `CampaignStore.create_campaign` (~549) serializes/validates first, then inserts in existing `_transaction` (~167), which rolls back on exception. Rejected choice requests must never call the store or register sessions. A test of insert-then-precommit failure must leave no row and no registry entry.
- `game.py` save/load already handles progression_level, metamagic, subclass_id (~1988 and2618); `campaign_validation.py` delegates to engine save validation; `campaign_serializer.restore_stored_campaign` restores that validated payload. No new save format/version.
- Limit claim: this leaf proves validation/creation and transaction failure safety, not global exactly-once campaign creation or every possible exception after an existing transaction has committed.

## Minimum RED → GREEN tests

New focused module: `ai-dnd/api/tests/test_roadmap_c06_creation_http.py`; independent scratch SQLite stores, existing FixedAuthenticator test fixture and ASGI HTTP transport. Do not access owner campaign data or use a real model.

1. `test_custom_sorcerer_three_http_creates_and_reopens_exact_state`: POST valid example using literal existing SPEC; expect200, character level3/applied3/PB2, metamagic exact2, subclass exact ID, cantrips exact4, six ordinary prepared spells, slots {"1":4,"2":2}, HP20 for existing SPEC CON14 (L1HP8 +6 +6), identity/equipment unchanged. Read persisted engine_save, create fresh store/manager/app, resume through HTTP, compare the same fields and exact spell state. Exercise all four supported subclass IDs as subcases, without claiming their effects.
2. `test_default_random_and_explicit_levels_preserve_compatibility`: absent character, existing custom request with omitted starting_level, explicit1, custom2 and random with omitted/1 stay successful with expected level1/2 resources. Existing non-Sorcerer custom level1 remains valid. Both route aliases are exercised.
3. `test_malformed_or_unsupported_creation_never_persists`: strict-type/range levels; non-Sorcerer2/3; random2/choices; missing/excess/wrong per-level keys; null step; unknown fields; wrong counts. HTTP422; database campaign rows and manager registry unchanged; no store.create_campaign call. Include direct-manager rejection so configure_character(**extra) cannot silently swallow malformed new fields.
4. `test_semantic_choice_failure_rolls_back_before_campaign_publish`: valid-shaped bad final level3 subclass or duplicate/already-prepared/unknown spell; expect invalid_character422. A session_factory captures the new session before mutation; compare full runtime snapshot after rejection, including RNG and container identities. Spy-wrapping (not replacing) real apply proves L2 actually applied before late L3 semantic failure. Existing campaign/session remains untouched.
5. `test_creation_store_failure_leaves_no_campaign_or_session`: inject failure after INSERT but before transaction commit via existing transaction seam; existing storage-error HTTP mapping, zero inserted rows, unchanged manager maps. Do not change production transaction behavior.
6. `test_creation_contract_and_projection_parity`: runtime schemas versus published request schemas (required/optional/null/strict bounds, aliases, nested extra-forbid); response projection exposes canonical choice fields and does not mutate state. Generated request validators preserve nested keys and values (no silent stripping), accept valid/default requests and reject structural primitive/count errors. Business cross-field/semantic enforcement is server-owned; do not falsely claim Orval generated validators encode all model validators.

Initial RED should be a valid level3 HTTP request receiving422 for extra fields (not an import/harness error), plus absent public choice projection. Reuse focused existing core tests; do not manufacture regressions to re-prove accepted capability.

Commands (from workspace parent; adapt unique evidence labels only):

```text
env -i PATH=/usr/bin:/bin HOME=/tmp/ai-dnd-takeover-harness/home TMPDIR=/tmp/ai-dnd-takeover-harness/tmp /workspace/scratch/a1b372df36be/ai-dnd-takeover/.venv/bin/python -I -B ai-dnd-takeover-work/run_guarded.py c06-creation-http-red api.tests.test_roadmap_c06_creation_http
```

GREEN uses a new label plus `api.tests.test_roadmap_c06`, `api.tests.test_roadmap_c06_level3`, `api.tests.test_roadmap_c06_slot_maps`, `api.tests.test_roadmap_c06_slot2_cast`, `api.tests.test_character_creation_2024`, `api.tests.test_campaign_persistence`, `api.tests.test_contract_parity`, and relevant existing campaign-create/rollback tests. Run generated-contract Node test (new focused `.mjs`, following current slot2 contract test), codegen repeat/no drift and workspace typecheck. Record actual outcomes, no inferred passes. Independent review must precede leaf acceptance; no tests were run for this draft.

## Honest remaining obligations / stop condition

Still pending: Innate Sorcery activation/effects; Font of Magic/Sorcery Point tracking/conversion; effects of stored Metamagic options; all subclass feature effects and always-prepared grants (C19); optional cantrip/spell/Metamagic replacement; unsupported spell resolvers/access, other classes above1, levels4+, UI, live level-up HTTP. Current source table's Sorcery Points3 is capacity metadata, not a tracked spendable pool. Four subclasses selected/stored does not mean four subclasses implemented. Selected Magic Missile slot2 acceptance does not make every prepared spell playable.

Stop after this bounded HTTP creation/save/reopen contract passes, generated schemas are synchronized, and independent review accepts the leaf. Do not mark C06 complete, create a UI, introduce a capability framework, or start unrelated rules work.

Rollback: retain reviewed pre-leaf source snapshot; no writes to personal saves. Already accepted core understands new level3 saves, but reverting the HTTP projection adapter removes public choice fields/new input access. Never downgrade persisted level3 characters to level1 or discard choices. No push/merge/deploy implied.

Open review choice: the proposed manager shared-schema revalidation tightens direct (non-HTTP) callers to the existing HTTP input contract. Verify existing direct custom-manager tests do not intentionally depend on ignored extra fields; if they do, narrow new-field validation while preserving this exact HTTP contract. This is not a reason to broaden product scope.

## Review refinement: pending-effects projection

Recommended small addition for honest public state: factor the existing pure pending-list construction out of `character_progression.preview_level_up` into one shared helper taking class and an explicit level (preview supplies its target; serializer supplies **applied** level), and expose its derived result as optional `character.progression_effects_pending: list[str]` for Sorcerer progression. Preview and serializer use the same helper; no new mechanics/resources/capability framework, no persisted duplicate list, and no call to a blocked next-level preview. For accepted level3 it must include Innate Sorcery, Font of Magic/Sorcery Points, Metamagic, subclass features/always-prepared grants, and unsupported optional replacements. For lower applied levels include only already-earned pending class obligations plus the existing optional-replacement limitation; XP-granted but unapplied levels must not claim later features. Mirror this optional field in GameCharacter/generated types. Extend test1/test6 to assert the list on create and reopen, helper/serializer purity and consistency with existing previews; preserve existing preview wording/contracts. This narrowly adds `character_progression.py` to the expected file set solely for extracting existing status text. Reviewer decides this refinement before implementation; it supersedes the preceding 'no expected core edits' statement only for that pure extraction.

## Parent review refinements before implementation
- Do not run historical global-app contract-parity as a purported green gate: guard intentionally disables the global app. Use real create_app OpenAPI for the new request/projection plus published/generated contract comparisons. Keep historical appNone baseline explicitly separate; never weaken guard to repair its harness.
- Public projection must identify stored choices as choices and expose bounded informative effects_pending for explicit applied progression. Factor the existing preview pending-text construction into a pure shared helper if needed; never call a blocked next-level preview to infer current status. No duplicate rules, capabilities framework or spendable SorceryPoints inference. Old unprogressed/other-class responses keep absent optional fields; projection must be detached and pure.
- HTTP-created level3 must feed the existing actual structured slot2 Magic Missile path in a test (with synthetic encounter setup using existing owner), then save/reopen/replay; do not substitute a separately constructed core caster as the integration proof.
- Strict numerical starting_level and exact external step keys must also hold at the direct manager boundary. Nested aliases may be normalized internally but external `level_2`/`level_3` aliases must not silently widen the published numeric-key HTTP contract. Decide normalization boundary before coding.

## Draft refinement: exact pending projection name


Recommended small addition for honest public state: factor the existing pure pending-list construction out of `character_progression.preview_level_up` into one shared helper taking class and an explicit level (preview supplies its target; serializer supplies **applied** level), and expose its derived result as optional `character.progression_effects_pending: list[str]` for Sorcerer progression. Preview and serializer use the same helper; no new mechanics/resources/capability framework, no persisted duplicate list, and no call to a blocked next-level preview. For accepted level3 it must include Innate Sorcery, Font of Magic/Sorcery Points, Metamagic, subclass features/always-prepared grants, and unsupported optional replacements. For lower applied levels include only already-earned pending class obligations plus the existing optional-replacement limitation; XP-granted but unapplied levels must not claim later features. Mirror this optional field in GameCharacter/generated types. Extend test1/test6 to assert the list on create and reopen, helper/serializer purity and consistency with existing previews; preserve existing preview wording/contracts. This narrowly adds `character_progression.py` to the expected file set solely for extracting existing status text. Reviewer decides this refinement before implementation; it supersedes the preceding 'no expected core edits' statement only for that pure extraction.

Pre-TDD review requirement: route by_alias=True alone is insufficient. exclude_none=True must be used; test validlevel2 missingstep3, level1 emptychoices, and random omission through actualHTTP so optionaldefaults cannot become explicitnull. Do not accept internal level_2/level_3 from externalHTTP.

Further pre-TDD review refinements:
- Existing direct manager character callers found: main.py and valid Bruenor inventory roundtrip fixture; no known ignored-extra-fields contract. Shared-schema revalidation is allowed within this adapter boundary; run the existing inventory roundtrip regression.
- Runtime CampaignSessionResponse.state is dict[str,Any]. create_app OpenAPI proves typed request components, not a nonexistent runtime GameCharacter schema. Response checks use actual HTTP JSON and published/generated GameCharacter only; do not broaden runtime response models merely for parity.
- Real transaction fault test must see the newly inserted row inside the transaction before raising, assert exactly one injected fault, then verify absence through a fresh connection and unchanged manager maps. Reuse the real transaction owner, no fake successful save.
