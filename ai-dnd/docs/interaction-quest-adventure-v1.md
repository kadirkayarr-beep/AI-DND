# Interaction & Quest Adventure V1

## Purpose and source authority

Open-ended Turkish player actions, fallible NPC perspectives and persistent
campaign-specific adventure threads, not dialogue menus or an MMORPG quest box.
Python decides game reality; the existing lore authority decides setting reality.
Only accepted structured campaign events establish campaign canon. Qwen interprets,
proposes within explicit bounds and narrates. Model prose is never evidence.

Mechanics: PHB/DMG 2024 and the uploaded current Monster Manual. Setting:
Heroes/Adventures of Faerûn. Baseline: 1501 DR, Year of the Shining Mythal.
Published adventures are possibilities, not assumed campaign history.

## Starting read-only audit

Branch main; HEAD bdabbbf1f20eaea335a707ab83577413f0339876.
Tracked tree initially clean. Two user prompt uploads were untracked:
Pasted-AI-DND-INTERACTION-QUEST-ADVENTURE-V1-LONG-AUTONOMOUS-I_1791161540128.txt
and Pasted--OPERATIONAL-HYGIENE-DO-NOT-WASTE-THE--1791161633955_1791161633955.txt.
Cached origin/main: 5983853dbb6ae7d4852f4a3f8e070c3fe1e440f1;
live remote not contacted. No Git mutation is required by this package.

| Capability | Class | Production owner / decision |
|---|---|---|
| Intent and generic interaction | B | game.parse/normalize/validate_player_intent and execute_intent; extend with a bounded envelope, do not replace |
| Dialogue/addressee/observation | A | game.plan_living_world_turn, resolve_npc_reference, local_dialogue and living_world |
| Skill/social checks and RNG | A/B | api.core_resolution, game deterministic checks; persuasion is not consent or mind control |
| Procedural NPC creation | A | living_world + validated game proposal path; no parallel NPC factory |
| NPC memory | B | player-originated NPC-ID-bound memory exists; typed claims/beliefs, privacy and filtered perspectives missing |
| Quest ledger/catalog | A | GameSession quest methods; strict save shape and empty production catalog retained |
| Flexible adventure lifecycle/plans | C | bounded world-state extension, integrated into the existing turn/save owners |
| Events/journal | A | api.campaign_journal; structured extension events feed the existing journal |
| Campaign Time and schedules | A | campaign_time, scheduled_events, timed_gameplay; deadlines consume clock deltas, never advance them |
| Inventory/equipment transfer | E | existing ground/player sword path and NPC combat equipment are not a general ownership/transaction owner; fail closed interface only |
| Save/SQLite/receipts | A | game save validator, api.persistence.campaign_store, SessionManager.autosave_turn; reuse atomic receipt transaction |
| Narration validation/budget | B | existing finish_turn/narrate_resolved_turn + safety validators; scoped perspectives and immersive fallback needed |
| Public API/frontend | B | api.serializers/schemas, OpenAPI, ai-dnd-experience; render returned state, retain free-text input |

Relevant existing verification: campaign API/idempotency, quest journal, narrative
rebalance/safety, model isolation, Campaign Time, bounded encounter and development
tooling suites. Historical evidence is not proof for these changes.

## Ownership and compatibility

The existing catalog quests keep their original shape and status semantics.
An optional versioned adventure extension inside the existing world snapshot holds
dynamic threads, commitments, plans, typed NPC perspectives, structured novelty
tags and accepted event records. Missing extension in an old save means empty
state. Malformed present state fails validation, not silent reset.
This is not a second save store, scheduler, RNG owner or quest catalog.

Threads may be discovered/offered/active/progressing/reframed/succeeded/failed/
abandoned/expired; not every thread must pass every state. Personal goals are
intentions, not facts. Objectives have server-owned alternative evidence routes.
Failed checks do not delete routes or make progress automatic. New evidence can
justify reframing; voluntary side switching changes allegiance, not faction canon.
Player statements of success cannot complete objectives.

## Open-ended proposal contract

One optional structured interpretation/proposal call can return an interaction
envelope and up to three local candidates. Operations cover goals, requests,
negotiation, refusal/delay, conditional agreement, commitments, information,
reframing, side switching, abandonment and bounded plans. IDs are grounded in
current canonical context; player-originated descriptions must be exact spans of
the input. No arbitrary mechanics, check DC, rewards, time, entities or truth
updates are accepted from this envelope.

Requests retain NPC agency. A proposal of willingness is not permission to mutate
inventory or impose a social outcome. Missing ownership/transfer authority means
no transfer, even on a high roll. Unsupported later-package operations return
natural in-world uncertainty and a structured diagnostic internally.

## NPC perspective and privacy

Distinguish facts witnessed by an NPC, player claims, beliefs, rumors and lies.
All are provenance-bound; claims/beliefs/rumors never upgrade themselves to truth.
The proposal/narration context contains only the addressed NPC's appropriate
perspective, public scene identifiers and player-known evidence; hidden objectives,
secrets and unrelated memories are excluded.
Private speech is heard only by its explicit addressee. Explicit public speech
may be heard by present conscious NPCs. No inferred off-screen propagation.
Rumor/reputation/survivor simulation remains a later-package interface.

Promises persist as commitments to the stated player intent. Fulfillment requires
accepted evidence, not Qwen assertions. Callbacks/reminders are selected by Python
from eligible local, persisted events/commitments with cooldowns; no autonomous
model conversation.

## Plans

At most six exact-input steps, with dependencies/preconditions and interruption
boundaries. Recording a plan executes none of it. Continuation returns one next
step to player control; it cannot invisibly execute travel, stealth, deception,
wait for an unknown shift, or make irreversible choices. Existing action owners
resolve player-confirmed steps. New danger/combat pauses the plan.

## Generation, novelty and pacing

Only low-impact local campaign-specific seeds bound to existing local procedural
actors, locations and validated evidence routes may be accepted. No new lore
figures, faction leadership, unique artifacts, historical claims or invented
mechanical rewards. High-impact candidates fail closed.
Generation eligibility considers current open threads, recent generation, current
scene and structured themes/conflicts/motivations/objective routes/antagonists/
reward patterns/resolution styles. Python selects at most one eligible candidate
from the same call; all rejected means no retry. Ordinary talk may produce nothing.
Do not use model prose as novelty history or campaign truth.

## Time, persistence and call budget

Deadline evaluation consumes the existing Campaign Time elapsed_seconds after
resolved gameplay; it never advances time, schedules independent jobs or uses a
wall clock. Each accepted expiration is recorded once; closing/reopening does
nothing to the clock. Knowledge of occurrence remains separate from occurrence.
Explicit multi-step plans are interpreted before the single-action timed owner;
recording a plan containing a wait does not execute that wait.

Save, state projection and action receipt are committed by the existing campaign
transaction. Same action ID/request replays the original response before any
interpretation, roll, generation or time change. Different payload conflicts.
Save failure rolls the entire extension back with the existing engine snapshot.
Session/campaign state is never stored in module globals.

Maximum two calls: optional structured interpretation/proposals, then optional
bounded narration. Invalid proposals and unsafe narration fail closed to immersive
deterministic fallback. No third call, rewriting call or retry loop.

## Later-package boundaries

No full economy/loot/equipment, exploration/dungeon/travel, faction/reputation/
living-world simulation, magic or character progression. Transfers without an
existing transaction owner remain unavailable; objective routes consume existing
engine outcomes only. Locked combat/time/death/spell semantics stay intact.

## Acceptance matrix

1–2: owned-item counter-offer representation and non-owned transfer rejection.
3: non-authored personal goals.
4,6–7: alternate evidence routes, evidence-grounded reframing, missed clue.
5: voluntary allegiance change without rewriting faction truth.
8–10,17–18: filtered perspective, diegetic ignorance, fallible beliefs/claims,
private/public listeners and correct addressee.
11: impossible persuasion cannot force NPC compliance.
12–14: persistent commitments and receipt replay without duplicated events/seeds.
15–16: Campaign Time deadline exactly once and no wall-clock progression.
19–20: structured novelty rejection and same-call selection/no retry.
21–23: narration rejection, two-call ceiling, prose cannot author canon.
24–25: restart compatibility and campaign/session isolation.

Focused tests precede the existing bounded development regression. Live HTTP and
real authenticated Qwen are separate evidence; mocks never certify live behavior.
Final status must disclose exact remaining gaps and NOT RUN checks.

## Verification boundaries and practical limitations

Real-model verification found that optional interaction fields were silently
omitted, and unconstrained operation selection could replace a stated personal
goal with information or a promise with side switching. The response schema now
requires the envelope and original quote; an explicit coarse input hint constrains
the operation but not its arguments. Generic interpretation remains available.

Ordinary addressed conversation can produce its bounded narration in the first
call, while a state-changing proposal must be resolved before optional narration.
No response can inject world updates through this conversation mode.

Current emergent seeds are deliberately restricted to present procedural actors
and local talk/visit routes. They do not create new NPCs, locations, items, combat
tasks or rewards. Structured novelty is a bounded first version, not a claim of a
complete narrative generator or autonomous NPC simulation.

Broad investigation goals persist without automatically succeeding on an
unrelated conversation or arbitrarily selected fact. Narrow explicit action goals
may use canonical visit/talk/acquire/defeat outcomes. Rich predicate-aware
investigation completion and native rumor/belief creation need approved evidence
and perspective producers; fixture-only perspective tests prove consumption and
isolation, not native production of those records.

The existing Final Gate contains an infrastructure-only scope policy and demands
a clean Git tree. Authorized gameplay edits and intentionally uncommitted work
therefore cannot legitimately make that gate GO. Do not weaken its policy or
create commits to hide that result; report its NO-GO separately from test results.

## Review evidence and final decision

**INTERACTION & QUEST ADVENTURE V1 — COMPOUND PLAN P1 RESOLVED**

The earlier native composite plan failure was a P1 interpretation gap, not a
product-authority blocker. Earlier scene/time returns were repaired and the real
parser was proven to return an empty steps array; plan schemas now require a
nonempty steps field. Nevertheless the final authenticated HTTP/Qwen run of that audit
returned clarification instead of recording the plan. It executed no steps,
changed neither location nor Campaign Time, and performed one actual model call.
Do not report its HTTP 200 or unchanged restart of a missing plan as acceptance.

The native corpus did record a personal investigation goal, a whispered promise
and a local offered thread. The goal receipt replay returned the original response
without another state change; campaign resume retained the complete extension.
All temporary campaigns created by these probes were deleted, not user campaigns.

The full bounded development run before the last plan-only fixes passed 154 tests
(0 failures/errors/skips). Its retained suite evidence is
docs/evidence/development-runs/20261005T014135Z-f633663a29ea415e97f87c73e97815c2/run.json.
Final Gate evidence is
docs/evidence/development-runs/20261005T014135Z-3f460d8f71df4fd7b06835a3c022ba8e/run.json.
The gate remained NO-GO for its infrastructure-only scope and dirty-tree clauses.
All four frontend checks passed; frontend tests were 57/57.

After the last plan fixes, the changed-flow command passed 70/70, no skips:
python -m unittest api.tests.test_interaction_adventure
api.tests.test_campaign_time api.tests.test_bounded_encounter
test_narrative_rebalance.TestNarrativeRebalance.test_03_no_turn_exceeds_2_model_calls
test_narrative_rebalance.TestNarrativeRebalance.test_04_narration_validation_failure_does_not_retry_model
(run from ai-dnd). Do not describe the earlier full-run source hash as the final
source hash. No full-gate rerun followed those narrow final changes.

The frontend landing page was screenshot-checked; interactive browser journal
testing, native deadline/rumor/belief generation acceptance, and production
deployment verification were NOT RUN. General NPC item transfers, autonomous
rumor/faction simulation and broader investigation predicate producers remain
explicit later-owner boundaries. Native counteroffers do not grant items.

### Compound-plan correction — 2026-10-05

Complete first-person optative, future and present clauses separated by commas,
semicolons, newlines or sequence/conjunction markers can now be recorded from
exact player source spans. Quoted speech is opaque and noun lists/single searches
are not compound plans. This bounded grammar is not a general Turkish NLP parser;
other intentions retain the existing model interpretation path.

Plan routing precedes scene materialization, merchant search and non-combat
action dispatch. Explicit combat commands and active combat/death/reaction
owners retain their precedence. Recognized compound plans use Python extraction
and the unchanged strict envelope validator, not a second classifier or model
paraphrase. The only optional model call is existing post-resolution narration;
there is no retry. Conditions remain literal, unevaluated player text. Recording
does not execute any step, cast a spell, advance Campaign Time or consume RNG.
The saved cursor remains zero; unknown current-step conditions pause the plan.

Six added targeted tests cover source/condition grounding across different verb
forms, quoted speech and single-search exclusions, distinct rejection reasons
and existing size bounds, spell/combat dispatch boundaries, HTTP replay/resume,
rollback and session isolation. The final bounded command listed above passed
**76/76**, no failures/errors/skips. No full gate or frontend tests were rerun.

One real proxied HTTP example used the owner's exact vardiya/gizlice/kayıt odası
sentence. It recorded four exact-source steps with cursor zero and paused status.
Only public adventure, journal and turn-index fields changed; Campaign Time,
location and physical public state did not. Receipt replay and campaign resume
returned the identical plan. Running-server logs recorded one qwen3:8b call
(narration, not step extraction); replay made no model call. The disposable
campaign was deleted. The primary frontend landing page was screenshot-checked.
The retained, synthetic-input HTTP summary is docs/evidence/compound-plan-http.json.
Published deployment and interactive browser journal checks were not performed.

This resolves the bounded native plan P1; unknown conditions still have no
automatic predicate evaluator or executor. Inventory transfers and the other
documented later-owner boundaries remain unchanged.