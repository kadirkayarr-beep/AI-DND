# C05.magic_missile.slot2_single_target — C06 selected castability dependency

Status: pre-TDD plan approved; bounded implementation independently statically accepted. Combined regression and evidence binding tracked in the leaf handoff. Source entry phb2024:spell:magic-missile; localPHBmetadata points PDF294, but full rule verified here from official D&D Beyond 2024 Basic Rules web, NOT PHBvisual acceptance or SRD5.2.
- https://www.dndbeyond.com/sources/dnd/br-2024/spell-descriptions#MagicMissile
- https://www.dndbeyond.com/sources/dnd/br-2024/spells#SpellSlots
Retrieved2026-10-28. Paraphrased oracle: base1 spell has3darts; each adds1d4+1Force, and slot2 creates4darts. Spend the chosen slot once. A slot must be at least the spell's level. Existing per-dart damage-roll policy is retained; no multi-target/shared-roll adjudication is changed.

## Scope / owners
C06actualSorcerer3 corestate supplies realslots4/2; C09existingtarget/mitigation/RNG/action/save/receipt owners remain sole authorities. No newspellengine, no natural-language slot guessing.
- spell_scope._cast(session,spell_id,target_id,slot_level): explicitMagicMissile slot2 only; otherupcastmodes remainunsupported. DefaultMMslot1 still3darts. Selectedbucket availability/counter/result fields useactualchosenlevel. One-slot-per-turn marker unchanged; no state/RNG/action change on refusal.
- spell_registry.cast_spell: successful slot_level and spell_slot delta reportactual2, not base1. ValidMMslot2rejection may reportrequested2; unsupportedothermodes retainexistingcontract.
- action_economy._execute: forward optional slot_level onlyfor magic; reject that choiceonotherstepkinds.
- api.schemas.EconomyStepInput: optional strictinteger slot_level1..9, magic-only modelvalidator. ExistingNone is omittedby model_dump(exclude_none=True), preserving legacyrequestfingerprints. Higherunsupportedslots stillrejectedbymechanicowner.
- lib/api-spec/openapi.yaml component; regenerate existing api-client-react/api-zod via approvedOrvalconfig, no manualfake generatedcode or newruntimeadapter.

## Tests (api.tests.test_roadmap_c06_slot2_cast)
SlotTwoTests:
- test_real_level_three_slot_two_spends_only_second_bucket_and_emits_four_darts (deterministicrawdie2 =>4x3=12; actualcorefixture, no capacitypatch)
- test_default_slot_one_remains_three_darts
- test_empty_unearned_or_unsupported_slot_refuses_before_rng_and_resources
- test_additional_action_does_not_allow_second_spell_slot_same_turn
- test_save_load_and_long_rest_preserve_selected_bucket
- test_native_nonmagic_slot_choice_refuses
SlotTwoApiTests:
- test_http_explicit_slot_two_receipt_replays_after_reopen_without_reroll (realASGI, syntheticSQLite, fixedtestprincipal; no realClerk/model claim)
- test_same_uuid_changed_slot_level_is_conflict
- test_slot_two_save_failure_rolls_back_and_retry_spends_once
- test_schema_strictness_and_legacy_absent_field_fingerprint_shape
- test_runtime_and_published_slot_field_contract_agree

Use existing test_spell_scope.caster with actual cp.apply2 andapply3 choices, or genuinecreatedlevel3 fixture. HTTPpath is existing /game/sessions/{id}/turn, not a mockedreplacementdriver. Faulttest reuses existing store transaction/rollbackowner; no personalDB. Testsassert resourcepool,damage,dartcount,RNG,othercampaignisolation,actualreceipt/reopen. Counterexamples first must failforunsupportedmechanic/schema, notmissingdependencies.

RED/PASS commands use verified run_guarded.py withunique c06-slot2-red/green labels andmoduleabove. RelatedC06/C09, spell_scope, actioneconomy, persistence/idempotency, save/migration; targetedruntimecreate_appschema check avoids historicalglobalappNone harness issue. Existing unsupportedMMslot2 test moves unsupportedboundaryto3, pairedwithnewunearnedslot2test; oldexpectations otherwise preserved. Contractgenerator and typecheck output retained separately.

## Boundaries
Onlysingle-target MM, levels1and2. No Shield, multi-target allocation, otherupcastspells, higherlevels or subclassfeatures are declaredcomplete. UIselector andcreate-at-levelHTTP/UI remain separate; this leaf exposes typed existingturnchoice, not fullgameplayacceptance. WholeC05/C06 staysOPEN.
Rights: officialpublicreference forprivateauthorizeddevelopment; not a redistributionlicense. Storefacts/sourceURLs, notbooktext. No push/merge/deploy/security/authchange. Preserveprechangecode/saves; oldbackend rejectsnewrequestfield, so downgrade usesmatchingclient/schema/code snapshot. Independentleafreview beforeimplementation andpostimplementationB02binding required.

Executable RED from workspace root:
env -i PATH=/usr/bin:/bin HOME=/tmp/ai-dnd-takeover-harness/home TMPDIR=/tmp/ai-dnd-takeover-harness/tmp /workspace/scratch/a1b372df36be/ai-dnd-takeover/.venv/bin/python -I -B ai-dnd-takeover-work/run_guarded.py c06-slot2-red api.tests.test_roadmap_c06_slot2_cast
PASS uses c06-slot2-green plus api.tests.test_roadmap_c06_level3, api.tests.test_roadmap_c09, api.tests.test_spell_scope, api.tests.test_action_economy, api.tests.test_persistence_idempotency, test_save_migration.
Generator from repository root: pnpm --filter @workspace/api-spec codegen (existingconfig; dependenciesinstalledfromfrozenlockwithscriptsdisabled, minimumReleaseAge retained). Record fulloutput; no claimedgeneratedsuccesswithoutactualrun. Exactgeneratedschema/type paths remain ownedbyOrval, notmanualimplementation.

## Pre-TDD review refinements
Slot1empty/slot2available mustsucceed; slot2empty mustnotfallbacktoslot1; omittedselection mustnotautoupcast. One-slot-per-turn test crosses2→1 buckets with an existing authoritative extra-action fixture. Registry success asserts outer/result slot_level2 and one level2 debit. Runtime magic-only crossfield checks are separate from publishedtype/range/nullability because modelvalidators are notautomaticallyexportedtoOpenAPI/Zod. Alltests useexisting /api/game/sessions/{id}/turn. ApprovedforboundedTDD; implementationacceptancepending.
