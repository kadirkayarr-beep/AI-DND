# AI-DND Project Status / Checkpoint Report

**Report date:** 28 September 2026  
**Scope:** Repository and development environment status after the completed Combat UX Polish phase. This is an inspection/report only; no feature work, engine changes, or deployment was performed.

## Evidence boundaries

- The report prioritizes current source, current test runs, current artifact configuration, and current Replit deployment metadata over old checkpoint prose.
- `ai-dnd/game.py` was hash-checked. Its current hash matches the protected checkpoint hash.
- API and deterministic tests were run with a temporary `AI_DND_CAMPAIGN_DB` so the development campaign database was not modified. The frontend panel tests, workspace typecheck, and production build were also run.
- A current-hash live Qwen smoke is recorded in `ai-dnd/LIVE_QWEN_SMOKE.md`. The completed Combat UX phase also included a real Chromium/Qwen browser run after an API-process restart; its sanitized result is summarized below.
- The earlier `ai-dnd/TESTING_CHECKPOINT.md` and `ai-dnd/CHECKPOINT_AI_PIPELINE_V10.md` are historical records. Do not copy their old source hashes or test totals as current facts.

## 1. Executive summary

AI-DND is a functional, single-user browser-based AI tabletop RPG development prototype. Its feature-complete browser experience is `artifacts/ai-dnd-experience`; it calls a Python FastAPI service, which owns sessions, campaign persistence, canonical state, world metadata, Journal updates, and Combat V1/V2 resolution. Real `qwen3:8b` narration has been verified through the server-side Ollama proxy.

| Area | Current verified status |
|---|---|
| Browser gameplay | Working in the Replit development environment: create/resume, natural-language turns, panels, Journal, and combat presentation |
| Qwen | `qwen3:8b` connected through a server-side Ollama proxy; not called directly by the browser |
| Campaign persistence | SQLite-backed; successful turns save canonical engine state and basic turn history |
| Character creation | Server-authoritative custom or random level-1 characters; browser supplies identity choices, not stats |
| World metadata | Server-owned environment, time-of-day, and weather values are serialized and persisted |
| Journal | Canonical location, NPC, and event tracking works; quest ledger is present but has no automatic lifecycle |
| Combat | Python Combat V1/V2 mechanics and structured UX are present; no Combat V3 |
| Public deployment | No active Replit deployment exists as of this report |
| Maturity | Useful local prototype; not production-ready for public or multi-user use |

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
- **Game engine:** `ai-dnd/game.py` owns the authoritative game rules, action/state mutations, random decisions, and Combat V1/V2. It remains protected/frozen for this phase.
- **Qwen:** the model helps interpret player intent and produce narration. Its output is bounded and checked; it does not directly write canonical game state.
- **Other services:** `artifacts/api-server` is a separate Express health/API scaffold and is not the AI-DND game engine or campaign store. Root `main.py` launches the terminal game, not FastAPI. Do not confuse either with `ai-dnd/api/main.py`.
- **Development workflow caution:** the workspace has both a root FastAPI workflow and an artifact-owned FastAPI workflow. Runtime session registries are process-local. Route traffic to one canonical instance; adding another API process without coordination can split session state.

## 3. Frozen engine / checkpoint

- **Protected source:** `ai-dnd/game.py`
- **Current SHA-256:** `e971f4cade451828697ab7c49900b634a9cf1a6a1997aa8c733d2a13e0a9c24a`
- **Checkpoint:** `ai-dnd/CHECKPOINT_CURRENT.sha256` contains the same hash for `game.py`.
- The hash was verified at the end of Combat UX work and again during this report. No source changes were made for this checkpoint report.
- The older `CHECKPOINT_V2.sha256`, `TESTING_CHECKPOINT.md`, and `CHECKPOINT_AI_PIPELINE_V10.md` refer to earlier source/test snapshots. They are historical evidence, not the current engine hash.
- Treat `game.py` as frozen unless the owner explicitly approves an engine change. Do not start Combat V3 as part of this checkpoint.

## 4. Completed development phases

| Phase | Goal and verified implementation | Deliberately not included | Current validation/status |
|---|---|---|---|
| 1. FastAPI / browser integration | Browser actions reach the Python API and are processed by server-managed sessions. Health, session, campaign, state, and turn operations are exposed. | Browser-to-Ollama calls; client-authored canonical state; public multi-user service. | API tests, live model smoke, and actual browser turns; **complete**. |
| 2. Full frontend integration | The `ai-dnd-experience` artifact provides the campaign browser, creation/reveal flow, adventure workspace, character/world/NPC/Journal/Combat views, and mobile drawers. | A full native mobile app, portrait generation, public deployment, and unsupported gameplay systems. | Frontend panel tests, workspace typecheck/build, mobile browser verification; **complete for the current web experience**. |
| 3. Persistent Campaign V1 | SQLite stores campaign snapshots, RNG, metadata, Journal, NPC memory within engine state, and player/narration history. Campaigns resume after a FastAPI restart. | Multi-instance coordination, account ownership, user-facing rollback to an old save, general schema-migration framework, campaign deletion API. | Persistence/API tests and restart/resume smoke; **complete within the single-instance boundary**. |
| 4. Canonical Character Creation V1 | Server validates custom/rand mode, chooses canonical race/class/name as applicable, generates stats/proficiencies, and computes starting character values. | Manual stat assignment, gear selection, rerolls, portraits, leveling, subclasses, feats, and spell selection. | Character/API tests; **complete for level-1 creation**. |
| 5. World Metadata V1 | Server derives/validates canonical environment, time-of-day, and weather metadata; state and themes survive resume. | Real clock, calendar, seasons, or automatic weather/time progression. | `test_world_metadata.py`, campaign serialization tests, theme integration; **complete for metadata V1**. |
| 6. Journal / Quest V1 | Journal records canonical discoveries, known NPCs, and notable events. A validated quest-ledger shape is serialized and rendered. | Automatic quest generation, acceptance, objective progress, completion/failure, or any quest inference from narration. | Journal/API/persistence tests; **Journal complete, quest lifecycle deliberately deferred**. |
| 7. Combat UX Polish | Combat V1/V2 state is rendered from Python’s canonical state; the API returns an allowlisted structured attack result; desktop and mobile Combat UI display rolls, HP, AC, initiative, and retaliation. | Combat V3 or new mechanics. Previous structured result cards are not restored after a campaign resume. | 25 authoritative V2 tests, five panel tests, real Qwen/Chromium attack and restart/resume flow; **complete for the requested UX scope**. |

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
| Turn history | Server history stores player message and narration. It does **not** store the structured combat result cards. The browser also keeps a local display transcript keyed by session ID; that cache is not canonical. |
| NPC memory | Stored inside canonical engine/world save, not in a separate vector/database service. |
| Combat | Active engine combat state, HP, round, participants/target, and initiative state persist. Previous frontend dice/result cards do not. |
| World metadata / Journal | Included in the versioned campaign payload and restored. |
| Versioning/migrations | Current database schema and campaign envelope are version 1. Reads validate versions and metadata and reject corrupt/unsupported saves. Resume has a narrow compatibility path for missing metadata/Journal; there is no general migration framework for arbitrary future versions. |
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

The quest ledger schema is validated and displayed, but new campaigns do not receive canonical quest state and current turns do not automatically create or progress quests. There is no confirmed Python-owned quest acceptance/objective/completion lifecycle. Narration or browser text must not be treated as a quest event.

The report prompt’s **#36 — “Let the Journal track quests from confirmed game outcomes”** describes this real gap. The implementation remains deferred: add it only after the Python engine exposes structured quest state transitions. This report does not imply the work is implemented or scheduled.

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
| API unittest suite | **68 passed, 0 failed.** Ran `python -m unittest discover -s ai-dnd/api/tests -p 'test_*.py' -q` with `AI_DND_CAMPAIGN_DB` redirected to a disposable `/tmp` database. Logged model-unavailable/storage-failure cases are expected negative-path tests. |
| Deterministic engine gates | **17/17 gates passed** with a temporary DB override via `python ai-dnd/run_tests.py`. Includes semantic, session, persistence, combat, regression, migration, query, door, and NPC-query checks. |
| Semantic/query/narrator checks | 87 semantic, 24 query-grounding, 18 narrator-safety checks passed inside the deterministic runner. |
| Combat V1 | 10 scenarios passed, including hit/miss, natural 1/20, knockout, target-location, and forged-target cases. |
| Combat V2 turn pipeline | 15 tests passed; the compatibility entry point runs the same 15 again and should not be counted as 15 additional unique cases. |
| Authoritative Combat V2 | **25 tests passed** (A–Y); old `TESTING_CHECKPOINT.md` count of 24 is stale. |
| Regression | 22 passed, 0 failed. The offline “Ollama unavailable” case intentionally verifies safe fallback; it is not live-model evidence. |
| Frontend Combat panel | **5 passed, 0 failed** via `pnpm --filter @workspace/ai-dnd-experience test`. |
| Workspace typecheck | **Passed** via `pnpm typecheck` across libraries and configured artifacts/scripts. |
| Production build | **Passed** via `PORT=5173 BASE_PATH=/ai-dnd-experience/ pnpm --filter @workspace/ai-dnd-experience build`. Vite emitted a non-blocking source-map warning at `src/components/ui/tooltip.tsx:2`; 1,777 modules transformed and the bundle built. |
| Live Qwen | Current-hash recorded smoke plus the real browser restart/resume attack test described above. These are separate from mocked/offline tests. |
| Source/checkpoint integrity | `game.py` hash matches `CHECKPOINT_CURRENT.sha256`; `git diff --check` was clean before creating this report. |

No coverage percentage/report is configured. Test totals above are current verification totals; older checkpoint counts should not be substituted.

## 15. Known issues

| Issue | Severity / impact | Workaround | Recommended fix / status |
|---|---|---|---|
| Previous structured combat result cards disappear after campaign resume. Canonical combat state still resumes correctly, but the detailed earlier dice/action cards are not in campaign history and the frontend clears them. | Medium; players lose the detailed combat record across a restart. | Current round/HP/target remain visible; the next attack produces a new card. | Persist validated, allowlisted combat results with server turn history and rehydrate them in the panel. Not a mechanics blocker. |
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
- Narrow skill-check cases exist, but no general typed/check-result API and polished check UI.
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
| Structured combat results are response/UI state, not durable event history. | Combat history is incomplete after resume and cannot support later replay/analytics. | Medium. Extend campaign history with a validated allowlist; keep engine mechanics unchanged. |
| OpenAPI contract and FastAPI aliases have drift. | Generated client and external integrations can disagree with runtime behavior. | Medium. Align spec, regenerate client, and test every advertised route. |
| Session registry is process-local while more than one development FastAPI workflow is configured. | Requests split across instances can produce missing session IDs even though SQLite campaign data exists. | Medium before deployment. Route one owner in dev; design shared runtime coordination before scaling. |
| Several layers validate/serialize engine saves, campaign envelopes, and public API state. | A field can be accepted/persisted but omitted or exposed inconsistently. | Medium. Preserve boundary-specific schemas and add contract tests instead of merging authority layers casually. |
| Ollama tunnel/proxy and model behavior are external development dependencies. | Availability and narration quality vary; no public-service reliability guarantee. | High before public use. Add production model operations, timeouts/observability, and fallback policy first. |

## 18. Backlog / deferred items

| Item | State of implementation | Why / prerequisite |
|---|---|---|
| Canonical quest outcomes (prompt-referenced #36) | Not implemented; the quest ledger remains empty without structured transitions. | Requires Python-owned quest acceptance/objective/completion state. Never infer from narration. |
| Combat result history persistence | Not implemented; earlier dice cards disappear after resume. | Persist safe `combat_result` entries and rehydrate them without exposing internal fields. |
| Canonical Skill Checks V1 | Narrow engine cases exist; broad contract/UI remains deferred. | Standardize named skill, ability/proficiency modifier, roll, DC policy, outcome, API schema, and presentation. |
| OpenAPI route parity | Partial/drift exists. | Align actual FastAPI routes and generated client; test contract. |
| Authentication and campaign ownership | Not implemented. | Required before exposing user campaigns to public/untrusted users. |
| Multi-instance/session coordination | Not implemented. | Requires a single runtime owner or shared session/locking design; SQLite alone does not share Python session objects. |
| Public deployment and operational hardening | No deployment exists. | Authentication, persistence ownership/backups, rate limiting, model operations, observability, and security review first. |
| Portrait generation | Not implemented. | Optional character presentation feature; separate from canonical identity. |
| Rich calendar/time progression | Not implemented. | Requires an explicit canonical clock, turn advancement, persistence, and tests. |
| Spells, leveling/XP, advanced combat, economy, factions, companions, procedural content | Not implemented. | Future gameplay systems; each needs an explicit canonical state model and dependency order. |

## 19. Recommended next development order

For continued **gameplay** work, the suggested order is:

1. **Canonical Skill Checks V1.** Formalize the narrow existing checks into a typed Python-owned result and API/UI display.
2. **Quest Outcomes V1.** Add only after Python exposes structured quest transitions; consume canonical skill/action outcomes rather than narration.
3. **Combat V3 design and implementation.** First define action economy, turn ownership, conditions, and multi-entity scheduling; avoid starting until those rules are agreed.
4. **Spells V1.** Depends on explicit class eligibility, spell choice/resources, and action/turn rules; the present creation form does not choose spells.
5. **XP / leveling V1.** Depends on canonical reward and quest/encounter completion outcomes and a migration-safe character save format.

This order remains reasonable, with one prerequisite change: resolve OpenAPI/runtime parity and confirm single-owner development routing before expanding client/API contracts. If the goal changes from gameplay prototyping to **public release**, prioritize authentication/ownership, rate limiting, durable backups, single/multi-instance design, observability, security review, and model operations before publishing.

## 20. Canonical Skill Checks V1 proposal (recommendation only)

This section is a scope proposal, not an implementation.

- **Build on:** existing narrow Python checks used by supported interactions (for example, Stealth, Investigation, and Athletics cases). Do not duplicate their dice/state logic in React or create a parallel rule engine.
- **Python owns:** identifying/validating the check, choosing the ability/skill and proficiency bonus, generating the die, applying a documented bounded DC policy, deciding the result, and any canonical state consequence. The numeric DC and outcome must not be accepted from a client or trusted solely from Qwen.
- **Qwen participates:** interpret natural-language intent and provide contextual narration. It may suggest a candidate check when the player’s intent needs one, but Python validates and resolves it; model prose is never the roll or the outcome.
- **Candidate V1 skills:** Perception, Investigation, Persuasion, Deception, Intimidation, Stealth, Athletics, Acrobatics, Insight, Survival. Include only the skills/classes supported by current engine data; make unsupported requests explicit rather than silently inventing rules.
- **API/UI:** return a typed result with skill, ability, d20, modifier/proficiency, server-owned DC or difficulty label, total, outcome, and any canonical effect. Show the result in the story and an accessible compact result view; do not add a client-side dice calculator.
- **Tests:** natural 1/20 policy if applicable to the chosen rules, proficiency/non-proficiency, invalid skill, malformed model intent, ambiguous target, no state mutation on failure, rollback, session isolation, and API serialization.
- **Out of scope:** saving throws, opposed checks, spells, new action economy, arbitrary model-authored DCs, skill-tree progression, and changes to Combat V3.

## 21. Future gameplay systems

These are possibilities, not current capabilities:

- **Core rules:** broader skill checks, saving throws, spells, conditions, rests, XP/leveling, equipment stats, and action economy.
- **World:** structured quests, factions, reputation, economy/shops, richer route/travel planning, calendar, seasons, and weather progression.
- **Characters:** subclasses, feats, backgrounds, portraits, companions, and party management.
- **Content:** procedural dungeons, structured encounters, loot tables, handcrafted campaign packs, and lore codex.
- **Product:** accounts, cloud saves, multiplayer, campaign sharing, DM mode, and public hosting.

## 22. Security / authority review

| State or boundary | Current trust boundary |
|---|---|
| HP / AC / inventory | Server engine owns values. Turn input does not accept authoritative stat/inventory fields. |
| Combat state / dice | Python validates target and resolves rolls/damage/state. Browser displays structured results; it cannot submit the result. |
| World metadata | Server derives, validates, snapshots, and serializes it. Qwen receives context but does not write metadata. |
| Journal / quests | Server derives Journal changes from canonical before/after state and action result. There is no browser write path or narration-based quest completion. |
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

1. `ai-dnd/game.py` remains protected unless the owner explicitly approves a change; report any SHA change.
2. Python owns canonical state and mechanical outcomes.
3. Qwen may interpret/narrate; it never directly owns HP, AC, inventory, combat, world metadata, or Journal/quest reality.
4. The frontend presents canonical values and must not calculate authoritative dice/results or persist canonical state locally.
5. Keep session ownership explicit; do not restore shared-world aliasing or let one campaign mutate another.
6. Keep campaign saves validated, versioned, transactional, and rollback-safe.
7. Keep Turkish matching deterministic and entity-grounded; do not use substring matches or rewrite the player’s original model input.
8. Do not infer quest acceptance/progression/completion from narration.
9. Do not add Combat V3 mechanics under a UX-only change.
10. Do not expose Ollama secrets or raw internal engine/model data in browser responses.
11. Do not add a second API process or route owner without accounting for process-local session registries.
12. Run the regression suite and report current source hash before calling a future phase complete.

## 25. Current roadmap checkpoint

**COMPLETED**

- ✅ FastAPI/browser integration and natural-language turn flow.
- ✅ Full responsive web experience and server-authoritative character creation.
- ✅ SQLite Campaign V1 persistence and restart/resume.
- ✅ Canonical world metadata and persisted Journal V1.
- ✅ Combat V1/V2 UX polish, structured API result, mobile presentation, and real-browser verification.

**NEXT (recommended gameplay phase)**

- ➡️ Canonical Skill Checks V1, after API/OpenAPI parity and session-routing boundaries are understood.

**BACKLOG**

- ○ Canonical quest outcomes from confirmed Python state.
- ○ Combat result-history persistence across resume.
- ○ API contract parity, authentication/ownership, and multi-instance coordination.
- ○ Public deployment hardening, backups, model operations, and security review.

**LATER**

- ○ Combat V3, spells, XP/leveling, advanced world systems, portraits, companions, multiplayer, and campaign sharing.

### Handoff summary (12 lines)

1. AI-DND is a single-user Replit development prototype; no active public deployment exists.
2. Main browser product: `artifacts/ai-dnd-experience`; game API: `ai-dnd/api/main.py`.
3. `ai-dnd/game.py` is protected; SHA-256 is `e971f4cade451828697ab7c49900b634a9cf1a6a1997aa8c733d2a13e0a9c24a`.
4. Python owns canonical state; Qwen `qwen3:8b` interprets/narrates through a server-side Ollama proxy.
5. Campaigns persist in SQLite; campaign IDs survive restart, runtime session IDs do not.
6. Successful turns autosave state, RNG, metadata, Journal, NPC memory in the engine save, and player/narration history.
7. Journal tracks canonical locations/NPCs/events; the quest ledger remains empty until Python emits structured quest outcomes.
8. Combat V1/V2 is authoritative and resumable; Combat V3 is not implemented.
9. Structured combat result cards are not restored after campaign resume.
10. Validation: 68 API tests, 17 deterministic gates, five UI tests, workspace typecheck, and production build passed.
11. The dev DB retains one campaign row of unverified provenance; preserve it pending owner confirmation.
12. Before public use, add auth/ownership, rate limits, backup/recovery, model operations, and a security review.

## A. Current health

**Local-development health: green.** **Feature completeness: prototype / partial rules system.** **Public production health: not ready.** Current tests, typecheck, build, engine hash, and real Qwen/browser evidence are satisfactory for the completed local phases; authentication, deployment, multi-instance persistence, and unfinished rules systems remain material gaps.

## B. Top 5 risks

1. Unauthenticated campaign list/read/resume/save routes expose all campaigns to anyone who can reach the API.
2. Runtime sessions are process-local; multiple API instances can split or lose session routing.
3. Local SQLite has no configured production backup/ownership strategy or general schema migration framework.
4. Qwen/Ollama availability and narration quality depend on the development proxy; model operations and abuse/rate controls are not production-grade.
5. Quest lifecycle and durable combat result history are incomplete; future systems must not infer canonical outcomes from narration.

## C. Top 5 next actions

1. Align OpenAPI paths/schemas with FastAPI and keep codegen contract tests current.
2. Define and implement Canonical Skill Checks V1 using Python-owned rolls/outcomes.
3. Persist allowlisted combat result history and restore it in the panel after resume.
4. Add structured quest outcomes only after the Python engine owns quest transitions.
5. Before public publishing, design auth/ownership, session routing, backups, rate limiting, observability, and security review.

## D. Recommended next phase

**Canonical Skill Checks V1** is the recommended next gameplay phase. It should turn existing narrow checks into a typed Python-owned result shared by the API, narration guard, and browser display. If the product goal changes to public release first, security and persistence hardening takes precedence.

## E. Do not touch / protected areas

- Do not modify `ai-dnd/game.py` or begin Combat V3 without explicit owner approval.
- Do not use historical V2/V10 hashes or test counts as the current checkpoint.
- Do not let Qwen or the browser author canonical mechanics, campaign saves, Journal state, or quest completion.
- Do not infer quest progress from narration.
- Do not delete the remaining unverified development campaign row without owner confirmation.
- Do not route gameplay across multiple uncoordinated FastAPI instances.