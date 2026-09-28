# Engine Change Approval Package

**Date:** 28 September 2026  
**Decision requested:** Owner approval before any change to `ai-dnd/game.py`  
**Current gate:** **ENGINE CHANGE APPROVAL REQUIRED**

No engine code, Combat V3, Spells V1, or XP/Leveling V1 implementation is included in this package. The protected `game.py` file remains unchanged. This package consolidates known engine requirements for owner review.

## 1. Verified current baseline

### Phase status

| Roadmap phase | Current status | Evidence / boundary |
|---|---|---|
| Phase 1 — Skill Checks V1 | **PARTIAL — ENGINE ROUTING REQUIRED** | The safe typed `skill_check_result` contract, allowlist, generated client, result card, rollback coverage, and currently supported canonical routes remain. Missing engine routes: Persuasion, Deception, Acrobatics, and Survival. No adapter, narration, or model-output workaround was added. |
| Phase 2 — Combat-result history persistence | **PASS** | Validated history is stored separately from transcript history, bounded to 50 results per campaign, and restored through campaign detail/resume. Failed turns and failed autosaves do not append results. |
| Phase 3 — Quest Outcomes V1 | **PARTIAL/BLOCKED — ENGINE CONTRACT REQUIRED** | The frozen engine has no canonical quest acceptance, objective progression, completion, failure, or cancellation outcomes. The quest ledger remains empty; no quest state is inferred from Qwen narration, player wording, or browser state. |

### Source and persistence versions

- Protected `ai-dnd/game.py` SHA-256 before Phase 2: `e971f4cade451828697ab7c49900b634a9cf1a6a1997aa8c733d2a13e0a9c24a`.
- SHA-256 after Phases 2–3: the same value. The file was not edited.
- Current SQLite schema version: **2**. Version 2 adds the separate combat-history table; the change is additive.
- Current campaign-envelope format: **1**.
- Current engine save version: **1**.
- Combat history is server-authored, separately validated, and limited to the public combat-result allowlist. Each entry has a stable event ID and turn index. Transcript text is not used to reconstruct results.

### Current API contracts

- Turn requests continue to submit player text, not authoritative combat, skill, quest, or character state.
- Turn responses may include an allowlisted `skill_check_result` and a validated `combat_history_entry`.
- Campaign detail and resume responses include `combat_history`; result history remains separate from the player/narration transcript.
- The existing supported campaign and turn routes remain the interface. OpenAPI was updated and codegen ran; the broader legacy health/route naming mismatch recorded in the status checkpoint is not claimed as resolved by this work.
- The browser renders server-returned results and deduplicates history by stable event ID. It does not derive rolls from narration.

### Verification completed

- API suite: **84 passed, 0 failed**.
- Portable deterministic gates: **17/17 passed**.
- Frontend Combat panel tests: **6 passed**.
- Workspace library/codegen typecheck and AI-DND experience typecheck: **passed**.
- Production frontend build: **passed**; Vite emitted the existing non-blocking Tooltip sourcemap warning.
- Phase 1 partial test result: supported structured skill-result, allowlist, rollback, and deterministic skill regressions passed within the API and deterministic suites. The four missing routes are intentionally unsupported and are not being counted as passing.
- Current-hash live-Qwen smoke is general pipeline evidence; it does not exercise skill-check routing. The disposable restart/resume smoke verifies persistence, not missing Phase 1 routes.
- Live FastAPI restart/resume smoke with a disposable temporary campaign database: **passed**; one structured combat-history result was restored and the quest ledger remained empty.
- `git diff --check`: passed.
- The registered AI-DND experience and FastAPI workflows restarted successfully; the browser preview loaded.
- API and persistence tests used disposable test data. The owner’s Cedric campaign was not deleted or used as a test fixture, and no campaign-delete endpoint was added.

### Known issues and boundaries

- Pre-v2 combat results cannot be recovered because they were never stored. Older campaigns migrate with empty combat history; no narration backfill is attempted.
- Phase 1 still lacks the four named engine routes.
- Quest lifecycle behavior remains unsupported until the engine contract and authoritative quest-definition/trigger source are approved.
- Runtime sessions remain process-local, and more than one FastAPI workflow is configured. Route gameplay through one canonical API instance.
- The broader legacy OpenAPI/health-route naming discrepancy remains outside the Phase 2 persistence change.
- Local roadmap material did not provide acceptance details for **#38**. It is **approved but deferred**: do not execute or invent scope; include it in owner follow-up after the approval boundary.

## 2. Proposed engine change map

These are proposals for approval, not implementation instructions. Function names below refer to the existing frozen engine.

### A. Skill Checks V1 — finish missing routing

- **Existing functions:** `run_player_turn()`, `execute_intent()`, and `perform_skill_check()`.
- **Why required:** Persuasion, Deception, Acrobatics, and Survival do not currently have canonical engine routing. The API and browser cannot safely supply that authority.
- **Smallest proposed change:** Add explicit engine-owned route recognition for those four skills and send valid checks through the existing shared resolver. Do not add an API adapter fallback, parse narration, or trust arbitrary Qwen output.
- **New state:** None proposed.
- **Mutation rules:** Validate intent and skill in Python first. Preserve existing canonical consequences only; invalid or unsupported requests must not mutate state.
- **RNG:** Use the session’s existing RNG for one roll per validated check. Add no hidden or client-side rolls.
- **Save/version:** No save fields or migration are expected. Keep engine save v1, campaign format v1, and SQLite schema v2.
- **Rollback:** The existing turn snapshot must restore state and RNG if resolution, validation, or autosave fails.
- **API impact:** Reuse the current allowlisted `skill_check_result`; no client-authored DC, roll, modifier, or outcome.
- **Frontend impact:** Reuse the existing server-result card; no new dice logic.
- **Session isolation:** Resolve through the current `GameSession`-bound engine context; add no module-global check state.
- **Backward compatibility:** Existing v1 saves remain unchanged and loadable.
- **Tests required:** One route test per missing skill; invalid and ambiguous intent; server-owned ability/proficiency/DC/roll/outcome; no mutation on invalid requests; RNG determinism; rollback; session isolation; existing supported-skill regressions; API allowlist; proof that Qwen cannot author results.

### B. Quest Outcomes V1 — define a canonical lifecycle contract

- **Existing functions/classes:** `GameSession`, `run_player_turn()`, `execute_intent()`, `serialize_game_state()`, and `load_game()`. No quest lifecycle function or structured quest-event producer currently exists.
- **Why required:** The browser’s quest ledger has no authoritative source for acceptance, objective progression, completion, failure, or cancellation.
- **Smallest proposed change:** After the owner approves where quest definitions and deterministic objective triggers come from, add session-owned canonical quest records and typed transition events. A proposed event should carry a stable event ID, quest ID, transition kind, optional objective ID, turn/action reference, and validated resulting status. Do not implement progress from free-form narration.
- **New state:** Proposed `quests` records with stable IDs, status, and objective state; proposed `quest_events` with stable IDs and source-action references. Exact quest-definition format and trigger rules remain an approval prerequisite.
- **Mutation rules:** Python alone accepts or changes quests. Progress only from an explicit validated player decision or a canonical engine outcome matched to an approved objective rule. Terminal transitions are idempotent; failed turns do not commit them.
- **RNG:** No new randomness for lifecycle bookkeeping. Any underlying action roll remains the existing action’s one canonical roll.
- **Save/version:** Combine approved quest state with the next engine-save migration described below; do not write quest transitions into narration or reconstruct them later.
- **Rollback:** Quest state/events must roll back with the turn snapshot and commit atomically with campaign autosave.
- **API impact:** Add allowlisted typed quest state/events to the API and OpenAPI only after the engine contract exists. Keep unsupported transitions disabled until then.
- **Frontend impact:** Display only returned canonical state/events. Keep the ledger empty when no transition exists; no local acceptance/progression/completion.
- **Session isolation:** Quest records and events belong to one `GameSession` and campaign.
- **Backward compatibility:** Migrate old saves to an empty quest collection while preserving all existing state; reject invalid new state explicitly rather than resetting a save.
- **Tests required:** Acceptance; each objective transition; completion; failure/cancellation; duplicate-event idempotency; no narration-derived state; rollback; save/resume/restart; invalid/forged event; session and campaign isolation; old-save migration.

### C. Combat V3 — bounded canonical turn foundation

- **Existing functions/classes:** `GameSession`, `ensure_combat_state()`, `start_combat()`, `resolve_attack()`, `resolve_enemy_attack()`, `advance_combat_turn()`, `end_combat()`, `execute_intent()`, `run_player_turn()`, `serialize_game_state()`, and `load_game()`.
- **Why required:** Current Combat V1/V2 is a limited single-target exchange. It does not provide the canonical multi-participant turn scheduler, stable target identity, and exact resumable state required by the roadmap.
- **Smallest proposed change:** Replace/extend the current combat state with a bounded Python-owned scheduler: stable participant IDs; initiative order; round and current actor; one primary action per actor turn; explicit target-ID validation; enemy action resolution in Python; canonical defeated/unconscious status; and a resulting turn owner/end state. Keep grid movement, reactions, bonus actions, legendary/lair actions, complex conditions, full death saves, and encounter balancing out of scope unless separately approved.
- **New state:** A structured combat state containing active status, round, participant records, initiative order, current actor ID, action availability/usage, target references, and combat-end status. Display names are not identities.
- **Mutation rules:** Python validates turn ownership, action availability, target legality, and participant status before mutation. Qwen may help resolve semantic references and narrate only after Python resolves the action. Ambiguous targets must be clarified, never guessed.
- **RNG:** Use the session RNG for initiative and canonical attacks/damage. Define stable tie behavior. Save and restore RNG at the same boundaries; no frontend or Qwen rolls.
- **Save/version:** Persist the exact active scheduler state and participant IDs. Use the next engine-save version and explicit v1 migration; do not silently end or reset old combat.
- **Rollback:** A rejected action changes neither combat state nor RNG. A failed turn/autosave restores the complete pre-turn state; history and state commit together.
- **API impact:** Return allowlisted active/round/current actor/initiative/participants/status/action result/resulting actor/end state. Do not expose engine objects.
- **Frontend impact:** Extend the existing combat presentation with initiative, current-turn highlight, multiple targets, participant HP/status, invalid-turn feedback, and explicit ambiguity handling. The browser never advances turns.
- **Session isolation:** Combat scheduler and RNG remain owned by the campaign’s `GameSession`; no shared mutable combat globals.
- **Backward compatibility:** Existing v1 campaigns must load through a tested migration. Combat V1/V2 compatibility tests remain where applicable.
- **Tests required:** Initiative ordering/ties; current actor; invalid out-of-turn action; target IDs; two enemies/three participants; defeat/unconscious; round rollover/completion; persistence at player/enemy/round boundaries; restart without skipped/doubled turns; rollback; v1 migration; forged/detached participants and targets; session/campaign isolation; existing Combat V1/V2 regressions; real browser and live `qwen3:8b` combat before a future PASS.

### D. Spells V1 — anticipated compatibility only

- **Existing functions/classes:** `GameSession`, `run_player_turn()`, `execute_intent()`, and the approved Combat V3 action resolver. There is no current spell resolver.
- **Why anticipated:** Spell casting will need to consume the same canonical turn, actor, and target rules as Combat V3.
- **Smallest future change:** After separate approval, add a small curated spell set with explicit spell ID, allowed class/minimum level, casting ability, action cost, target type, resource cost, canonical effect, and persistence. Do not add the full spell catalogue or unsupported reactions, concentration, summons, or complex areas by default.
- **New state:** Future known-spell IDs and validated spell-resource counts, scoped to the character/session. Exact fields depend on the approved class and resource model.
- **Mutation rules:** Python validates caster, spell, level, target, available resource, and effect; consumes resources only on a valid resolved cast. Browser and Qwen cannot submit damage, healing, or slot totals.
- **RNG:** Reuse session RNG only for an approved attack/save/effect. Resource validation and consumption add no randomness.
- **Save/version:** Anticipated engine-save v3 after the proposed v2 foundation, with defaults/migration for existing saves; no implementation now.
- **Rollback:** Restore spell resources, effects, and RNG on rejected or failed turns.
- **API impact:** Add a typed allowlisted spell result and resource summary; regenerate OpenAPI clients.
- **Frontend impact:** Optional spell list/buttons may submit ordinary player actions only; display server-returned results.
- **Session isolation:** Known spells/resources are canonical character state, not browser state or shared globals.
- **Backward compatibility:** Old campaigns load with the approved default spell/resource state, not silently granted slots.
- **Tests required:** Valid/invalid caster, class/level, unsupported spell, target, attack/save/heal, resource consumption/no-resource rejection/cantrip behavior, rollback, persistence/restart/migration, session isolation, and proof that Qwen/browser cannot author effects.

### E. XP / Leveling V1 — anticipated compatibility only

- **Existing functions/classes:** `GameSession`, canonical character state, `resolve_attack()`, `resolve_enemy_attack()`, and `run_player_turn()`. No XP award or leveling transition currently exists.
- **Why anticipated:** XP must be awarded from canonical outcomes, such as an enemy defeat or a future canonical quest completion, not from narration.
- **Smallest future change:** After separate approval, add a bounded XP threshold table and a single server-side award path keyed to canonical completion events. Keep class progression limited to explicitly supported fields.
- **New state:** Add canonical integer `xp`; use/extend the existing character level field. Add an award-event ID or equivalent deduplication reference so retries cannot double-grant XP.
- **Mutation rules:** Python awards only from approved canonical defeat/completion events and performs level transitions from the approved table. No client/Qwen XP input; no mixing milestone and XP rules.
- **RNG:** XP award and threshold checks are deterministic and consume no RNG.
- **Save/version:** Anticipated engine-save v4 after the earlier foundations, or a newly approved combined version plan; old saves receive explicit zero/default migration values.
- **Rollback:** XP, level, and award IDs roll back atomically with the source combat/quest transition.
- **API impact:** Expose safe XP/level/threshold state and any level-up result through typed response contracts.
- **Frontend impact:** Display server-returned progression; never submit XP or level changes.
- **Session isolation:** XP/level are owned by the campaign character state.
- **Backward compatibility:** Preserve level-1/legacy character state with an explicit migration; never infer XP from transcript text.
- **Tests required:** Canonical award source, duplicate prevention, threshold boundaries, level transition, invalid/forged grants, rollback, persistence/restart/migration, session isolation, and Qwen/browser authority checks.

## 3. Save and migration plan

### Current versions

- SQLite schema: **2**.
- Campaign envelope: **1**.
- Engine save: **1**.

### Proposed next version after approval

- Use one explicit engine-save **1 → 2** migration for the approved Quest Outcomes and Combat V3 canonical state, rather than separate uncoordinated engine edits.
- Keep the campaign envelope at **1** if the outer payload shape remains unchanged. If an approved API/payload change moves canonical fields outside the engine save, explicitly bump and migrate that envelope instead.
- Keep SQLite schema at **2** unless the approved engine design requires a new relational table/index. If SQL changes are required, add a transactional additive schema migration to **3**; do not rewrite campaign rows unnecessarily.
- Spells and XP remain unimplemented. Their anticipated next engine-save versions are planning placeholders only and must be reconciled with the approved design before implementation.

### Required migration behavior

`old campaign (campaign v1 / engine save v1)` → validate existing fields → add only approved defaults for new fields → validate the complete new state → restore the original campaign and RNG in a new session.

Old campaigns must remain loadable. Missing optional new state may migrate to explicit empty/default values; malformed, unsupported, or corrupt saves must fail visibly. Never silently reset a campaign, infer state from narration, or discard existing combat state. Tests must cover the actual migration and rollback path before a future phase can pass.

## 4. Approval boundary

Approval is required before changing `ai-dnd/game.py`. The owner should confirm the proposed function scope, quest-definition/trigger source, state/version plan, and which engine work is included. Until that approval:

- Keep Phase 1 visibly **PARTIAL — ENGINE ROUTING REQUIRED**.
- Keep Phase 3 **PARTIAL/BLOCKED — ENGINE CONTRACT REQUIRED** and the quest ledger empty.
- Do not implement Combat V3, Spells V1, or XP/Leveling V1.
- Keep approved item **#38** deferred; its acceptance criteria are not present in the local roadmap material.
- Preserve the protected SHA above and the owner’s campaign data.

**ENGINE CHANGE APPROVAL REQUIRED**