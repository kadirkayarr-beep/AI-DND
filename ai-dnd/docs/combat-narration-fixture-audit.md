# Combat and narration runtime fixture audit

## Scope and result

This is an offline, test-only reconciliation of `test_combat_v2.py` and
`test_narrative_rebalance.py`, not a gameplay remediation or a redesign of
parse/preflight checks. The final integration repair is described below.
No production engine or action-economy code was changed. No test was
skipped, deleted, marked expected-failure, or excluded to make the selection green.

The initial command was:

```sh
cd ai-dnd
python -m unittest test_combat_v2 test_narrative_rebalance
```

It reproduced **68 tests, 14 errors and 7 failures**. The errors included missing
authoritative attack distance, native request rejection for ambiguous/nonlocal
targets, and bypassing legacy state normalization. The narrative failures
included old dialogue telemetry and travel expectations without a known route.

The reconciled selection contains **70 test methods: 68 passing, 2 failing**.
The two failures represent real product defects below, with **3 failing
assertion records** because the location query has two independently checked
contracts. There are no errors or hidden failures. The 78 adjacent authoritative
combat and narrative-safety methods also pass.

## Fixture corrections and preserved contracts

- Combat has explicit five-foot authored distance, held/owned longsword equipment,
  proficiency, damage provenance, and enemy perception. None of these facts is
  guessed by the engine or supplied by model narration.
- Strict session-owned dice cover initiative, critical damage, unconscious-target
  advantage, death saves, and stabilization recovery. Extra or unused dice still
  fail. The stabilization regression additionally observes the real enemy-turn
  owner to report a forbidden continuation before unplanned dice.
- Enemy-owned initiative slots reject a player attack without rolling; a neutral
  continuation resolves the actual enemy turn. Ambiguous and nonlocal turn
  requests assert the current request error plus unchanged serialized state and
  RNG. Direct intent clarification checks remain intact.
- Ordinary lethal NPC damage asserts **dead**, not the old generic unconscious
  result. Player zero HP retains death-save initiative boundaries instead of
  prematurely ending combat.
- Legacy preparation uses an actual version-2 save with its historical inactive
  combat shape, loaded through the real migration owner; it does not delete fields
  from an already native world before modern request validation.
- Narrative cases own fresh sessions. Resetting a character in the shared default
  session did not reset earlier journeys, scene state or time, causing order
  dependence that masked the route prerequisites.
- Conversation-only narration now asserts `deterministic_dialogue`, one actual
  model call, and the interaction owner's safe substitution of packets carrying
  unsupported lore/world updates. Telemetry describes the accepted substitute;
  it must not be forced to describe a general-validator fallback that did not run.
  A new ordinary-smalltalk case independently proves that general narration still
  rejects unsupported lore and canonical relationship invention with the original
  reason codes and no retry.
- Successful procedural travel has an authored local procedural origin, allowing
  the Time owner's five-minute pedestrian convention. Only encounter dice are
  controlled. Tests assert 300 seconds, the matching registered destination,
  committed player location and arrival state. The low-level proposal fixture
  initializes the clock for its already-resolved starting scene.
- A separate negative route test proves that registering a matching proposal does
  not move the player when the origin has no authoritative route/local convention:
  status is `unverified`, success is false, time is unchanged and no travel dice
  are consumed. Unrelated proposal rejection and model-call limits remain checked.

## Genuine defects retained and separately tracked

### Enemy acts again after stabilization — existing task #171

`test_combat_v2.CombatV2Turns.test_npc_knocks_out_player` now reaches the actual
Death owner. A real enemy critical hit reduces the player to zero. Three
successful death saves, separated by real enemy misses, stabilize the player.
The scheduler then calls the enemy-turn owner again instead of returning at the
stable player boundary:

```text
AssertionError: True is not false : Enemy attacked again after stabilization
```

An earlier diagnostic execution allowed that extra turn to complete and observed
four enemy attacks, where only the initial hit and two intervening misses were
permitted. The final regression detects the attempt before any extra dice or
damage. Its script contains only the legitimate rolls, so fixing the scheduler
does not create an unused-dice failure. Production work belongs to the existing
task **Stop further enemy attacks when a death save stabilizes the player**
(#171); no duplicate task was proposed.

### A location query is replaced by NPC prose — proposed task #177

`test_narrative_rebalance.TestNarrativeRebalance.test_27_direct_factual_queries_use_zero_model_calls`
retains two visible failing subtests for `Neredeyim?` with an active local NPC:

```text
python_only:      AssertionError: 1 != 0
canonical_answer: AssertionError: 'Eski Han' not found in 'Hancı başını sallar.'
```

Python already resolves a successful location query with the correct
`direct_response` (`Bulunduğun yer: Eski Han.`), but the interaction conversation
branch calls the model and substitutes its prose. This is not an obsolete
telemetry label: the canonical answer is actually lost. The test uses a scoped
offline response to demonstrate the loss, not a live model call. Presence and NPC
identity assertions still run and pass as separate subtests. Remediation is
tracked as **Keep location questions factual even while talking to an NPC** (#177).

## Retained evidence and reproduction

The final combined invocation, including both edited modules followed by the
adjacent unchanged owner suites, was:

```sh
python ai-dnd/scripts/run_regression_evidence.py \
  test_combat_v2 test_narrative_rebalance \
  test_combat_v2_authoritative test_narrative_safety_calibration \
  --archive-root ai-dnd/docs/evidence/combat-narration-fixture-audit
```

**148 methods ran; 146 passed; the same two methods produced three failure
records.** The command exits nonzero, intentionally preserving genuine failures.
The final combined archive, with per-test records, traceback log and source
fingerprints, is:

[Final combined run](evidence/combat-narration-fixture-audit/20261005T141843Z-c2c7c62d44544aca82845814035ea1b9/run.json)

Earlier diagnostic evidence is retained rather than replaced:

- [Reconciled target run before the stabilization observer refinement](evidence/combat-narration-fixture-audit/20261005T141728Z-864f02d6a3144a449e12a457b269a6e3/run.json):
  70 methods, the same three failure records; the stabilization assertion counted
  the extra completed attack.
- [Adjacent owner run](evidence/combat-narration-owner-checks/20261005T141752Z-461742794738402eafc1c5d46f4fc790/run.json):
  78 methods, all passing.

These are new offline local-engine runs against the fingerprinted dirty test
checkout. They do not certify historical runs, root discovery of unrelated
modules, browser behavior, live Qwen quality, or production HTTP acceptance.

## Final integrated collection repair

Completion combined concurrent edits to the shared API fixture file,
`api/tests/test_campaign_api.py`, and exposed an unmatched closing brace plus
three orphaned copies of the failed-exit test tail. These copies were removed,
without changing any intact test body or removing any async test definition.
The failed-exit, stale-resumed-exit and merchant tests all remain and pass.
This is a minimal collection-integrity repair, not additional gameplay scope.

The first repaired combined run reached 145 methods but additionally exposed a
fixture invocation issue: API narration observation can wrap the module's
`finalize_narration` callable without exposing the marker used by dynamic
`GameSession` helper lookup. The direct safety test now invokes the same module
callable with its owning session explicitly, as the other direct safety fixtures
already do. Mechanics and assertions are unchanged.
That failed attempt is retained:

[First integrated run](evidence/combat-narration-integrated-checks/20261005T142451Z-c7aca7ad20e044398b85f9f883ab6265/run.json)

The final invocation includes the three previously unimportable suites, both
edited runtime modules, and both adjacent owner suites:

```sh
python ai-dnd/scripts/run_regression_evidence.py \
  api.tests.test_campaign_api api.tests.test_persistence_idempotency \
  api.tests.test_death_bounded test_combat_v2 test_narrative_rebalance \
  test_combat_v2_authoritative test_narrative_safety_calibration \
  --archive-root ai-dnd/docs/evidence/combat-narration-integrated-checks
```

**223 methods execute: 221 pass; only the same two deliberately retained product
defects fail, producing three assertion failure records. There are no errors.**
All 75 campaign API, persistence-idempotency and bounded-death methods pass;
all 78 adjacent combat/narration owner methods pass in that same process.

[Final integrated run](evidence/combat-narration-integrated-checks/20261005T142614Z-8e1c92a9374b472db598c6f97a30de16/run.json)

The existing source-definition checker also reports **71 test files, zero
errors** across root `test*.py` and `api/tests/test*.py`. An AST parse of the
repaired API file succeeds; its async test-definition inventory matches the
pre-repair source, and its intact failed-exit test body is byte-for-byte unchanged.
No preflight rules were relaxed and the tracked gameplay failures remain visible.
