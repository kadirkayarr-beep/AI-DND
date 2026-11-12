# Living world: design-to-code map

Answers section 14 step 1 and 2 of `02_YASAYAN_DUNYA_TASARIM_TR.md`. Design only. Nothing implemented, no product test or model run.

**Evidence pin:** every `file:line` is commit `cba0408` (`task/c-series-merge`), paths under `ai-dnd/`. `game.py` and `grounded_action.py` were being edited in that worktree during this work, so `game.py` citations were rechecked against the commit object, not the working copy. `graphify-out/graph.json` is absent in both worktrees, so direct search replaced the graph.

## Bottom line

- **No NPC has a goal with a next step anywhere in the code.** `immediate_goal` is text that nothing reads for decisions. The only thing that moves NPCs through time is a daily position routine, and it is off unless an environment variable is set.
- **The good news is the shell exists.** The clock, atomic turn commit, action-id replay, listeners on events, perspective entries, an offer-like Thread, and the two-call arbiter are all real. The slice is one new owner module plus small hooks, with no save version bump.
- **Five facts constrain the slice** (section 3a). The biggest: a failed extra model call currently rolls the whole turn back, and scheduled events cannot carry NPC plans because they stop at the player's location.
- **The narrator receives private fields today**, chiefly the full personal profile including `immediate_goal` (section 4). Fix this first; it is independent and small.
- **Dependency:** the 20-turn run (`OLCUM_20TUR_20261031.md`) shows conversation mostly does not start. A living-world slice cannot be observed by a player until that routing is fixed.

## 1. Design section 3 records against the code

| Record | Exists | Partial | Missing |
|---|---|---|---|
| **Campaign clock** | `campaign_id` (`api/session_manager.py:223`), game time as `start_second + elapsed_seconds` (`campaign_time.py:82`); campaign `revision` in store (`api/persistence/campaign_store.py:287`) | Clock only moves to `stop_at`, with `remaining_seconds` reported (`campaign_time.py:129-133`) | Durable `resolved_through`. Out-of-horizon events are not resolved, so game time is not a resolved boundary |
| **NPC** | `id`, `location`, `current_hp`, `combat_status`, `npc.inventory` (`adventure/dialogue_jobs.py:72`). One `location` string prevents two places | `current_activity` is one profile string, rewritten by routines (`scheduled_events.py:560`). Obligations exist only as "pinned by quest" (`:543-546`) | `goal_ids`, `plan_id`, `last_resolved_time`. Also `_occur` moves an NPC with no liveness check (`scheduled_events.py:239-241`) |
| **Goal** | None as a record | `personal_profile.immediate_goal`: template text (`local_dialogue.py:104`) or a place issue (`local_places.py:345`). Required by `ensure_personal_profile` (`:311`), read by no logic | Everything: owner, desired state, priority, costs, review trigger, status |
| **Resource / obligation** | Item containers with exclusive ownership (`adventure/dialogue_jobs.py:81-83`) | Promises: `npc_statements` commitments (`npc_statements.py:492-508`) and `Commitment` (`interaction_adventure.py:62`). Two separate stores | Reservation, `expires_at`, time as a resource |
| **Knowledge / belief** | `PerspectiveEntry` with `kind`, `source_id`, `secret` (`interaction_adventure.py:85-90`); PC knowledge in `player_knowledge` | Only `player_claim` has a production writer (`:1061`). `record_witness` (`:604`) has no caller. `belief`, `rumor`, `lie` have no writer | `learned_at`, `confidence`, `truth_link`, `disclosure_scope` |
| **Plan** | None for NPCs | `interaction_adventure.Plan` (`:114`) is the **player's** single plan slot (`:142`). `dependencies` and `followups` on scheduled events are event chains; no production definition uses `followups` | `owner_id`, `next_step`, `alternatives`, `required_resources`, `earliest_at`, version |
| **Offer / agreement** | Quest lifecycle: `AVAILABLE` until heard, then `DISCOVERED`, `ACTIVE`, `ABANDONED`, `FAILED`, `COMPLETED` (`adventure/play.py:21-83`). This already separates exists / heard / accepted. Deadline via `adventure/deadlines.py:8` | `Thread` status `offered` (`interaction_adventure.py:50`) with `refuse/agree/betray` operations (`:1234-1278`). `dialogue_jobs.prepare` creates jobs with parcels and rewards. Thread `deadline` is dead: `bind_deadline` (`:625`) has no caller | Explicit issuer and recipient, `accepted_terms` snapshot, a refused state distinct from abandoned, withdrawn, filled by another. `refuse` also marks commitments broken (`:1264-1269`), which the design forbids |
| **Event** | Four logs: `scheduled_events`, interaction `events` with `listeners` (`:93-104`), `campaign_journal` `notable_events`, `world["events"]` texture | `dependencies`, `causal_group`. `listeners` are close to witnesses | One event identity with `causal_parent_ids` and `action_id`. Noticing versus identifying versus telling are not separated |
| **News transfer** | None | `incidents/knowledge.py:12` `rumor` has no production caller | Whole record. Nothing carries information between NPCs |
| **Creative proposal** | Incident pipeline: envelope, `attempts.run`, gate, `commit`, canon stamp (`incidents/commit.py:97`). Off unless `AI_DND_EMERGENCE_LIVE=1` on the Neverwinter pack (`api/session_manager.py:226-230`) | `Candidate` (`interaction_adventure.py:148`), `job_proposals`, `create_npcs`, each narrow | Proposed plans or actions, `valid_from`, `resource_costs`. Generators stop at the player's horizon by design (`incidents/horizon.py:11-12`) |
| **Action receipt** | Strongest match. `action_id`, `request_hash`, stored response, `public_state`, `base_revision`, `committed_revision`, `result_digest` (`api/main.py:1042`, `:1099`, `:1674`; `api/session_manager.py:649`; `api/persistence/campaign_store.py:343`). One unresolved action per campaign (`api/main.py:1058`) | Narration fails to a deterministic fallback, inside the same commit | `result_event_ids` |
| **Player view** | `serialize_session_state` is an allowlist (`api/serializers.py:611`, `:628`). `public_npc_*`, `name_known_to_player`, incident `awareness` | Several small projections, no single one | One `viewer` record and `projection_revision`. **The narrator does not read the public projection** (section 4) |

## 2. What advances NPCs in game time

| System | What changes | On a real default turn? |
|---|---|---|
| `campaign_time.advance` | Runs `process_events`, then `close_due` (`campaign_time.py:122-128`) | **Yes** on wait, sleep, travel, walking, rest (`game.py:4546`), exploration, foraging, combat rounds (`game.py:5500`). Plain conversation adds 0 s unless `free_v1` is on, then 60 s (`dialogue_runtime.py:398`) |
| Daily routines | NPC position and activity string (`scheduled_events.py:535-568`) | **No by default.** Seeded only inside `observe_turn` (`dialogue_runtime.py:394`), which returns early unless `is_enabled` (`:360`). That needs `AI_DND_DIALOGUE_MODE=free_v1`, read at `api/session_manager.py:225`, only documented at `docs/PLAYABLE_DIALOGUE.md:26`. Even when on: one fixed shape, 8 to 22 at work, otherwise rest (`:582-585`) |
| Scheduled `npc_location`, `npc_hostility`, `route_block`, `flag` | Effects are real (`scheduled_events.py:236-248`) | **Tests and one live smoke only.** The production registrars are `deadlines.arm` (no effects, `adventure/deadlines.py:28`) and `arm_table_absence` (`game.py:7225`) |
| Table absence | An item or mark on a table changes while the player is away | Yes, hidden and narrow. Armed on leaving, resolved on arrival inside 24 h |
| Quest deadlines | Quest goes `FAILED` (`adventure/deadlines.py:37-55`) | Yes. Clock-driven, but no NPC does anything afterwards |
| Incidents | Lifecycle only: `IGNORED` or `EXPIRED` (`incidents/commit.py:127`) | Early return with no incidents (`incidents/hooks.py:104`). Generation needs the live flag. Neither moves an NPC |
| `consume` Thread expiry | Thread `expired` (`interaction_adventure.py:1420`) | Dead path: `deadline` is never bound |
| `initiative_beat` | A reminder line every 5 turns on look or query (`:1483`, `game.py:17254`) | Yes, but counted in turns, not game time. Its docstring says it is not simulation |
| Relationship and observation notes | Score, `dialogue_observation`, `dialogue_deception` (`dialogue_runtime.py:364-392`) | Only `free_v1`. Threat detection is an exact-phrase match (`:372-374`) |
| Escort and show commitments | Fulfilled when the NPC walks with the player (`grounded_action.py:1262`) | Yes, player-driven, not goal-driven |

**Verdict:** nothing is an NPC goal with a next step. Everything above is a clock position, a timeout, or a reaction to the player. In a default campaign, no NPC changes anything over game time.

## 3. Smallest vertical slice

### 3a. Facts that constrain it

1. **The call cap is a hard failure, not a budget.** Two calls maximum. A third raises (`api/ollama_adapter.py:207`) and is refused at `api/main.py:1461`. "One extra call" can only use a free slot. The design also forbids a hidden third call.
2. **A failed extra call kills the turn.** Any adapter failure outside `resolved_narration` returns 503 and rolls back (`api/main.py:1447-1459`). The incident call has this latent bug: `incidents/attempts.py:189` catches the exception, but the adapter already recorded it (`api/ollama_adapter.py:220`), and `before_narration` runs outside the scope (`game.py:16740` versus `:16746`).
3. **Scheduled events cannot carry plans.** `_in_player_horizon` covers only the current location, its children, and the active road (`scheduled_events.py:479-490`). Due events elsewhere are marked missed without effects (`:464-476`). Also 256 total with no pruning, and over-cap raises (`:18`).
4. **Canonical context is not bounded, and it crowds out memory.** The 4800-byte fit counts it, but `narrative_director.py` sends the unclipped original (`enriched = dict(canonical_context)`) and keeps only the fitted continuity. Each byte added to canonical context can push continuity out (`api/narrative_memory.py:781-815`). The largest measured prompt was 4608 tokens.
5. **Offers split by mode.** In `free_v1`, NPC speech is claimed at `game.py:16533` and never reaches `interaction_adventure.resolve`, so speech cannot accept or refuse. Jobs are accepted only through the journal (`dialogue_commitments.py:59`). In legacy mode the route works, but offers are five fixed titles with no reward (`interaction_adventure.py:1356-1362`).

### 3b. Scope

One new owner, `ai-dnd/npc_agenda.py`, in the style of `interaction_adventure.py`: strict pydantic, no module state, no clock writes. Any offer becomes the giver's plan, so no NPC-specific chains and no authored content.

**World key `npc_agenda_v1`:**

```
State    version=1, resolved_through:int, plans[], offers[], news[], log[] (cap 64)
Plan     plan_id, owner_id, offer_id, goal_kind="fill_offer", version,
         status(active|blocked|done|dropped), next_step, tried_npc_ids[],
         needs_review:bool, last_resolved_at
Step     kind(await_answer|seek_other|do_self|drop), target_npc_id|null,
         earliest_at, deadline
Offer    offer_id, issuer_id, recipient_id="player", source_ref("quest:<id>"|"thread:<id>"),
         public_terms, offered_at, presented_at|null, expires_at,
         state(presented|accepted|refused|expired|filled_by_other|breached|completed|failed),
         accepted_terms|null, player_outcome_seen:bool
News     message_id, sender_id, recipient_id, kind, source_event_id,
         earliest_arrival, delivered_at|null, credibility(heard|witnessed)
Log      event_id, causal_parent_ids[], source, at, kind, actor_ids[], witness_ids[]
```

Deferred on purpose: resources and reservations, `truth_link`, confidence levels, background detail levels, creative new entities.

### 3c. Flow

**Offer, zero extra calls.** `open_offer()` is called from two creation sites: `adventure/dialogue_jobs.py` after `director.discover` (line 70), and `accept_candidate` (`interaction_adventure.py:1363`). It creates the Plan with `await_answer`.

**Accept and refuse, zero extra calls.** Reuse calls that already happen.
- Legacy: envelope `agree` and `refuse`. Bind to the issuer's sole open offer when `thread_id` is null (repair, not reject).
- `free_v1`: add one optional enum `offer_decision` (`none|accept|refuse|breach`) to the dialogue packet. `validate_reply` needs one key added to its strict set (`dialogue_runtime.py:115-116`). Python binds it to the sole open offer.
- Change `refuse` so an **offered** thread does not break commitments (`interaction_adventure.py:1264`).
- `ignored` is not a state. The offer stays open until `expires_at`, and real time never touches it.

**NPC plan, zero calls by default.** On refuse or expiry, the step becomes `seek_other` at `now + 3600`, capped at the deadline. Execution rechecks owner alive, free, not in combat. Candidates are other living NPCs in the settlement, not yet tried. Order and result come from a stable hash of `campaign_id:plan_id:version:npc_id` (same idea as `incidents/rng.py:16`), so split and bulk time give the same result. Success closes the offer as `filled_by_other`. The quest or thread closes through its existing transition. No offer is re-presented.

**Betrayal, zero extra calls.** A breach is an accepted offer that the player acts against, through `betray` or `offer_decision=breach`. Python reads it as a claim, not a fact: it records that the player told a third party, never that the deal was criminal. Python then:
1. sets `Offer.state=breached`,
2. calls `_event(privacy="public")` with kind `witnessed_fact`, giving listeners from `present_npcs`,
3. calls `record_witness` (first production caller, no schema change).

Relax `betray`'s `thread` requirement (`:1253`) the same way as above.

**News with witnesses, zero calls.** If the issuer is a listener, they know now. If not, and a witness exists, one `News` goes from witness to issuer with `earliest_arrival = now + 3600` in the same settlement. No witness means no message, so the issuer does not know. On delivery:
- write a `PerspectiveEntry` kind `rumor` on the issuer,
- `relationships.note(issuer, -2, "breach:<offer_id>")`,
- set `needs_review` on any plan of that issuer.

The player sees the result only through that NPC's voice, using the existing perspective channel.

**Extra model call, only when needed.** Trigger: `needs_review` (candidates exhausted, or news changed the plan). Output is an enum plus ids, no prose:

```
{choice: wait|ask_npc|do_self|drop, target_npc_id: id|null, delay_seconds: 0..14400}
```

- Fresh message list, never `session.messages`, never narrative memory.
- `num_predict` about 120, input under about 1,200 tokens.
- Python validates, and an invalid answer changes nothing.
- If no slot is free, the flag stays, and at the deadline the engine applies `drop`. The world never waits on the model.
- Time-spending turns are the usual fit, because wait and travel often use no model call. This is inferred, not measured.

### 3d. Hook points

| Point | Location | Why |
|---|---|---|
| Tick, no model | `campaign_time.py:128`, after `close_due`: `known.extend(npc_agenda.resolve_due(world, resolution["stop_at"], source))` | Every clock movement passes here, uses the actual stop point, never wall clock. `grounded_action.py:1013` swallows exceptions, so resolve on a copy and assign at the end. Max 16 items per call; set `resolved_through` only when drained |
| Review call | `game.py:16421`, right after `observe_turn` in `_run_player_turn` | All routes converge here, after narration, so the narrator cannot see it. Inside the transaction, so replay never recalls it. Use `arbiter.decide(calls_used=..., narration_needed=False)`, which allows it only when at most one call is used |
| Failure safety | `api/model_phase.py`, `only_resolved_narration_failures` | Add a tolerated phase for this call so a failure is logged and the turn stands. Fix the incident path the same way |
| Narrator | `game.py:6752`, add `known_news` beside `player_known_events` | Max 2 items, 200 bytes each, player-known only. Filled when the player reaches the issuer, via one `_event(player_known=True)`, which also reaches the journal through `api/campaign_journal.py:766` |

### 3e. Files and saves

| File | Change |
|---|---|
| `npc_agenda.py` (new) | Owner. Estimated 300 to 450 lines, unverified |
| `campaign_time.py`, `game.py` | Tick hook, review hook, `known_news`, profile allowlist (section 4), save validation |
| `interaction_adventure.py` | `open_offer` call, refuse fix, sole-offer binding, `betray` relaxation |
| `adventure/dialogue_jobs.py`, `dialogue_runtime.py` | `open_offer` call, `offer_decision` |
| `api/model_phase.py` | Tolerated phase |
| `run_tests.py`, `test_runner_inventory.py` | Both hold explicit release lists, so register new tests |

**Saves.** Additive top-level key, absent on old saves. Validate only when present, after `game.py:2354`. No change to `save_migration.py` and no `SAVE_FORMAT_VERSION` bump (4; versions 1 to 6 load). Do not add fields to `interaction_adventure.State` (`extra="forbid"`, an older build could not load it) or to scheduled events. Read with no write on absence, like `npc_statements.view`. The key lives in the engine save, so it commits with the receipt and rolls back with the turn. `serialize_session_state` is an allowlist, so it stays private unless added. Existing offered threads stay as they are, with no back-adoption.

**8K.** The agenda never enters the narrator except `known_news` (max 400 bytes). The profile allowlist removes about 140 bytes of values plus key names, from template means. Net worst case is about +200 bytes on news turns only, none otherwise. The review call is under the design's separate 8K.

### 3f. Tests, written first, synthetic ids only

| File | Must prove |
|---|---|
| `api/tests/test_npc_agenda_time.py` | Reading, reload, and idle do not move plans; explicit wait does; split and bulk time give the same state; dead owner acts on nothing; sent news survives sender death; the 16 cap keeps a durable queue; the tick works outside the player horizon |
| `api/tests/test_npc_agenda_offer.py` | Refuse breaks no commitment; ignored stays open; refused offer never re-presented; expiry and `filled_by_other` close the source quest or thread; acceptance snapshots terms |
| `api/tests/test_npc_agenda_news.py` | No issuer reaction before arrival; reaction after; no witness means no message; a false claim stays a claim; relationship applies once |
| `api/tests/test_npc_agenda_model_budget.py` | Review at 0 or 1 calls; defers at 2; never a third call; provider failure keeps the turn; same `action_id` replays with one review and one event set; conflicting content returns 409 |
| `api/tests/test_npc_agenda_save.py` | Old save loads and round-trips unchanged; corrupt key refused; commit-before and commit-after disconnect behave as design section 13 |
| `api/tests/test_narrator_private_projection.py` | Sentinel values in private profile fields, plans, and hidden NPCs never reach `build_world_context`, the prompt, `serialize_session_state`, or the review call's history |

Build order: narrator fix, schema and tick, offers, news, review call. Each step is shippable alone.

## 4. What reaches the narrator that should not

`build_world_context` (`game.py:6733`) reaches the prompt at `:12383`. Its NPC keys are an allowlist, so `backstory`, `knowledge`, `inventory`, `daily_routine`, and `dialogue_deception` do **not** reach it. The pops at `:6852-6853` are dead code.

| Priority | Path | Problem |
|---|---|---|
| **High** | `procedural_personal_profile` (`game.py:6788-6795`) | The whole profile for the addressed NPC: `immediate_goal`, `personal_detail`, `recent_activity`, `mood`, `schema_version`, plus any extra key. The gate is "role known", which is not a disclosure rule. For place-furnished NPCs the role is always known (`local_places.py:338`) and `immediate_goal` holds the place issue (`:345`). The speech path already excludes these (`game.py:7729`), and `SHAREABLE_PROFILE_FIELDS` exists (`interaction_adventure.py:178`). Fix: allowlist. Better: send a field only once it is the accepted conversation focus |
| **High** | `personality`, `tags`, `relationship`, `shop_id` (`game.py:6783-6784`) on an NPC whose role is hidden | `public_npc_role` returns None, but `tags` can hold `shopkeeper` and `shop:<id>` (`game.py:4204`), and `shops[].shopkeeper_id` links them. `personality` repeats through `perspective` (`interaction_adventure.py:598`). This is the route for "the game states what the character has not noticed". Fix: visible cues only for unknown roles |
| **High** | `door` (`game.py:6847`) | Sends `locked`, `open`, `broken` whether or not the player has learned them. `_current_door` has no hidden filter (`:2899`). Fix: only what is observed or tested |
| Medium | `active_npcs` (`game.py:3636`) | Filters by `scheduled_events.visible_npcs` only, which ignores `hidden` and `discovered`. The API uses the stronger `exploration.player_entities` (`api/serializers.py:628`). I found no production writer of a hidden NPC, so this is latent |
| Medium | `interaction_perspective` (`game.py:6857`) | Only `secret` is filtered (`interaction_adventure.py:600`). A `kind` of `lie` or `belief` would label the speech for the narrator. Latent until something writes those kinds, which this slice starts doing |
| Medium | `id`, `reality_layer`, `active_npc_id` (`game.py:6783-6816`) | Engine vocabulary in the prompt. Likely source of the `[[npc_001]]` shown to the player (20-turn finding 5). Unverified |
| Low | `verified_npc_memory` (`:6797-6800`) | With no target, every visible NPC's memory. Labelled verified, but it is only attributed speech |
| Low | `recent_events` (`:6832`) | Free model text filtered by location only |

**Unknown names inside `build_world_context` are safe:** `:6747`, `:6819`, `:6860` all use `public_npc_name`, and `incidents/projection.py:81` respects `name_known_to_player`. **Outside it they are not:**
- `dialogue_runtime.py:102` sends the canonical speaker name to the speech model.
- `adventure/dialogue_jobs.py:29` sends canonical target names.
- `dialogue_commitments.py:47` and `adventure/dialogue_jobs.py:66`, `:136` put canonical names in player-visible text.

Separately, two unknown NPCs of the same role get the same label (`living_world.py:266-274`), which matches 20-turn finding 1.

**Clean:** `current_campaign_time`, `player_known_events` (observed only), `pending_event_decisions`, `scene_incidents`, `known_history`. Secrets did not leak through these paths. No test names `procedural_personal_profile`, so narrowing should not break a key assertion, but I could not run the suite.

## 5. Risks and what I could not determine

**Risks**
- **Order of work.** 8 of 20 turns hit a clarification wall. Until that is fixed, a player cannot reach an offer to test.
- **Which mode ships is an owner decision.** Legacy has speech accept but thin offers. `free_v1` has real jobs and routines but no speech accept without this slice. Everything above supports both, which costs two creation sites.
- **Thin content.** Offers carry only what those two sources provide. A generic plan on a thin offer may feel hollow; this needs the owner's play judgement, and no state test can prove it.
- **Existing refusal path.** `dialogue_jobs.py:60` raises on a closed job, which becomes a 503 at `api/main.py:1408`. Plans will close jobs more often, so it must become a dropped proposal.
- **Routine overlap.** The slice deliberately does not move NPCs. `process_npc_routines` overwrites location, and any scheduled location effect suspends a routine permanently (`scheduled_events.py:550-552`).
- **Relationship idempotence** relies on a 24-item reason list (`relationships.py:59-62`), so an old reason can be evicted and reapplied. Guard on offer state.
- **Uuid event ids** (`interaction_adventure.py:1017`) differ between runs. Equivalence tests must compare meaning, not ids.
- **Failure-policy change** touches a sensitive path in `api/main.py`. Test it as carefully as the feature.
- **Latency** of the review call adds to its turn. The 4 s narration figure does not cover it.

**Could not determine**
- Whether the owner's launch sets `AI_DND_DIALOGUE_MODE` or `AI_DND_EMERGENCE_LIVE`. The repository sets neither. This decides what is live in actual play.
- Real token counts for any change here. All byte and token figures are estimates. The only measured figure is the 4608-token prompt, from a run that barely reached NPC speech.
- How often a free model slot occurs on a real turn. I traced the routes but have no per-turn distribution. If it is rare, plans fall back to deterministic `drop` more often, which is safe but duller.
- Whether Ollama keeps prompt state between calls in a way that matters for the design's separate-context rule. The slice uses separate message lists; I did not inspect runtime caching.
- Undo behavior. The checkpoint exists (`api/main.py:1779`, `:1825`). I assume agenda state reverts with `world_state` but did not trace it.
- Behavior of unread parts: I read `game.py` by targeted sections only, and did not read `incidents/gate.py`, `adventure/director.py`, or `adventure/arcs.py`.
- Whether `task/c-series-merge` line numbers survive the edits in progress there.
