# Single master prompt — PLAYABLE LIVING WORLD V1

Implement one coherent, bounded **Playable Living World V1** phase in this AI-DND project. This is an implementation request, not another proposal-only phase or a series of disconnected prompt patches. Fix ordinary gameplay from player input through durable world state and player-facing narration while preserving Forgotten Realms canon authority.

The desired experience is that a player can look around, enter a tavern, see people, approach the bartender, ask a name, sit at a table, leave, notice street activity, approach a guard, return to a familiar person, and resume after a server restart without empty-state/debug answers, disappearing people, identity drift, or invented canon. The player must not need implementation commands such as “create one campaign-local shop.”

## Baseline and scope

Inspect the current checkout before editing. The reviewed V13 `ai-dnd/game.py` SHA-256 was `463b0d9b1a8079b37744f6535748358af50bee6dfca7180de68560fcf89a18cb`. If HEAD differs, map the differences and adapt to the current implementation; do not overwrite newer work or restore a historical backup. Read applicable repository instructions and preserve user work. Keep historical reports/checkpoint manifests unchanged. Produce a new phase report and hashes.

Known V13 findings to reproduce before fixing:

- `_handle_query` answers presence from the existing list and returns before materialization. Ordinary looking and approaching do not enable `should_generate_npcs/features`; even “Bir tüccar arıyorum” misses the narrow search gate.
- An accepted “Kapıda isimsiz bir muhafız bekliyor” can leave no NPC or resolvable scene referent. Narrative memory omits narrator prose and strips temporary texture; there is no validated promotion path.
- General NPC updates reject merchant roles; shop creation requires explicit setup and enforces a global one-shop ceiling. Feature proposals can be discarded because a table description mentions a cup.
- `_LORE_UNSUPPORTED_DETAIL_PATTERNS` treats local “demirci” and “iki gün” language as unsupported canon. A valid local NPC proposal can be rolled back solely because “Rana demirci olarak çalışır” appears in narration.
- Player narration includes `UNVERIFIED`, “kayıtlı NPC”, “Python world state”, and equivalent no-op explanations. The frontend displays these strings directly.
- Narration and world proposals arrive together, but the prompt tells Qwen not to narrate new entities before approval; there is no explicit accepted-reference rendering contract.
- Lore is retrieved before travel resolves. Locations lack a coherent local parent/exit relationship; initial canon locations are unmaterialized. World metadata alone does not provide scene activity or revisit continuity.

Verify these against the current checkout. Do not reintroduce already-fixed cup/atmosphere false positives or treat historical smoke failures as proof of current behavior without reproduction.

Allowed implementation files, only where necessary for this phase:

- `ai-dnd/game.py`: turn orchestration, mundane intent/action handling, scene hooks, reference resolution, proposal validation, narrator contract, fallback rendering, bounded save/migration integration. Do not rewrite unrelated character, dice, combat or quest mechanics.
- New focused modules `ai-dnd/living_world.py` and, if useful, `ai-dnd/scene_contracts.py`; prefer small explicit components over extending the monolith with many special-case regexes.
- `ai-dnd/api/main.py`, `session_manager.py`, `narrative_director.py`, `narrative_memory.py`, `world_metadata.py`, `campaign_journal.py`, `schemas.py`, `serializers.py` for integration, public projection, transactional snapshots and continuity.
- `ai-dnd/api/persistence/{campaign_models,campaign_serializer,campaign_store,campaign_validation}.py` for bounded validated scene persistence/migration/rollback only; prefer the existing campaign envelope and SQLite transaction.
- `ai-dnd/api/lore_authority/{registry,campaign_state,models}.py` only for scoped retrieval/local-reference integration when demonstrably needed; preserve provenance, review, source priority, visibility, epoch and conflict rules.
- `ai-dnd/api/ollama_adapter.py` only for necessary request-context/diagnostics integration, preserving model/authentication/call limits.
- `ai-dnd/test_playable_living_world.py`, relevant existing regression tests, `ai-dnd/api/tests/` tests including a new `live_playable_living_world_smoke.py`, and `ai-dnd/run_tests.py` to include the new deterministic gate.
- `artifacts/ai-dnd-experience/src/pages/game-browser.tsx`, directly affected components/types, its tests and package test command: clear player language and display/use server-approved scene data. No UI redesign.
- `lib/api-spec/openapi.yaml`, necessary generation config, regenerated `lib/api-client-react/src/generated/` and `lib/api-zod/src/generated/` outputs. Use codegen; do not manually diverge generated contracts.
- New phase report and sanitized smoke evidence files under an existing appropriate report directory or `ai-dnd/`.

Read root config/checkpoints, but keep deployment/authentication, dependency versions and lockfile unchanged unless a concrete required change is separately approved. Do not edit source packs, extraction/review logs, old engine backups/manifests, `artifacts/ai-dnd-web`, mockup-sandbox, unrelated api-server/db code, or existing user campaign data. Do not publish/deploy, migrate the production database, or clean up users' campaigns as part of this request.

## Required design and invariants

Implement a single explicit per-turn pipeline. It must cover early direct-response paths as well as Qwen paths. Suggested order: resolve intent and target → plan destination/scene → materialize/reuse needed local scene data → retrieve relevant lore/continuity → request narration/proposals → validate staged changes → finalize against accepted references → persist atomically → publish response. If resolution requires staged proposals, handle that within the same bounded transaction. There must be no third model call or hidden model repair loop.

Keep four distinct authority classes:

1. **Verified setting canon:** reviewed Forgotten Realms entities/facts, source provenance, epoch/region validity, secrecy and conflict resolution. Model memory is never a source. Unknown official lore stays unknown. Existing approved campaign overrides remain separate and must not be manufactured by narration.
2. **Persistent campaign-local fiction:** ordinary people, local establishments, significant features, supported relationships and local consequences. Python owns stable IDs, validation, location membership and commit. These are campaign facts, not additions to the official lore registry. Use existing `PROCEDURAL_LOCAL_FICTION` semantics where possible.
3. **Bounded scene referents:** anonymous background people/objects presented as potentially interactable. Store a scene-scoped handle, description/aliases, location, source turn, lifecycle and promotion link. A referent shown to the player must be resolvable on follow-up. Promote only accepted presented referents or an explicitly permitted new local encounter; never arbitrary player assertions.
4. **Ephemeral atmosphere:** sounds, smells, light, gestures and anonymous population texture. No automatic mechanics, ownership, lore discoveries or quest facts. Pure atmosphere need not receive persistent entity IDs.

Named/addressable recurring people and significant interactable objects must be registered before their final narration is delivered. For other addressable background details, accepted scene handles provide continuity until promotion. Never recover authoritative entities by blindly mining old raw narration, browser text, or model summaries.

Python must continue to own HP, AC, dice, skills/DC, attacks/turn order, inventory, doors, quest outcomes and rewards. Do not alter Combat V3 rules, invent XP/spells/economy, give items through descriptive prose, or grant results because a player asserts them. Keep session isolation, RNG determinism, bounded memory and secret filtering. Keep `qwen3:8b`, at most two model calls per turn, and the existing context/token ceilings. Do not solve quality problems by increasing calls/tokens or weakening guards globally.

### Scene lifecycle and normal actions

- Add an idempotent `ensure_scene`/equivalent with explicit triggers: campaign entry or first look, successful arrival, presence query, relevant local search, and attention to an already-presented referent. Address absence before answering presence; no circular “nothing exists until you ask to create it.”
- Materialize a small coherent scene appropriate to location type and verified constraints. A staffed tavern should expose a host/bartender and usable ordinary furnishings; a city street should expose plausible activity and approachable locals. Quiet/empty wilderness is valid. Do not populate every scene or invent canonical celebrities.
- Use stable, campaign-scoped IDs, generation/revisit metadata, bounded counts, deduplication and reproducible identity. Preserve existing NPC limits or replace them with an equally explicit bounded policy. Revisiting must reuse identities; repeated looking must not endlessly spawn NPCs.
- Support mundane observe, approach, talk, sit/stand, wait briefly, enter and exit/return semantics. Distinguish moving within a scene from changing locations. Clear harmless player-chosen actions may succeed without unnecessary dice. Ambiguous targets need a short contextual clarification; multiple similar NPCs must not merge.
- Resolve Turkish case/tense variants and role/deictic references using structured context: “barmene”, “şu muhafız”, “kapıdaki adam”, “ona”, “aynı masa”, “dışarı”. Test actual variants; do not expand an unbounded regex patch list.
- Give local places a scoped anchor/parent and explicit return/exit relationship sufficient for city → local tavern → city. Preserve legacy location IDs/saves and valid travel semantics; do not invent official distances, intercity routes or transport mechanics.
- Remove the accidental global one-shop restriction as a general world-population policy. Allow bounded ordinary merchants and establishments without activating prices, stock, money or transactions. Preserve explicit negative creation requests. This authorizes local population behavior, not an economy engine. A factual inventory/character query must not create unrelated entities.
- Store a minimal local activity/visit revision and meaningful persistent local changes so waiting and returning can produce context-sensitive behavior. Use canonical time/weather when available; do not add a global calendar, weather simulator, NPC scheduler or faction simulation. A small committed local scene beat is sufficient for V1; unsupported mechanical changes stay unsupported.

### Proposal, canon and narration contract

- Make new proposal references explicit (e.g. temporary proposal keys mapped to Python IDs). Validate a staged scene before final display. The final prose must not mention a rejected entity as real. Use accepted references and bounded deterministic rendering/repair when needed, without extra Qwen calls.
- Do not send contradictory “propose this now but don't mention it until a later approval you cannot see” instructions. Tell Qwen exactly which existing entities, provisional references and authority classes it may use, and which changes Python may accept.
- Evaluate canon claims by their entity scope and supported relation, not merely the presence of “demirci”, “gümüş”, “iki gün”, a capitalized occupational word or a harmless causal phrase. A local blacksmith's occupation is not evidence of Neverwinter's official industrial specialization. A personal statement is not verified setting history. Record NPC speech as speech; commit stable local characterization only through the appropriate validated path.
- Preserve strict rejection of fabricated rulers/deities/canonical cities, unsupported official routes/distances/history, hidden knowledge leaks and invented past conversations. Check that local naming cannot impersonate a canonical entity or launder a setting-level claim via a local profile. Mere inclusion of a valid fact ID is not proof that the sentence expresses that fact.
- Refresh scoped lore for the resolved destination/current canonical anchor and resolved speaker when necessary, before narration; do not carry only stale pre-travel context. This is local retrieval, not another LLM call. Avoid dumping the whole pack on ordinary turns. Preserve source/visibility boundaries.
- Permit natural NPC invitations, questions and reactions. An offer is not player acceptance, an item transfer or a payment. Never force player dialogue, beliefs, actions or objectives.
- Preserve safe parts when one independently invalid clause/proposal can be removed. If removal would leave an unsupported action, entity reference or contradiction, regenerate the final surface deterministically from the accepted scene/action. Preserve valid independent local materialization only when its validation is independent of the rejected canon claim; invalid dependent proposals must not survive.
- Fallbacks must be contextual Turkish prose with a useful answer or next affordance. No `NO_STATE_CHANGE`, `UNVERIFIED`, “Python/world state”, “kayıtlı NPC”, proposal validation, schema, implementation-version or state-diff language in the story. Do not replace errors with false success. Keep failures and unsupported actions honest, concise and in context. Server logs may retain internal reason codes.
- Do not use one generic no-change sentence for unrelated normal actions. Repetition handling must not collapse into the same fallback repeatedly. Player-facing UI empty states should use natural language and distinguish present people from previously encountered people; the frontend must not invent missing entities or rewrite rejected facts into accepted narration.

### Memory, persistence and atomicity

- Preserve stable NPC identity, dialogue target, explicit name disclosures, supported relationship changes, local scene changes, promoted features and location anchors across travel and real process restart.
- Maintain separate speaker-attributed player/NPC speech, accepted scene referents, local committed facts and setting lore. A player's claim “I already told Elara my name” is not evidence. An unregistered Elara must not acquire false history. No cross-NPC memory transfer.
- Do not re-enable raw narration as mechanical authority. Retain just the bounded accepted presentation references needed for follow-up, with explicit expiration/promotion rules. Expired or ambiguous referents need truthful resolution, not arbitrary creation. Persist currently relevant handles so a resume does not strand the last visible scene.
- Add stable IDs for significant features and migrate legacy feature records deterministically if required. Ensure serializers/OpenAPI/client/Zod/persistence agree on the new public contract; keep private memory, seeds and diagnostics private.
- Extend full rollback to scene state, handles, IDs/counters, RNG, active target, memories, lore refs, journal and transcript effects. A validation/storage failure must not leave partial scene generation or consume identities inconsistently. Autosave the accepted turn and narrative together in the existing transaction before delivery. Keep backward-compatible legacy save loading; version/migrate only where necessary and test repeat loading for idempotence.

## Test plan and release gates

First reproduce current failures with deterministic tests. Preserve existing mechanics/canon coverage. Update only tests whose narrow former product policy is deliberately superseded here (such as globally one shop or permanently empty presence); document each changed expectation and keep its original safety intent covered. Do not delete failing safety tests to obtain PASS.

Required new deterministic/integration cases:

- Fresh canon-bound city first look/presence; tavern first entry; empty/quiet scene; missing or rejected Qwen proposals still yield a truthful usable scene.
- Follow-up to a previously displayed anonymous guard; promotion exactly once, name/role/appearance/parent preserved; two similar guards clarify; absent unsupported person does not gain fabricated history.
- Ordinary table/cup descriptions permitted, meaningful table/feature stable through revisit and resume; no inventory transfer from props.
- Natural merchant search, multiple bounded local merchants/locations, negative creation requests, no purchase/currency/stock implementation.
- Harmless “demirci”/personal dialogue versus unsupported citywide specialization; canon-name collision; false ruler/deity/city/route; fake lore citation; wrong epoch; secrets and unresolved source conflict.
- Mundane approach/sit/wait/exit, no unchosen action or needless roll; in-scene actions do not teleport the player.
- Mixed response with one rejected proposal/clause; no rejected named entity on screen, no partial dependent commit; no repeated generic fallback.
- Existing NPC name disclosure/recall, wrong NPC false recall, travel/return continuity and a process restart with the last presented scene still usable.
- Save migration, corrupt/oversized scene input, rollback on model/validation/autosave failure, per-session isolation, deterministic IDs/RNG, bounded scene memory, ≤2 model calls.
- Destination-scoped retrieval, public contract parity, actual frontend rendering of narration and server scene state together, reload/resume.

Run the existing authoritative commands in the project's normal Python 3.13/Replit environment:

```sh
cd ai-dnd
python run_tests.py
python -m unittest test_narrative_safety_calibration
python -m unittest discover -s api/tests -p 'test_*.py'
```

Also run the new focused living-world suite. From workspace root run contract codegen if changed, `pnpm --filter @workspace/ai-dnd-experience test`, its typecheck, relevant library typechecks, and its production build with valid `PORT`/`BASE_PATH`. Inspect missing `scripts/` prerequisites rather than weakening workspace configuration. Run `git diff --check`. Do not use root-wide Python unittest discovery as the sole gate: legacy import-time/stdout behavior is documented.

### Mandatory real Qwen playability smoke: 36 turns

Use the real authenticated API, actual `qwen3:8b`, a new disposable SQLite database and a new Neverwinter/The North/1501 DR campaign. No preseeded bartender/guard/feature fixtures in this live run; those must arise through the implemented normal flow. Never touch the shared campaign DB. Record the actual dynamic NPC/place IDs and use those names in follow-ups. Do not hardcode expected generated names.

Complete these 36 meaningful turns, adapting only referential names to actual outputs:

| Turns | Required player experience |
|---|---|
| 1–6 | First ordinary look; who is here; approach a visible local; greeting/name; explicit player-name disclosure; ordinary small talk. |
| 7–12 | Find a nearby local tavern through normal play; enter; look; who is inside; approach bartender; ask bartender's name. |
| 13–18 | Ask about their day; sit at a presented table; inspect a harmless feature; notice addressable background activity; approach/promote that referent; follow up using a pronoun/role. |
| 19–24 | Leave to the anchored street; observe current activity; approach an actually displayed guard; ask an ordinary local question; return to the same tavern; recall the same bartender/table and any committed local change. |
| Restart | Save and terminate the API process, start a fresh process on the disposable DB, resume the same campaign. Assert IDs, locations, scene state, references, memory, history and lore binding before continuing. |
| 25–30 | Continue referring to the pre-restart scene; recall the disclosed name with the correct first NPC; test false recall with a different NPC; find an ordinary local merchant; converse without requesting engine setup; ask to purchase and receive an honest contextual limitation without invented transaction. |
| 31–36 | Ask a loaded canon question; ask an unsupported official route/distance; challenge with an invented ruler/deity; ordinary look after the rejection must still be playable; perform a meaningful supported Perception/Investigation interaction; wait briefly and revisit/check local continuity. |

Exercise existing combat preservation through deterministic/integration tests. Do not manufacture a hostile canon NPC merely to claim this normal-life smoke includes combat. If a real suitable local participant arises, an additional controlled disposable combat check may be reported separately without replacing the 36-turn scenario.

Capture sanitized evidence per turn: input, resolved action, scene and target IDs, accepted/rejected proposal categories and reasons, created/promoted/reused IDs, relevant pre/post state changes, selected lore fact IDs, memory evidence IDs, model-call count, token usage, safety action and exact final narration. Keep credentials, full prompts, private memories and withheld secrets out of logs. Include the resume comparison. Manually review every final answer in addition to automated assertions.

PASS requires all of the following:

- All mandatory regression, contract, build and living-world checks pass; 36/36 real turns complete and restart/resume succeeds.
- Zero fabricated official canon, secret leaks, false player actions, mechanical contradictions, false historical memory or unsupported transactions in final output.
- Zero narration-only named/addressable recurring entities; every such reference resolves to accepted entity/scene data. At least one genuine background-referent promotion, one persistent feature, one merchant encounter, and stable tavern/bartender/guard encounters are demonstrated.
- Zero implementation/debug fallback phrases in player story text. Every ordinary action receives an appropriate response; looking around must not be answered solely as an empty registry query in a scene intended to be inhabited.
- Correct identity and relevant scene consequences across repeated looks, travel, return and real restart; no duplicate entity explosion or cross-NPC memory leakage.
- ≤2 model calls on every turn, no increased token budget, no hidden retries. At most two unplanned whole-response safety replacements among the 31 ordinary-play turns (all except 27 and 30–33). Deterministic grounded identity/canon answers, intentional safety challenges and truthful unsupported-economy responses are not unplanned safety replacements. Classify the reasons explicitly; do not relabel degraded fallbacks as intentional to pass. Turn 34 specifically tests recovery into ordinary play after a canon refusal.
- No two consecutive ordinary turns collapse to the same generic non-answer. A human review confirms coherent purpose, reactions and player choice, not merely random decorative details or a roster dump.

Any violated invariant is FAIL. Missing credentials, unavailable model or inability to run the real smoke is **BLOCKED / LIVE PLAYABILITY UNVERIFIED**, never PASS. Preserve failures and retest evidence separately; do not edit the history of failed runs. A mechanical-only PASS is not release approval.

## Completion and approval boundary

Complete the bounded implementation and verification above, then provide: concise architecture/change summary; changed files and why; invariant checks; exact test results; the sanitized 36-turn transcript/evidence with manual judgments; post-restart comparison; remaining limitations; new checkpoint hashes; and an honest PASS/FAIL/BLOCKED disposition. Explain superseded narrow test expectations explicitly. Do not leave the core fix as TODOs or claim completion solely because unit tests pass.

This prompt authorizes the narrow living-world changes described above, including the necessary `game.py` touchpoints; do not repeatedly ask approval for those routine implementation choices. **Before broader engine changes, stop and obtain explicit user approval.** Broader changes include Combat V4 or altered combat math/initiative, spells, XP/leveling, economy/inventory redesign, quest/faction engines, global calendar/weather/NPC scheduling, new official lore/source packs/regions, multiplayer, authentication/deployment changes, higher model-call budgets, or unrelated engine rewrites. If such a dependency seems necessary, finish independent in-scope work, present the concrete problem, smallest proposed change, affected files, invariant/test impact and alternatives, then wait. Do not silently cross that boundary or disguise a broader feature as scene materialization.
