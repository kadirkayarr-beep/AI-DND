# AI-DND Project Status / Checkpoint Report

**Updated:** 29 September 2026
**Scope:** Current repository and development status after completion of approved Phases A and B. Phase C is next; the historical protected engine checkpoint remains preserved, with phase hashes recorded below.

## Evidence boundaries

- The report prioritizes current source, current test runs, current artifact configuration, and current Replit deployment metadata over old checkpoint prose.
- The historical pre-engine `ai-dnd/game.py` hash was verified before Phase A. The Phase A post-change hash is recorded in the engine change log below; the historical manifest was not overwritten.
- Phase A validation used disposable sessions and temporary test storage: 109 API tests, 17 deterministic gates, and 7 experience-client tests passed. Both AI-DND web clients passed typecheck and production build. A four-skill authenticated Qwen smoke used one disposable in-memory session; no owner campaign data was accessed.
- Phase B validation: 123 API tests, 17 deterministic gates, 10 experience-client tests, workspace typecheck, API codegen/library typecheck, and both web production builds passed. A post-restart authenticated Qwen API smoke passed six turns with nine model calls (maximum two per turn); the current engine hash is recorded below.
- A current-hash live Qwen smoke is recorded in `ai-dnd/LIVE_QWEN_SMOKE.md`. The completed Combat UX phase also included a real Chromium/Qwen browser run after an API-process restart; its sanitized result is summarized below.
- The earlier `ai-dnd/TESTING_CHECKPOINT.md` and `ai-dnd/CHECKPOINT_AI_PIPELINE_V10.md` are historical records. Do not copy their old source hashes or test totals as current facts.

## 1. Executive summary

AI-DND is a functional, single-user browser-based AI tabletop RPG development prototype. Its feature-complete browser experience is `artifacts/ai-dnd-experience`; it calls a Python FastAPI service, which owns sessions, campaign persistence, canonical state, world metadata, Journal updates, and Combat V1/V2 resolution. Real `qwen3:8b` narration has been verified through the server-side Ollama proxy.

| Area | Current verified status |
|---|---|
| Browser gameplay | Working in the Replit development environment: create/resume, natural-language turns, panels, Journal, and combat presentation |
| Qwen | `qwen3:8b` connected through a server-side Ollama proxy; not called directly by the browser |
| Campaign persistence | SQLite-backed; successful turns save canonical engine state, transcript history, and separate validated combat-result history (limit 50 per campaign) |
| Character creation | Server-authoritative custom or random level-1 characters; browser supplies identity choices, not stats |
| World metadata | Server-owned environment, time-of-day, and weather values are serialized and persisted |
| Journal | Canonical location, NPC, and event tracking works; Python now owns explicit quest acceptance, cancellation, and evidence-based objective outcomes |
| Combat | Python Combat V1/V2 mechanics and structured UX are present; no Combat V3 |
| Public deployment | No active Replit deployment exists as of this report |
| Maturity | Useful local prototype; not production-ready for public or multi-user use |

## Amendment execution status

These are the current gameplay-roadmap statuses; they are separate from the earlier foundation milestones listed below.

| Amended phase | Status | Current boundary |
|---|---|---|
| Phase 1 — Skill Checks V1 (approved Phase A) | **PASS — ENGINE ROUTING COMPLETE** | Persuasion, Deception, Acrobatics, and Survival now route through the existing Python skill-check resolver. The typed API result and existing client card contract are unchanged; model output cannot author mechanics. |
| Phase 2 — Combat Result History Persistence | **PASS** | Validated structured results persist separately from transcript history, are bounded to 50 per campaign, and rehydrate after resume. Failed turns/autosaves do not append results. Combat mechanics and `game.py` were not changed. |
| Phase 3 — Quest Outcomes V1 (approved Phase B) | **PASS** | Python owns quest state and explicit idempotent accept/reject/cancel commands. Canonical location, defeat, and supported-item evidence drives progress; narration cannot mutate quests. Production definitions remain empty pending owner-approved content. |
| Phase 3.5 — Narrative Director V1 (approved Phase C) | **PENDING — NEXT** | Existing bounded, ID-scoped continuity memory remains unchanged. Implement the approved scene-adaptive prose contract after Phase B. |
| Phase 4 — Combat V3 Foundation (approved Phase D) | **PENDING — NOT STARTED** | Combat V2 remains intact. The approved scope is the bounded multi-participant scheduler, not full D&D 5e. |

**Owner approval:** The approval attachment `attached_assets/Pasted--AI-DND-ENGINE-CHANGE-APPROVAL-GRANTED-Resume-the-appro_1790628387000.txt` grants the scoped A–D work. Phases A and B are PASS; continue in order through C and D. Preserve the historical `e971f4cade451828697ab7c49900b634a9cf1a6a1997aa8c733d2a13e0a9c24a` baseline. Phases E–F remain conditional compatibility work; stop for scoped design approval if either needs substantial unapproved architecture.

## 2. Architecture

```text
React / Vite browser
        ↓
AI-DND FastAPI (`ai-dnd/api/main.py`)
        ↓
SessionManager + CampaignStore + Journal / metadata adapters
        ↓
per-session Python game state (`ai-dnd/game.py`)
        ↕
server-side Ollama adapter → qwen3:8b
```

**Authority rule:** **Python decides reality. Qwen understands intent and describes reality. The frontend presents reality.**

- **Frontend:** `artifacts/ai-dnd-experience` owns the opening, campaign library, character-creation flow, adventure workspace, responsive panels, transcript presentation, and display of server-returned state/results. It sends player text and selected campaign/character inputs; it does not own canonical HP, AC, inventory, metadata, Journal, or combat state.
- **FastAPI:** `ai-dnd/api/main.py` validates requests, exposes health/session/campaign/turn routes, checks model availability and call limits, serializes safe public state, coordinates turn rollback, and returns structured action results.
- **Session/campaign layer:** `SessionManager` creates and owns in-memory runtime sessions. `CampaignStore` stores versioned canonical snapshots and player/narration history in SQLite.
- **Game engine:** `ai-dnd/game.py` owns the authoritative game rules, action/state mutations, random decisions, Combat V1/V2, and Quest Outcomes V1. Continue only within the owner-approved A–D phases.
- **Qwen:** the model helps interpret player intent and produce narration. Its output is bounded and checked; it does not directly write canonical game state.
- **Other services:** `artifacts/api-server` is a separate Express health/API scaffold and is not the AI-DND game engine or campaign store. Root `main.py` launches the terminal game, not FastAPI. Do not confuse either with `ai-dnd/api/main.py`.
- **Development workflow caution:** the workspace has both a root FastAPI workflow and an artifact-owned FastAPI workflow. Runtime session registries are process-local. Route traffic to one canonical instance; adding another API process without coordination can split session state.

## 3. Historical engine checkpoint and current phase hashes

- **Historical protected source:** the pre-engine `ai-dnd/game.py` baseline is `e971f4cade451828697ab7c49900b634a9cf1a6a1997aa8c733d2a13e0a9c24a`.
- **Current post-Phase-B SHA-256:** `b20c1635cbf81905185a784c8baebcb90dae41df646b6733a9ad2715226427c0`.
- **Historical manifest:** `ai-dnd/CHECKPOINT_CURRENT.sha256` remains unchanged by design; it records the protected pre-engine baseline. Record phase hashes here and create the next protected major checkpoint only after Phase D.
- Phase A and B changes are within the owner-approved roadmap. The older `CHECKPOINT_V2.sha256`, `TESTING_CHECKPOINT.md`, and `CHECKPOINT_AI_PIPELINE_V10.md` refer to earlier source/test snapshots and remain historical evidence.
- The older `CHECKPOINT_V2.sha256`, `TESTING_CHECKPOINT.md`, and `CHECKPOINT_AI_PIPELINE_V10.md` refer to earlier source/test snapshots. They are historical evidence, not the current engine hash.
- Implement only the next owner-approved phase in order. Do not start Combat V3 before Phase C passes or expand into unapproved Phases E–F.

## 4. Earlier foundation milestones (separate from the amended gameplay phases)

| Phase | Goal and verified implementation | Deliberately not included | Current validation/status |
|---|---|---|---|
| 1. FastAPI / browser integration | Browser actions reach the Python API and are processed by server-managed sessions. Health, session, campaign, state, and turn operations are exposed. | Browser-to-Ollama calls; client-authored canonical state; public multi-user service. | API tests, live model smoke, and actual browser turns; **complete**. |
| 2. Full frontend integration | The `ai-dnd-experience` artifact provides the campaign browser, creation/reveal flow, adventure workspace, character/world/NPC/Journal/Combat views, and mobile drawers. | A full native mobile app, portrait generation, public deployment, and unsupported gameplay systems. | Frontend panel tests, workspace typecheck/build, mobile browser verification; **complete for the current web experience**. |
| 3. Persistent Campaign V1 | SQLite stores campaign snapshots, RNG, metadata, Journal, NPC memory within engine state, and player/narration history. Campaigns resume after a FastAPI restart. | Multi-instance coordination, account ownership, user-facing rollback to an old save, general schema-migration framework, campaign deletion API. | Persistence/API tests and restart/resume smoke; **complete within the single-instance boundary**. |
| 4. Canonical Character Creation V1 | Server validates custom/rand mode, chooses canonical race/class/name as applicable, generates stats/proficiencies, and computes starting character values. | Manual stat assignment, gear selection, rerolls, portraits, leveling, subclasses, feats, and spell selection. | Character/API tests; **complete for level-1 creation**. |
| 5. World Metadata V1 | Server derives/validates canonical environment, time-of-day, and weather metadata; state and themes survive resume. | Real clock, calendar, seasons, or automatic weather/time progression. | `test_world_metadata.py`, campaign serialization tests, theme integration; **complete for metadata V1**. |
| 6. Journal / Quest V1 | Journal records canonical discoveries, known NPCs, notable events, quest offers, and Python-owned quest state. | Unapproved production quest content and outcomes inferred from narration or browser state. | Quest Outcomes V1 **PASS**; production catalog intentionally empty until owner-approved definitions are added. |
| 7. Combat UX Polish | Combat V1/V2 state is rendered from Python’s canonical state; the API returns allowlisted structured results; desktop and mobile Combat UI display rolls, HP, AC, initiative, and retaliation. | Combat V3 or new mechanics. | UX scope complete; Phase 2 now persists validated result history across campaign resume. |

## 5. Current gameplay capabilities

Players can currently:

- Create a campaign and a custom or random level-1 character, then resume a saved campaign by its campaign ID.
- Send natural-language actions to the server and receive Qwen-assisted narration grounded in Python-owned state.
- Move among engine-supported locations, discover locations, inspect the current world, and interact with supported doors/features.
- Encounter and converse with NPCs; NPC facts/memory live in the engine state and persist with the campaign.
- View the character, inventory, world, NPCs, Journal, and combat state in the browser.
- Use limited Python skill checks for supported interactions such as some locked-door, Stealth, or Investigation cases. These are not yet a general, first-class skill-check API/UI system.
- Start/continue/end supported single-target combat, make an attack, resolve canonical attack rolls/damage, receive an enemy response, and persist the active combat state through campaign save/resume.
- See environment/time/weather-driven visual themes when canonical metadata is available.

Availability depends on the current engine state and supported intent/action rules. This is not a full D&D rules engine: arbitrary narrative actions do not automatically become canonical mechanics.

## 6. Character system

**Canonical creation inputs and outputs**

- Nine engine-defined races: Human, Elf, Dwarf, Halfling, Gnome, Half-Elf, Half-Orc, Tiefling, Dragonborn.
- Twelve engine-defined classes: Barbarian, Bard, Cleric, Druid, Fighter, Monk, Paladin, Ranger, Rogue, Sorcerer, Warlock, Wizard.
- Custom mode sends name/race/class; random mode lets the server choose a name/race/class. Race/class options come from the Python engine.
- Python rolls six ability scores using 4d6-drop-lowest and assigns them, generates class-appropriate skill proficiencies (Rogue gets four; other supported classes get two), and computes the level-1 character’s values including HP, AC, and proficiency bonus (+2).
- Starting inventory is engine-owned; the creation form does not let the player choose equipment. The frontend displays inventory but does not author it.

**Not supported as creation/progression features:** manual ability-score allocation, user-triggered rerolls, equipment choice, portrait generation, level-up, XP progression, subclasses, feats, and spell selection. Class/race constants or descriptions in `game.py` should not be mistaken for a complete implementation of every D&D feature.

## 7. Campaign persistence

| Concern | Current behavior |
|---|---|
| Storage | SQLite at `ai-dnd/saves/campaigns.sqlite3` by default; `AI_DND_CAMPAIGN_DB` can override the path. |
| IDs | Campaign IDs and runtime session IDs are separate UUID4 values. Campaign ID persists; runtime sessions live in memory. Resume after process loss restores the campaign into a new session ID. |
| Save frequency | New campaign gets an initial save. Successful turns autosave canonical state/history. An explicit save route/UI action also exists. |
| Transaction/failure behavior | SQLite WAL and transactional writes. A failed model/engine/validation/Journal/autosave turn restores the in-memory state snapshot and does not commit a partial campaign update. |
| RNG | Random state is serialized/restored and covered by persistence tests. |
| Turn history | Server history stores player message and narration. Validated structured combat results are stored separately from transcript history, with stable server IDs and a per-campaign limit of 50. The browser rehydrates and deduplicates these results; its local display transcript is not canonical. |
| NPC memory | Stored inside canonical engine/world save, not in a separate vector/database service. |
| Combat | Active engine combat state and validated structured result history persist. Combat mechanics remain V1/V2; this is not Combat V3. |
| World metadata / Journal | Included in the versioned campaign payload and restored. |
| Versioning/migrations | SQLite schema is version 2; campaign envelope is version 1; engine save is version 1. Schema v2 adds a separate combat-history table and migrates old databases additively. Reads validate versions and reject corrupt/unsupported saves. There is no general migration framework for arbitrary future engine-save versions. |
| Access/ownership | Single-user development behavior. There is no authentication or campaign owner boundary; opaque UUIDs are not authorization. No campaign-delete endpoint or user-visible “roll back to prior save” endpoint exists. |

At report time, the development SQLite database contains one campaign row with unverified provenance. The known `CombatSmoke` row created for the browser test and its history were removed; the other row was preserved rather than risk deleting user data. Do not treat the database as empty or delete the remaining row without owner confirmation.

## 8. World model / metadata

- Canonical environment categories: `tavern`, `forest`, `city`, `village`, `road`, `wilderness`, `dungeon`, `cave`, `castle`, `temple`, `ruins`; `unknown` is the neutral fallback.
- Canonical time values: `dawn`, `day`, `evening`, `night`.
- Canonical weather values: `clear`, `rain`, `fog`, `snow`, `storm`; `unknown` is the fallback.
- Environment is derived on the server from the current engine location’s known identity/type/name and aliases, with a neutral fallback. Missing time/weather defaults to `day`/`clear`.
- Values are validated and persisted; public state serializes the canonical values. The API supplies the metadata as context to Qwen and retains the server snapshot around the turn. Qwen does not author it.
- No real-world clock is used. No full calendar, season cycle, or verified automatic time/weather progression exists.
- `EnvironmentThemeProvider` consumes canonical values for presentation. The UI supports the environment families, four times of day, and weather overlays; it does not turn visual effects into game-state authority. Unknown/missing data uses a neutral/fallback appearance.

## 9. Journal / quest system

**Journal V1 works for:**

- Discovered locations and visit details.
- Known/encountered NPCs, sightings, and location context.
- A time-ordered notable-event list derived from canonical state/action changes, including supported exploration, NPC, inventory, and combat events.
- Persistence, campaign isolation, and resume continuity.

Python now owns quest offers, accepted/cancelled/completed states, objective progress, and structured outcomes. Accept/reject/cancel are explicit idempotent commands; only canonical location, defeat, or validated supported-item evidence advances objectives. Narration and player prose never create or mutate quest state. The browser renders returned state and submits quest IDs only.

Production quest definitions remain empty until owner-approved content is supplied. Tests may inject server-owned definitions. Engine saves migrate from v1 to v2 while preserving existing state, RNG, and held world references; the campaign envelope and SQLite schema remain unchanged.

## 10. Combat system

### Current Combat V1/V2 mechanics

- Python validates an attack target against a canonical NPC and current location; detached/forged target data is not authority.
- Supported single-target combat has active state, initiative metadata, rounds, attack d20, AC comparison, damage, HP/status updates, and one enemy response as part of the exchange.
- Natural 1 is an automatic miss; natural 20 is a critical hit with critical damage dice.
- Enemy hit/miss/natural 1/natural 20, player/NPC knockout, round progression, and incompatible/forged targets are covered by deterministic tests.
- Combat state is reset/ended by the current engine’s supported rules. “Unconscious” is implemented; death saves and full death-state rules are not.
- These rules are Combat V1/V2 only. No V3 mechanics were introduced.

### Combat UX presentation

- `combat_result` is a structured, allowlisted API result for supported attack actions; it includes returned roll/modifier/total/target AC/damage/HP/status information and a nested enemy response where applicable.
- The panel renders idle/active/ended state, canonical player and target HP/AC/status, round, initiative order, attack result cards, and retaliation. It retains at most eight result entries in current frontend memory.
- Desktop uses the workspace Combat tab; mobile provides a world drawer and active-combat entry point. A real 390×844 browser run verified the mobile drawer and result card.
- The combat state survives save/restart/resume. The prior structured roll cards do not; see Known Issues and Backlog.

### Not yet implemented: Combat V3

No general action economy, spell actions, reactions, multi-enemy turn scheduler, death saves, advanced conditions, encounter balancing, or full combat event-history/replay system is present. Do not describe the presentation work as Combat V3.

## 11. Frontend / design status

- **Opening:** branded story-first landing page with new-adventure and continue actions, engine-health feedback, and campaign-library navigation.
- **Character creation/reveal:** custom and random modes, engine-provided options, validation/loading/error states, read-only canonical character reveal. Portrait area is intentionally empty.
- **Adventure workspace:** character/inventory panel; story transcript and natural-language composer; world, NPC, Journal, and Combat tabs; current location and HP summary; save/new controls; active-combat quick entry.
- **World/NPC/Journal:** render server state and canonical Journal collections. The browser does not write those collections.
- **Responsive behavior:** desktop uses multiple panels. At tablet/mobile widths, the story becomes primary, desktop side panels hide, and character/world data are opened through accessible drawers with close/backdrop/Escape/focus behavior. Combat is available from the mobile combat affordance/drawer.
- **Environment presentation:** reusable CSS themes cover 11 known environments, four times of day, and supported weather overlays. Reduced-motion preferences disable combat-result animation.
- **Transcript boundary:** the transcript/localStorage and combat-card list are presentation caches, not canonical records. The server campaign snapshot/history is authoritative.

## 12. Qwen / Ollama integration

- **Model:** server-pinned `qwen3:8b`; unsupported model names are rejected.
- **Connection:** Python uses the configured Ollama host and a server-only bearer token from environment secrets. Browser requests contain player text, not Ollama credentials.
- **Call behavior:** model availability is preflight-checked. Per-turn calls are capped at two; exceeding the cap fails/rolls back instead of silently allowing unlimited retries. Some deterministic actions/queries require zero model calls.
- **Narrator safety:** model output is sanitized/checked against canonical state and may be replaced by a safe narration. Model failure does not authorize state changes.
- **Intent and NPC memory:** Qwen provides intent/narration assistance using canonical context; the engine grounds supported action/state transitions and NPC memory remains in the game save.
- **Live evidence:** `ai-dnd/LIVE_QWEN_SMOKE.md` records a 28 September 2026 smoke against the current source hash: 11 turns, 17 model calls, maximum two calls per turn, one narration replacement, and no recorded state-routing/contradiction failures in that run. The completed browser test also produced actual `qwen3:8b` calls after an API restart; the final post-resume turn logged two model calls.
- **Limit:** this is a development proxy/tunnel arrangement and depends on server environment configuration and a reachable Ollama endpoint. It is not a production-grade hosted model service.

## 13. API status

The current AI-DND API is FastAPI in `ai-dnd/api/main.py`. It exposes `/api/game/...` routes and legacy `/api/...` aliases for the game operations below.

| Capability | Current route family |
|---|---|
| Health/model readiness | `GET /api/game/health`, `GET /api/health` |
| Character options | `GET /api/game/character-options`, `GET /api/character-options` |
| Create runtime session | `POST /api/game/sessions`, `POST /api/sessions` |
| Session state | `GET /api/game/sessions/{session_id}/state`, `GET /api/sessions/{session_id}/state` |
| Process turn | `POST /api/game/sessions/{session_id}/turn`, `POST /api/sessions/{session_id}/turn` |
| Campaign list/create | `GET` / `POST /api/game/campaigns` and `GET` / `POST /api/campaigns` |
| Campaign detail | `GET /api/game/campaigns/{campaign_id}`, `GET /api/campaigns/{campaign_id}` |
| Resume | `POST /api/game/campaigns/{campaign_id}/resume`, `POST /api/campaigns/{campaign_id}/resume` |
| Explicit save | `POST /api/game/campaigns/{campaign_id}/save`, `POST /api/campaigns/{campaign_id}/save` |

Turn input is natural-language `message` only (maximum 4,000 characters); callers cannot submit authoritative state fields. Journal and combat state are included in campaign/session state rather than separate client-write APIs. No campaign DELETE or arbitrary save rollback endpoint exists.

`lib/api-spec/openapi.yaml` and generated API client/codegen exist and the combat response contract was updated for structured results. Contract parity still needs attention: the spec’s health/path naming does not exactly match the current FastAPI aliases (for example, `/healthz` is documented but not exposed by this FastAPI app). Use runtime FastAPI routes as the source of truth until the spec is aligned.

## 14. Test / validation status

| Check | Current result |
|---|---|
| API unittest suite | **108 passed, 0 failed.** Ran `python -m unittest discover -s api/tests` from `ai-dnd/`. Campaign persistence tests use isolated test databases; logged engine/storage failures are expected negative-path cases. |
| Deterministic engine gates | **17/17 gates passed** with a temporary DB override via `python ai-dnd/run_tests.py`. Includes semantic, session, persistence, combat, regression, migration, query, door, and NPC-query checks. |
| Semantic/query/narrator checks | 87 semantic, 24 query-grounding, 18 narrator-safety checks passed inside the deterministic runner. |
| Combat V1 | 10 scenarios passed, including hit/miss, natural 1/20, knockout, target-location, and forged-target cases. |
| Combat V2 turn pipeline | 15 tests passed; the compatibility entry point runs the same 15 again and should not be counted as 15 additional unique cases. |
| Authoritative Combat V2 | **25 tests passed** (A–Y); old `TESTING_CHECKPOINT.md` count of 24 is stale. |
| Regression | 22 passed, 0 failed. The offline “Ollama unavailable” case intentionally verifies safe fallback; it is not live-model evidence. |
| Frontend Combat panel | **6 passed, 0 failed** via `pnpm --filter @workspace/ai-dnd-experience test`. |
| Workspace/frontend typecheck | **Passed** for generated workspace libraries and `ai-dnd-experience`. |
| Production build | **Passed** via `PORT=5000 BASE_PATH=/ai-dnd-experience pnpm --filter @workspace/ai-dnd-experience run build`. Vite emitted the non-blocking Tooltip sourcemap warning; 1,780 modules transformed. |
| Phase 1 partial verification | Existing supported structured skill-result/allowlist/rollback API tests and deterministic skill regressions passed within the suites above. The four missing routes remain intentionally unsupported; this does not make Phase 1 a PASS. The recorded current-hash live-Qwen smoke is general pipeline evidence and does not exercise skill routing. |
| Live restart/resume smoke | Passed against a disposable temporary campaign database. One structured combat-history result restored after API restart; the quest ledger remained empty. This smoke is not evidence for the four missing skill routes. |
| Source/checkpoint integrity | `game.py` hash matches `CHECKPOINT_CURRENT.sha256` at `e971f4cade451828697ab7c49900b634a9cf1a6a1997aa8c733d2a13e0a9c24a`; `git diff --check` passed. |

No coverage percentage/report is configured. Test totals above are current verification totals; older checkpoint counts should not be substituted.

## 15. Known issues

| Issue | Severity / impact | Workaround | Recommended fix / status |
|---|---|---|---|
| Combat results from before SQLite schema v2 cannot be recovered because they were never stored. | Low; historical result cards remain absent on old campaigns. | New results persist after the migration; current canonical combat state remains available. | Expected and documented. Old history starts empty; do not backfill from narration. |
| OpenAPI/runtime route naming is not fully aligned. | Low–medium; generated clients or external callers can target a stale path. | Use actual FastAPI routes above. | Align OpenAPI paths and regenerate the client; add a route parity check. |
| A prior smoke on an older source hash recorded a conservative narrator-name guard false positive (`Gizli Yol`). The current-hash recorded smoke reports no state-routing/contradiction failures, but does not establish that every false-positive case is gone. | Low; a valid narration may be replaced by safe fallback text. | Retry or use clearer player wording; game state remains Python-owned. | Add a focused regression case and verify against the current source before claiming fixed. |
| Last production build emitted a Tooltip sourcemap warning. | Low; build succeeds and browser rendering is unaffected. | None required for local use. | Inspect the source-map origin when convenient; do not treat this warning as a build failure. |
| Natural-language travel/target references can need explicit wording when names are ambiguous. | Low; an action may be treated as narrative rather than a canonical move. | Name the complete location/NPC and intended action. | Keep deterministic Turkish matching exact/entity-grounded; add phrasing tests before changing intent rules. |
| One development campaign row remains with unverified provenance after the end-to-end test cleanup. | Operational/data-safety caution, not a game-rule defect. | Preserve it; do not delete based on its name alone. | Ask the owner to identify it before any cleanup. |

## 16. Known limitations

- Single-user, no authentication, accounts, authorization, or campaign ownership.
- No multiplayer/party collaboration, campaign sharing, or campaign-level roles.
- No distributed session coordination or supported multi-instance deployment.
- No full quest lifecycle; the quest array is a validated ledger shape only.
- Skill Checks V1 has a typed allowlisted result, generated client, and browser card for supported canonical routes. Persuasion, Deception, Acrobatics, and Survival still require engine routing.
- Combat is a limited single-target exchange, not full tabletop action economy or Combat V3.
- No death saves, full conditions system, spell actions/selection, rests, XP, or leveling.
- No equipment selection/stat system, shops/economy, companion system, factions/reputation, or complete calendar/seasons.
- No generated portraits.
- Basic engine-supported location travel exists; this is not a full route planner, living world simulation, or procedural campaign system.
- No public deployment is active.

## 17. Technical debt

| Debt | Risk | Urgency / approach |
|---|---|---|
| Much canonical behavior and legacy compatibility remains concentrated in frozen `game.py`. | Future changes can cause broad regressions; large refactors could violate held-reference/session compatibility. | High caution, not an invitation to refactor now. Add new behavior behind small, tested API/session boundaries unless the owner approves an engine migration. |
| Campaign/database/payload formats are versioned but have no general migration chain. | Future schema evolution can strand or reject old saves. | Medium. Define an explicit migration/version policy before changing payload formats. |
| Pre-v2 combat results were not durably recorded. | Older campaigns cannot display historical result cards from before the additive migration. | Low. Expected; retain empty history for old campaigns and never reconstruct from narration. |
| OpenAPI contract and some legacy FastAPI aliases have drift. | Generated client and external integrations can disagree with runtime behavior. | Medium. Current campaign/combat schemas were regenerated; retain route-parity checks and resolve the remaining legacy naming mismatch separately. |
| Session registry is process-local while more than one development FastAPI workflow is configured. | Requests split across instances can produce missing session IDs even though SQLite campaign data exists. | Medium before deployment. Route one owner in dev; design shared runtime coordination before scaling. |
| Several layers validate/serialize engine saves, campaign envelopes, and public API state. | A field can be accepted/persisted but omitted or exposed inconsistently. | Medium. Preserve boundary-specific schemas and add contract tests instead of merging authority layers casually. |
| Ollama tunnel/proxy and model behavior are external development dependencies. | Availability and narration quality vary; no public-service reliability guarantee. | High before public use. Add production model operations, timeouts/observability, and fallback policy first. |

## 18. Backlog / deferred items

| Item | State of implementation | Why / prerequisite |
|---|---|---|
| Canonical quest outcomes | Quest Outcomes V1 is implemented and verified; production quest definitions remain empty. | Add only owner-approved server-owned quest content. Never infer from narration. |
| Combat result history persistence | Complete for validated post-migration results; bounded to 50 per campaign and restored on resume. | Pre-v2 results cannot be recovered; no narration reconstruction. |
| Canonical Skill Checks V1 | **PARTIAL — ENGINE ROUTING REQUIRED.** Safe typed result/API/UI work remains in place. | Add explicit Python routing for Persuasion, Deception, Acrobatics, and Survival only after approval. |
| OpenAPI route parity | Partial/drift exists. | Align actual FastAPI routes and generated client; test contract. |
| Authentication and campaign ownership | Not implemented. | Required before exposing user campaigns to public/untrusted users. |
| Multi-instance/session coordination | Not implemented. | Requires a single runtime owner or shared session/locking design; SQLite alone does not share Python session objects. |
| Public deployment and operational hardening | No deployment exists. | Authentication, persistence ownership/backups, rate limiting, model operations, observability, and security review first. |
| Portrait generation | Not implemented. | Optional character presentation feature; separate from canonical identity. |
| Rich calendar/time progression | Not implemented. | Requires an explicit canonical clock, turn advancement, persistence, and tests. |
| Spells, leveling/XP, advanced combat, economy, factions, companions, procedural content | Not implemented. | Future gameplay systems; each needs an explicit canonical state model and dependency order. |

## 19. Current approval boundary

Approved roadmap status:

1. Phase A — Skill Checks V1: **PASS**.
2. Phase B — Quest Outcomes V1: **PASS**.
3. Phase C — Narrative Director V1: **NEXT**, already owner-approved; existing prompt behavior remains unchanged until this phase is implemented.
4. Phase D — Combat V3 Foundation: **PENDING Phase C**.
5. Phases E–F remain compatibility-only and require scoped approval for substantial new architecture.

Public-release hardening remains separate: authentication/ownership, rate limiting, backup/recovery, single/multi-instance design, observability, security review, and model operations are still required before public use.

## 20. Canonical Skill Checks V1 current status

**PASS — ENGINE ROUTING COMPLETE.** The four remaining approved routes use the existing Python resolver.

- **Retained safe work:** validated structured `skill_check_result`, allowlisted API/OpenAPI contract, generated client, browser result card, rollback validation, currently supported canonical skill routes, and existing API/regression/typecheck/live-Qwen evidence.
- **Engine routes:** Persuasion, Deception, Acrobatics, and Survival use the existing Python skill-check resolver.
- **Authority constraint:** Do not fake mechanics through API adapters, frontend logic, narration parsing, or arbitrary Qwen output.
- **Verification:** Phase A passed its API, deterministic, UI, typecheck/build, and authenticated live-model gates; Phase B retains these regressions.

## 21. Future gameplay systems

These are possibilities, not current capabilities:

- **Core rules:** broader skill checks, saving throws, spells, conditions, rests, XP/leveling, equipment stats, and action economy.
- **World:** advanced quest content beyond Quest Outcomes V1, factions, reputation, economy/shops, richer route/travel planning, calendar, seasons, and weather progression.
- **Characters:** subclasses, feats, backgrounds, portraits, companions, and party management.
- **Content:** procedural dungeons, structured encounters, loot tables, handcrafted campaign packs, and lore codex.
- **Product:** accounts, cloud saves, multiplayer, campaign sharing, DM mode, and public hosting.

## 22. Security / authority review

| State or boundary | Current trust boundary |
|---|---|
| HP / AC / inventory | Server engine owns values. Turn input does not accept authoritative stat/inventory fields. |
| Combat state / dice | Python validates target and resolves rolls/damage/state. Browser displays structured results; it cannot submit the result. |
| World metadata | Server derives, validates, snapshots, and serializes it. Qwen receives context but does not write metadata. |
| Journal / quests | Python derives progress from canonical evidence. The browser submits explicit quest IDs and renders validated returned state; it cannot write quest state or complete quests through narration. |
| Campaign save | Explicit save accepts a campaign path ID, not a client state snapshot. |
| Ollama credentials | Read from server environment; not returned in API responses or sent to the browser. |
| Campaign access | **Not protected by user auth.** UUIDs are identifiers, not access control. A caller who can reach the API may list/read/resume/save campaigns. |

The trust assumption is a single-owner development workspace with access controlled outside this application. Do not expose the current API to untrusted public users without authentication, ownership authorization, rate limiting, and a security review.

## 23. Production readiness

**Not production-ready.** Replit’s deployment metadata service was queried successfully and reports no active deployment.

Ready for local development/demo:

- Browser, FastAPI, SQLite campaign flow, current Qwen proxy, and core tests work in this workspace.
- The frontend production build succeeds when the artifact’s required `PORT` and `BASE_PATH` environment values are supplied.

Not ready for public users:

- No authentication, authorization, or campaign ownership.
- Local SQLite and process-local runtime sessions are not a multi-instance/cloud-save strategy; backup/restore and ownership are not configured.
- No verified public deployment, rate-limit policy, operational model SLA, or complete production observability/alerting.
- Replit Ollama proxy/tunnel development configuration is not an independent production inference service.
- Campaign privacy, model safety, abuse controls, backup/restore, and deployment security need review before public exposure.

## 24. Protected invariants

1. Continue only within the owner-approved A–D roadmap, in order; report the engine SHA at each completed phase.
2. Python owns canonical state and mechanical outcomes.
3. Qwen may interpret/narrate; it never directly owns HP, AC, inventory, combat, world metadata, or Journal/quest reality.
4. The frontend presents canonical values and must not calculate authoritative dice/results or persist canonical state locally.
5. Keep session ownership explicit; do not restore shared-world aliasing or let one campaign mutate another.
6. Keep campaign saves validated, versioned, transactional, and rollback-safe.
7. Keep Turkish matching deterministic and entity-grounded; do not use substring matches or rewrite the player’s original model input.
8. Do not infer quest acceptance, progress, or completion from narration; preserve server-owned quest definitions and canonical evidence.
9. Do not add Combat V3 mechanics under a UX-only change.
10. Do not expose Ollama secrets or raw internal engine/model data in browser responses.
11. Do not add a second API process or route owner without accounting for process-local session registries.
12. Run the regression suite and report current source hash before calling a future phase complete.

## 25. Current roadmap checkpoint

**APPROVED ENGINE ROADMAP STATUS**

- Phase A — remaining Skill Checks V1 routes: **PASS**.
- Phase B — Quest Outcomes V1: **PASS**.
- Phase C — Narrative Director rich-prose contract: **NEXT; approved**.
- Phase D — bounded Combat V3 foundation: **PENDING Phase C**.
- Phases E–F — Spells and XP/Leveling: compatibility boundaries only; stop for scoped design approval if substantial new architecture is needed.

**PHASE A HASH AND VERIFICATION**

- Historical pre-engine SHA-256, preserved: `e971f4cade451828697ab7c49900b634a9cf1a6a1997aa8c733d2a13e0a9c24a`.
- Phase A pre-change `game.py` SHA-256: `e971f4cade451828697ab7c49900b634a9cf1a6a1997aa8c733d2a13e0a9c24a`.
- Phase A post-change `game.py` SHA-256: `273cd96fffc26f0bd17eab3ec458f7481464422e9d784269f6b2cd1993744480`.
- Phase A gate: **PASS**. 109 API tests, all deterministic regressions, 7 experience-client tests, both web artifact typechecks/builds, and authenticated disposable Qwen classification/resolution for all four skills passed.
- The real-Qwen Phase A smoke used four parser calls in a new in-memory session. The pre-existing `CHECKPOINT_CURRENT.sha256` historical manifest was not overwritten.

**PHASE B HASH AND VERIFICATION**

- Phase B pre-change `game.py` SHA-256: `273cd96fffc26f0bd17eab3ec458f7481464422e9d784269f6b2cd1993744480`.
- Phase B post-change `game.py` SHA-256: `b20c1635cbf81905185a784c8baebcb90dae41df646b6733a9ad2715226427c0`.
- Phase B gate: **PASS**. 123 API tests, 17 deterministic gates, 10 experience-client tests, API codegen/library typecheck, workspace typecheck, and both web artifact production builds passed.
- Post-restart authenticated Qwen API smoke: **PASS**, 6 turns, 9 model calls, maximum 2 per turn, zero reported issues. The shared-proxy API service logged real `qwen3:8b` calls; the campaign preview loaded with no browser errors.
- The smoke used a disposable in-memory session and did not create or alter campaigns. Quest lifecycle authority and persistence/isolation/rollback/narration behavior are covered by deterministic and API tests.
- The historical `CHECKPOINT_CURRENT.sha256` remains unchanged. The next protected major checkpoint is due only after Phase D.

**SEPARATE BACKLOG**

- API route naming, authentication/ownership, and multi-instance coordination.
- Public deployment hardening, backups, model operations, and security review.
- Portraits, advanced world systems, companions, multiplayer, and campaign sharing.

### Handoff summary (12 lines)

1. AI-DND is a single-user Replit development prototype; no active public deployment exists.
2. Main browser product: `artifacts/ai-dnd-experience`; game API: `ai-dnd/api/main.py`.
3. Current post-Phase-B `ai-dnd/game.py` SHA-256 is `b20c1635cbf81905185a784c8baebcb90dae41df646b6733a9ad2715226427c0`; historical pre-engine SHA `e971f4cade451828697ab7c49900b634a9cf1a6a1997aa8c733d2a13e0a9c24a` remains preserved.
4. Python owns canonical state; Qwen `qwen3:8b` interprets/narrates through a server-side Ollama proxy.
5. Campaigns persist in SQLite; campaign IDs survive restart, runtime session IDs do not.
6. Successful turns autosave state, RNG, metadata, Journal, NPC memory, player/narration history, and separate bounded combat-result history.
7. Journal tracks canonical locations/NPCs/events and Python-owned quest outcomes; the production quest catalog remains empty pending owner-approved definitions.
8. Combat V1/V2 is authoritative and resumable; Combat V3 is not implemented.
9. Validated combat-result cards are restored after campaign resume; pre-v2 results cannot be recovered.
10. Phase B validation: 123 API tests, 17 deterministic gates, 10 experience-client tests, generated clients, workspace typecheck, both web builds, and post-restart authenticated Qwen smoke passed.
11. The dev DB retains one campaign row of unverified provenance; preserve it pending owner confirmation.
12. Before public use, add auth/ownership, rate limits, backup/recovery, model operations, and a security review.

## A. Current health

**Local-development health: green.** **Feature completeness: prototype / partial rules system.** **Public production health: not ready.** Current tests, typecheck, build, engine hash, and real Qwen/browser evidence are satisfactory for the completed local phases; authentication, deployment, multi-instance persistence, and unfinished rules systems remain material gaps.

## B. Top 5 risks

1. Unauthenticated campaign list/read/resume/save routes expose all campaigns to anyone who can reach the API.
2. Runtime sessions are process-local; multiple API instances can split or lose session routing.
3. Local SQLite has no configured production backup/ownership strategy or general schema migration framework.
4. Qwen/Ollama availability and narration quality depend on the development proxy; model operations and abuse/rate controls are not production-grade.
5. Phase C and D remain unfinished; Phases E–F require scoped approval if they need substantial new architecture.

## C. Top 5 next actions

1. Continue with approved Phase C — Narrative Director V1; preserve Python authority and existing compatibility constraints.
2. Complete approved Phase D only after Phase C passes, then create the required protected major engine checkpoint.
3. Keep production quest definitions empty until owner-approved content is available.
4. Preserve the historical `CHECKPOINT_CURRENT.sha256`; do not start Phases E–F without scoped approval.
5. Separately resolve API route naming and public-use security/operations before any public release.

## D. Current next step

**Proceed to approved Phase C — Narrative Director V1.** Phase B passed all local and live gates. Do not begin Phase D until Phase C passes, and do not create the new protected major checkpoint until Phase D is complete.

## E. Do not touch / protected areas

- Only implement the next explicitly approved A–D phase in order; do not expand into Phases E–F without scoped approval.
- Preserve the historical `CHECKPOINT_CURRENT.sha256`; the new protected major checkpoint is due only after Phase D.
- Do not use historical V2/V10 hashes or test counts as the current checkpoint.
- Do not let Qwen or the browser author canonical mechanics, campaign saves, Journal state, or quest completion.
- Do not infer quest progress from narration.
- Do not delete the remaining unverified development campaign row without owner confirmation.
- Do not route gameplay across multiple uncoordinated FastAPI instances.