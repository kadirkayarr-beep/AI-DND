# Engine Change Approval Package

**Date:** 28 September 2026  
**Decision requested:** Owner approval before any change to `ai-dnd/game.py`  
**Current gate:** **ENGINE CHANGE APPROVAL REQUIRED**

This is an approval proposal only: no engine change, including #38, Quest Outcomes, Combat V3, Spells V1, or XP/Leveling V1, is implemented here. The protected `game.py` file remains unchanged.

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
- Direct re-verification for this correction: **EXPECTED SHA:** `e971f4cade451828697ab7c49900b634a9cf1a6a1997aa8c733d2a13e0a9c24a`; **ACTUAL SHA:** `e971f4cade451828697ab7c49900b634a9cf1a6a1997aa8c733d2a13e0a9c24a`; **MATCH: YES**.
- The differing SHA in my previous final response was a response typo only. The source file and the approval/checkpoint documents had the correct value; no engine change occurred.
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
- The owner-confirmed **#38** scope and acceptance criteria are included below. It remains approved but deferred until explicit engine approval; do not execute it now or add scope beyond the confirmation.

## 2. Proposed engine change map

These are proposals for approval, not implementation instructions. Function names below refer to the existing frozen engine.

### A. #38 — Remaining Skill Check Routing

**Owner-confirmed scope:** Complete the remaining Phase 1 skill checks after explicit Engine Change Approval.

- **Existing functions/location:** `perform_skill_check()` (`game.py:699`) resolves canonical checks; `execute_intent()` (`game.py:3838`) routes resolved intents; `run_player_turn()` (`game.py:4067`) owns turn processing.
- **Current responsibility:** Python resolves supported checks; the existing structured result is validated and projected by the API. The four routes below are not yet canonically routed.
- **Required routes:** Persuasion, Deception, Acrobatics, and Survival.
- **Why required:** These missing routes are the only confirmed #38 scope. Without engine routing, neither the API, browser, nor Qwen can safely supply their canonical mechanics.
- **Proposed change:** Add explicit Python-owned intent routing for exactly those four skills and pass valid checks through the existing `perform_skill_check()` resolver. Do not add adapter fallbacks, narration parsing, or arbitrary model-result acceptance.
- **New state:** None.
- **Dice/RNG:** Reuse the session RNG and existing resolver for one d20 roll per validated check. Do not add client-side or duplicate rolls.
- **Mutation rules:** Python validates route, skill, ability/proficiency, DC policy, roll, and outcome. Invalid/unsupported checks do not mutate canonical state; only already-approved engine consequences may follow a resolved result.
- **Persistence/save schema:** No new fields or migration are expected; retain engine save v1, campaign envelope v1, and SQLite schema v2.
- **Rollback:** Existing turn rollback must restore state and RNG on invalid results, exceptions, or failed autosave.
- **API impact:** Preserve the existing validated `skill_check_result` contract exactly; client cannot submit DC, die, modifier, or outcome.
- **Frontend impact:** Reuse the current server-authoritative result card. Browser continues to display only the returned canonical result.
- **Legacy campaign/session compatibility:** No save-shape change. Route state and RNG remain scoped to the existing `GameSession`.
- **Deterministic engine tests:** Add one deterministic test for each route, plus unsupported/invalid skill rejection, modifier/DC ownership, no unintended mutation, RNG determinism, rollback, and existing supported-skill regressions.
- **API regression tests:** Verify allowlisting, response serialization, browser-consumed fields, and rejection of client-authored rolls/DC/outcomes.
- **Live-model tests:** After approval, verify intent routing with real `qwen3:8b` using disposable data; assert Python owns the result and Qwen cannot author mechanics.
- **Acceptance requirements:** Obtain explicit Engine Change Approval before editing `game.py`; implement only the four routes; preserve the existing API/UI contract; keep presentation server-authoritative; browser must not generate rolls, DCs, or outcomes and Qwen must not author canonical results; verify with real `qwen3:8b` using disposable data; do not delete or alter owner campaigns, including Cedric; and keep Phase 1 partial until all four routes are implemented and tested.
- **Risk:** Medium. Intent misrouting could trigger the wrong check; explicit skill allowlists and deterministic route tests are required.

### B. Quest Outcomes V1 — canonical definition and lifecycle contract

- **Existing locations/functions:** `GameSession` (`game.py:4232`); `execute_intent()` (`game.py:3838`) and `run_player_turn()` (`game.py:4067`) own action routing; `resolve_attack()` (`game.py:1666`) changes canonical target combat status; `serialize_game_state()` (`game.py:1239`) and `load_game()` (`game.py:1344`) own persistence. There is no quest lifecycle function or structured quest-event producer today.
- **Current responsibility:** The engine owns location, inventory, and NPC/combat state changes, but does not define quests or emit accepted/progressed/completed outcomes. The browser’s current ledger is only a validated empty shape.
- **Why required:** Phase 3 cannot safely populate a quest ledger until the engine identifies canonical quest definitions, explicit acceptance, and typed objective evidence.
- **Definition/source proposal:** V1 definitions come only from a server-owned, owner-approved catalog (proposed new `ai-dnd/quest_catalog.py`) with stable `quest_id` and `objective_id` values and typed offer conditions. The initial catalog remains empty until definitions are approved. Each objective is a typed predicate, not free-form text. Qwen and browser input cannot create or edit definitions. If no approved catalog entry exists, the quest is not offerable.
- **Acceptance proposal:** Add `GameSession.accept_quest(quest_id)` and `GameSession.cancel_quest(quest_id)` as explicit Python commands. Expose them through `POST /api/game/sessions/{session_id}/quests/{quest_id}/accept` and `POST /api/game/sessions/{session_id}/quests/{quest_id}/cancel`; the path ID is validated against the server catalog. Repeated commands return the committed state without emitting duplicate transitions. Do not infer acceptance from conversational wording, and do not accept client-supplied objective predicates or resulting status.
- **Canonical objective evidence:**
  - `visit_location`: emit only after Python changes the canonical location to the required registered location ID.
  - `defeat_entity`: emit only after a canonical combat result changes the referenced entity to the engine’s defeated/unconscious state; match the stable entity ID, not its display name.
  - `acquire_item`: emit only after a validated inventory mutation gains the required canonical item key. If the inventory cannot identify that item unambiguously, keep this objective type disabled until it can.
  - Each event carries a stable source-event ID and turn index. Objective evaluation consumes that event once; no Qwen text matching.
- **Event production/evaluation proposal:** Emit location evidence in the canonical location-change branch of `execute_intent()`/`run_player_turn()`; emit defeat evidence at the `resolve_attack()` mutation that changes canonical entity status; emit item evidence only from a validated inventory-acquisition mutation. Add `GameSession.evaluate_quest_events(events, turn_index)` to match these events to accepted typed objectives after the action resolves and before the turn commits.
- **Completion/failure/cancellation proposal:** Mark complete only when all required typed objectives are satisfied. Support player cancellation only as an explicit validated command. Keep failure disabled unless an independently canonical, deterministic failure trigger exists; do not invent deadlines or infer failure from prose.
- **Proposed state:** Keep immutable `QuestDefinition` records in the server catalog. Derive `quest_offers` from typed catalog conditions and canonical state; offers are not persisted. Persist per-session `QuestState` records containing `quest_id`, status (`accepted`, `completed`, or `cancelled`; `failed` only if a safe trigger is approved), per-objective status/counts, and processed source-event IDs for deduplication. Return typed `QuestOutcome` transitions with event ID, quest ID, transition kind, optional objective ID, source-event ID, and turn index. No separate unbounded transcript-derived quest log.
- **Mutation rules:** Python alone accepts quests and updates objectives. State transitions are idempotent by source-event ID. A failed/rolled-back turn commits neither quest state nor outcome.
- **Dice/RNG:** Lifecycle bookkeeping consumes no RNG. Any action roll that produces evidence remains the existing canonical action roll, exactly once.
- **Persistence/save schema:** Store quest state inside the engine save. Combine the approved quest contract with the proposed engine-save v1→v2 migration for the Quest/Combat approval batch; no SQL table is proposed. Campaign envelope remains v1 if its outer shape is unchanged; SQLite remains schema v2.
- **Rollback:** Restore quest state and source-event deduplication state with the full turn snapshot. Commit the turn, quest state, and API outcome atomically with campaign autosave.
- **API impact:** Add strict allowlisted `quest_offers`, quest-state, and outcome schemas to campaign/session state and successful-turn responses, OpenAPI, and generated clients. Accept/cancel requests carry only the canonical quest ID and command type; API code calls the Python session method and never mutates quest state itself.
- **Frontend impact:** Render only Python-returned offers, accepted state, objective progress, and outcomes. The browser may send an explicit accept/cancel command but cannot author objectives or mark progress. Keep the ledger empty until this contract is implemented.
- **Session isolation:** Quest state and processed event IDs live inside the owning `GameSession` and campaign, never module globals.
- **Legacy compatibility:** Migrate v1 engine saves to an empty quest state while preserving all existing state and RNG; old campaigns load with an empty ledger. Reject corrupt/unsupported state rather than resetting it.
- **Deterministic engine tests:** Catalog validation; explicit acceptance; location, defeat, and supported item evidence; wrong entity/location/item rejection; completion; duplicate-event idempotency; disabled unsupported failure; rollback; session isolation; migration.
- **API tests:** Accept/cancel validation; no client-authored objective/status; allowlisted outcomes; response and campaign-resume consistency; campaign isolation; rollback.
- **Live-model tests:** With disposable data and real `qwen3:8b`, narration such as “quest accepted” or “objective complete” must not mutate state; a separate explicit canonical command/action must be required. No owner campaign data.
- **Risk:** High. The current engine lacks a definition source and typed action-event stream; acceptance and objective trigger rules must be approved before implementation.

### C. Combat V3 — bounded canonical turn foundation

- **Existing functions/location:** `ensure_combat_state()` (`game.py:1413`), `resolve_combat_target()` (`:1625`), `resolve_attack()` (`:1666`), `start_combat()` (`:1778`), `resolve_enemy_attack()` (`:1810`), `end_combat()` (`:1847`), `advance_combat_turn()` (`:1856`), `execute_intent()` (`:3838`), `run_player_turn()` (`:4067`), `serialize_game_state()` (`:1239`), `load_game()` (`:1344`), and `GameSession` (`:4232`).
- **Current responsibility:** Combat V1/V2 resolves a limited single-target exchange, attack/retaliation, and a small combat state. It does not own the requested multi-combatant scheduler with stable participant identities.
- **Why required:** The roadmap requires Python to own whose turn it is, legal targets/actions, defeat state, and exact resumable combat state; the frontend and Qwen cannot safely provide these.
- **Proposed change:** Add a bounded Python-owned scheduler that supports an explicit current turn owner; initiative order and multiple enemies; stable combatant IDs; explicit target IDs; one primary action per actor turn; round progression; validation of legal/illegal actions; canonical defeated/unconscious state; and exact persistence/resume. Keep the primary-action dispatcher typed and extensible so a future approved spell resolver can share the same actor, target, turn, result, persistence, and rollback boundary; no spell rules or fields are included now. Enemy action choice and mechanics remain Python-owned. Ambiguous natural-language targets must be clarified, never guessed.
- **New state:** `CombatState` with active/end status, round, participant records and IDs, initiative order, current actor ID, action availability/usage, explicit target ID, and participant HP/status. Names remain presentation labels only.
- **Mutation rules:** Validate actor turn, action allowance, target identity/legality, and status before mutating. A valid primary action updates the canonical result and scheduler exactly once. Qwen may assist with semantic reference resolution only; Python validates and applies the action, then Qwen may narrate it.
- **Dice/RNG:** Use the session RNG for initiative and canonical attack/damage rolls. Specify stable initiative tie behavior. Persist/restore RNG at turn boundaries; no client or model rolls.
- **Persistence/save schema:** Persist participants, IDs, initiative, round/current actor, action usage, statuses, and the boundary of any pending enemy resolution. This is part of the proposed engine-save v1→v2 migration. SQLite remains v2 unless a new relational structure is approved; campaign envelope remains v1 if unchanged.
- **Rollback:** Illegal actions consume no RNG and mutate no combat state. Any engine, validation, or autosave failure restores the complete pre-turn combat state and RNG. Save the result/state atomically; restart must not skip or double-apply a turn.
- **API impact:** Return allowlisted active/end state, round, current actor, initiative, participants/status, action result, and resulting turn owner. Never expose raw engine objects; update OpenAPI/generated clients.
- **Frontend impact:** Reuse current combat UI and add only initiative order/current-turn highlight, multiple targets, participant HP/status, invalid-action feedback, and target ambiguity handling. Browser does not advance turns or resolve effects.
- **Session isolation:** Scheduler, participant IDs, and RNG belong to the campaign’s `GameSession`; no module-global combat state.
- **Legacy campaign compatibility:** Explicitly migrate v1 saves, preserving campaign state and RNG. For committed Combat V1/V2 state, map the existing player and canonical target to stable participant IDs, preserve HP/status/round/initiative, and set the next actor from the committed turn boundary. If required identity or turn data is missing, fail visibly rather than silently ending or resetting combat. Keep applicable Combat V1/V2 regressions.
- **Deterministic engine tests:** Initiative order/ties; current actor; invalid out-of-turn action; target identity; two enemies and three participants; defeat/unconscious; round rollover/completion; persistence at player/enemy/round boundaries; restart without skipped/doubled turns; rollback; v1 migration; forged/detached participants and targets; session/campaign isolation.
- **API tests:** Public allowlist; target/turn validation; invalid action feedback; saved state and response consistency; resume/restart; forged participant rejection; campaign isolation.
- **Live/browser tests:** Perform real browser combat and real `qwen3:8b` combat using disposable data after approval; prove Python owns turns, target resolution, rolls, enemy actions, and results. Do not use owner campaigns.
- **Explicitly out of scope:** Reactions, bonus actions, opportunity attacks, grid movement, concentration, a full condition system, summons, death saves, legendary actions, encounter balancing, and full D&D 5e combat. None is currently considered strictly necessary for this foundation.
- **Risk:** High. The scheduler changes combat authority and save shape; turn-boundary, migration, rollback, and restart defects could skip/double actions or resume the wrong actor.

### D. Anticipated compatibility requirements for Spells V1

This is an architecture constraint only; it is not a spell-system design or a proposed implementation.

- Keep the Combat V3 primary-action/result boundary extensible so a future approved spell action can share canonical actor, target-ID, legality, persistence, and rollback rules instead of bypassing the scheduler.
- Keep action results typed and server-authoritative, with an extension point for a future Python effect resolver and resource mutation.
- Keep the session RNG and canonical save/load boundary usable by future spell rolls/effects.
- No spell catalogue, class/level rules, slot/resource fields, spell API schema, or frontend spell flow is proposed here.
- **Risk if ignored:** an attack-only hard-coded scheduler could force a second turn system or client-side spell authority later.

### E. Anticipated compatibility requirements for XP / Leveling V1

This is an architecture constraint only; it is not an XP/leveling design or a proposed implementation.

- Preserve stable, typed IDs for canonical events such as entity defeat and quest completion so a later approved reward system can consume them idempotently.
- Keep canonical outcome production separate from narration and browser state; a later reward listener must not award twice on retries/resume.
- Keep `GameSession` save/load extensible for later character progression fields through an explicit migration.
- No XP field, reward table, threshold, level transition, or progression API/UI is proposed here.
- **Risk if ignored:** missing stable outcome IDs would make future rewards vulnerable to duplication or narration-derived grants.

## 3. Save and migration plan

### Current versions

- SQLite schema: **2**.
- Campaign envelope: **1**.
- Engine save: **1**.

### Proposed next version after approval

- If Quest Outcomes and/or Combat V3 are approved in the same change batch, use one explicit engine-save **1 → 2** migration for whichever canonical state changes are approved rather than separate uncoordinated engine edits. #38 alone is response-only and requires no save-version change.
- Keep the campaign envelope at **1** if the outer payload shape remains unchanged. If an approved API/payload change moves canonical fields outside the engine save, explicitly bump and migrate that envelope instead.
- Keep SQLite schema at **2** unless the approved engine design requires a new relational table/index. If SQL changes are required, add a transactional additive schema migration to **3**; do not rewrite campaign rows unnecessarily.
- Spells and XP remain unimplemented. No future save versions or state fields are assigned to them here; define their migrations only when separately scoped and approved.

### Required migration behavior

`old campaign (campaign v1 / engine save v1)` → validate existing fields → add only approved defaults for new fields → validate the complete new state → restore the original campaign and RNG in a new session.

Old campaigns must remain loadable. The Quest state migrates to an explicit empty ledger. A legacy active Combat V1/V2 save maps its canonical player/target, HP/status, round, initiative, and committed next-actor boundary into Combat V3 state; if that mapping cannot be validated, fail visibly instead of discarding or ending the combat. Missing optional state may use approved defaults; malformed, unsupported, or corrupt saves must fail visibly. Never infer state from narration or discard existing combat state. Tests must cover the actual migration and rollback path before a future phase can pass.

## 4. Approval boundary

Approval is required before changing `ai-dnd/game.py`. The owner-confirmed #38 scope is listed below; explicit engine approval is still required before implementing it. For Quest Outcomes and Combat V3, the owner must approve the definition/trigger source, state/version plan, and which proposed work is included. Until that approval:

- Keep Phase 1 visibly **PARTIAL — ENGINE ROUTING REQUIRED**.
- Keep Phase 3 **PARTIAL/BLOCKED — ENGINE CONTRACT REQUIRED** and the quest ledger empty.
- Do not implement Combat V3, Spells V1, or XP/Leveling V1.
- Keep owner-confirmed item **#38** deferred until explicit engine approval; implement only its listed four routes and acceptance criteria afterward.
- Preserve the protected SHA above and the owner’s campaign data.

**ENGINE CHANGE APPROVAL REQUIRED**