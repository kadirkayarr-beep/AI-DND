# BM — Model first (önce model): design

Date: 2026-11-17. Owner go-ahead: Kadir, "Evet, başla" (2026-11-17). Scope source: `YENIDEN_TASARIM_PLANI_20261113.md` § "BM. Önce model" (K37, approved). Base: `origin/main` e94d81a3 (PR #121 merged).
Status: design for review. Kadir picks the approach (section 4); the plan (`docs/superpowers/plans/2026-11-17-bm-once-model.md`) is written for the recommended approach A.

Line numbers below are from e94d81a3 and are only hints; briefs name files and functions.

## 1. Intent and why

The player types a sentence; today, in conversation, Python word patterns decide what it means before any model reads it, and many of those patterns answer with a fixed sentence. The game then feels mechanical and sometimes answers a different question. K37 asks for the opposite order: the model reads the move first (`front_proposal`), Python checks the ids and applies the result, and the word patterns stay only as a backup when the model gives no answer.

Evidence:
- 2026-11-16 play: 11 of 28 moves ended in a ready-made Python sentence; on move 3 the model read "talk", the engine printed a shop line because the line had the word "dükkân" (`OYNAYIS_TANI_20261116.md`).
- 2026-11-17 play (`OYNAYIS_NOTLARI_20261117.md`), Kadir's priority order:
  1. B1: a question to Nivrek that names another NPC (Çarnuva) is answered with Çarnuva's whereabouts and job terms ("Teslim edene 15 bakır.") instead of the question. B2: a general place/rumour question gets "ben bilmem" from the NPC who told that rumour earlier.
  2. B3: the journal records something different from what was heard ("gerginlik" heard, journal says "vardiya öğünleri gönderilecek"; "kilitte taze çizikler" heard, journal says "buluşma değişikliği notu"); three generic "Söylediklerin konuşmada duyuldu." lines.
  3. B4: the sergeant does not know the roster detail the arrival narration showed ("Hangi çizelge?"). B6: at 17:10 the priest twice says "sabah duam". Repeated ready lines: "Dorin. Tamam." (two NPCs), "Nivrek burada; tezgâhı açık." (twice), "benim işim değil" / roster excuse (four turns).
  Also B5 (the steward does not mention the work he himself opened) and B7 ("Şehirden uzaklaşarak yol boyunca yürümeye devam ediyorum" stops on the caravan warning; "Yol boyunca ilerliyorum" walks on).

## 2. How it works today (verified in code)

- Conversation mode skips the model reading. `game._front_step`: when `interaction_mode in {"say","ask_dm"}` and the line names no coin and is not said to a vendor, it notes `skipped:typed` and returns None. Any line with a chosen `target_id` is skipped too. So in conversation the word patterns are the only decision makers (Codex verification §1.1, §2.1 B).
- Old chain after a skipped reading: several classifier calls exist (`parse_player_intent` call sites in `_run_player_turn_internal`: scene pre-parse, interaction proposal, query intent). The two-call cap is `api/ollama_adapter.MAX_MODEL_CALLS_PER_TURN = 2`.
- Front reading is one call (`front_proposal.schema`, inside `parse_player_intent(..., front_list=...)` under `api.model_phase.front_call`); it can already carry an interaction proposal. Local medians: reading 10.2 s, narration/speech 5.8 s; cloud call 1.7–2.5 s (plan §2c).
- `front_proposal.enabled()` is on only with `AI_DND_FRONT_PROPOSAL=1`; local play turns it on (`default_on_for_local_play`). When off, every path below is the only path.

### 2.1 Root causes found for the play findings

| Finding | Root cause (file: function) | Verified? |
|---|---|---|
| B1 | `game._thread_gate` → `world_threads.turn_gate` → `_speaks_of_work` / `_names_the_work`: word lists (`answer_table` work/reference/question terms, item stems) decide that a line to a job owner is "about the job", then the owner states `thread_catalog._owner_line` terms ("{recipient}, {target} içinde {package} bekliyor. Teslim edene {pay} bakır."). Naming the recipient's job/package words in a question is enough. | Path and sentence template read in code. Which exact word fired in the play: **not verified** (Task 4 red test pins it). |
| B2 | `town_knowledge.public_knowledge` orders: town item, threads (own job first), gone news, then `town_rumours.rumour_for` (a trouble first, then heard rumours), cap 10 items / 1500 bytes. The NPC's own spoken rumour is late and can be cut; a general question gets the first item (her own job line, as in T8). `heard_rumours.own_line` matches only when the player names the place, and is used only in `_town_fallback`. D-325: `historical_claim_denial` runs before `_town_fallback`. | Code read. Which cut happened in the play: **not verified**. |
| B3 | `town_knowledge.note_mention` marks a thread heard when the reply names the thread's **place** (`item["location_id"] in spoken`) or its **owner** (`_mentioned`), not when the reply carries its content. `quest_log._trail_rows` (block 4, `source="duyulan"`) then shows that thread's catalog `public_line`. So the journal shows whichever record shares the place, not what was said. The generic line is `interaction_adventure` `statement_heard` event summary "Söylediklerin konuşmada duyuldu.", copied to the journal as `adventure_event` (`api/campaign_journal.py`). | Code read; matches both play examples. |
| B4 | `game._experimental_npc_dialogue_context` gives `scene = living_world.visible_scene_facts` (location, people, features, nearby places). The arrival narration text the player read is not in the NPC prompt. | Code read. |
| B6 | Same context has no clock. Arrival narration gets `campaign_time.public_time` (`arrival_narration.facts` → `zaman`), NPC speech does not. | Code read. |
| "Nivrek burada; tezgâhı açık." | `game._run_player_turn_internal` shop presence branch: `_shop_presence_question` (shop word + any "?") asked of a shopkeeper returns this line, `action shop_inquiry`, no model. "satıcılar arasında ne dönüyor?" matches. | Code read. |
| "Dorin. Tamam." | `local_dialogue` INTRODUCTION pool (`python_memory_response`, 0 model calls) for name disclosure. | Code read. |
| "benim işim değil", roster excuse | Model text steered by `town_knowledge.speech_note` closed-mouthed branch ("kısa kes") plus `role_note`; nothing tells the model what it already said as a refusal. | Prompt read; model output **not verified** (no speech debug). |
| B5 | Unknown. `town_knowledge._job_note` / `is_closed_mouthed` / `inner_of` master are candidates. | **Not verified**; Task 6 red test decides. |
| B7 | `grounded_action.road_goes_on`: at an outdoor road place the first go-on line gets a fixed `_ROAD_ON` warning (status `not_now`, no move, `road_warned` set); only the next line walks. Front read "Şehirden uzaklaşarak…" as `go_to way_out`. | Code read. |

## 3. Goals, non-goals, anti-goals

Goals
- G1: In conversation (say/ask_dm, person chosen) the front reading runs; its reading decides which owner answers. Word-pattern owners run only when the reading is missing (model failed, flag off).
- G2: A question naming a third person is answered as a question to the addressed person (B1). A general rumour/place question gets the rumour that person told (B2, D-325).
- G3: The journal shows what was actually heard, from the NPC who said it; no generic "Söylediklerin konuşmada duyuldu." line (B3).
- G4: NPC speech knows the scene the player was shown on arrival and the time of day (B4, B6), and its own open work (B5).
- G5: Fewer repeated ready lines: name disclosure, shop presence and refusal phrasing come from the model when it answers (repeat table).
- G6: B7: leaving along the road is not stopped by a fixed warning line (owner decision K-BM-2).
- G7: Measured: route log records the narration source; "moves that end in a ready-made line" (money, dice, XP, purchase and rule lines excluded) is computed from it. Baseline 11/28 (39%). Target ≤ 10% in Kadir's next play.

Non-goals
- No new word or regex list to route intent (owner rule). Existing lists stay only as fallback.
- Money, dice, XP, purchase and rule refusals stay engine sentences (B2 scope, K37 "Sınır").
- No combat screen data (BS), no arrival prefix repeats ("Dışarı, Neverwinter sokaklarına çıkıyorsun." ×5, "Daha içeri açılan ağır bir kapı var") — parked to the arrival/A2 work; D-307, D-308 stay out.
- No old-save compatibility (owner rule).
- No browser tests.

Anti-goals (failure even if tests pass)
- A third model call in any turn.
- The model creating money, items, jobs or rewards (K2 minimal blocking: Python validates and commits).
- A turn that ends with nothing when the model fails: the old path must still answer.
- Longer local turns without the ready-line share going down (we pay latency for nothing).

## 4. Approaches

### A. Full front reading in conversation (recommended)
Every conversation line (except fight, slash, journey, hideout, "konuşmayı bitir") is read once by the front call. The front schema gets two fields: `about_person_id` (the person talked **about**, from the people list, or none) and `asks` (what the line asks: `place`, `rumour`, `work`, `person`, `shop`, `name`, `small_talk`, `other`, `none`). If `kind == "speak_to"` and no work/money decision is read, the NPC speech call answers with richer context; old word owners do not run. Work, coin, hand-over and offer answers keep their Python owners, now triggered by the reading (`job_id`, `kind`, `answer`) instead of words.
- Calls: reading (1) + speech or narration (1) = 2. If the reading fails, the old chain runs **without** its classifier calls (marked unusable), so speech is call 2.
- Cost: say turns that used 0 calls (name, shop presence, lore gate) or 1 call now use 2. Local: about +10 s on those turns; cloud: about +2 s (estimate from plan §2c, not measured for this change).
- Gain: one decision point, matches K37 literally, fixes B1 at the cause, removes most say-mode ready lines.

### B. Speech call reads and speaks in one
No front reading in conversation; the speech schema gets `asks`/`about_person_id`/`decision` fields and the reply is checked after. 1 call for plain talk.
- Problem: work/pay/accept decisions must be written **before** the NPC voices them (thread gate rule "Python writes the state; the model only voices the result"). Either word lists keep deciding those turns (against the owner rule) or the reply is checked after and repaired (the old unbacked-money pattern K2 removed). Not recommended.

### C. Model confirms only where a pattern fires
Old patterns run first as detectors; when one would print a fixed line, the front reading is asked to confirm; if it reads plain talk, speech answers instead.
- Cheaper (extra call only on pattern hits) and smaller diff.
- But the word lists still decide when the model is asked (K37 says they are only a backup), lines the patterns mis-route without a fixed line (B1 thread talk path is voiced by the model) are still mis-routed, and two systems must be kept in step. Acceptable fallback if Kadir rejects A's latency.

Shared by all three: context fixes (G2–G5 contents), journal fix (G3), measurement (G7), B7. Only the routing tasks (plan Tasks 1–4) differ.

Recommendation: **A**. It is the only one where the model's reading actually decides every conversation line, it fixes B1 at the cause, and the cost is bounded by the existing two-call cap. The latency cost is real on local Gemma; Kadir plays the acceptance gate on the cloud chain (K15), where it is about 2 s.

## 5. Design (approach A)

### 5.1 New module `ai-dnd/talk_front.py` (game.py split, owner-approved)
Holds the conversation routing that this work touches, moved out of `game.py`:
- `reads_say_line(session, player_input, target_id, interaction_mode, combat_action, check_feature) -> bool` — replaces the say/ask_dm skip rule inside `_front_step`.
- `old_owner_allowed(front: dict | None, owner: str) -> bool` — the single gate the say-mode word owners ask; True only when `front` is None (no reading), or the reading is not plain talk. Owner names are the fixed set in 5.3.
- `shop_presence_reply(world_state, npc_target) -> str` — the shop presence sentence builder moved from `_run_player_turn_internal` (behaviour unchanged when it runs).
- `work_reading(front, npc) -> dict | None` — what the reading says about this person's work (job id, decision kind), for `_thread_gate`.
`game.py` keeps thin call sites.

### 5.2 Front schema additions (`front_proposal`)
- `about_person_id`: enum of listed people ids + `none`. Python accepts it only if listed and different from the addressed `person_id`.
- `asks`: enum `ASKS = ("place", "rumour", "work", "person", "shop", "name", "small_talk", "other", "none")`.
- Both placed early in `required` (small models drop late fields), and the schema must still pass `model_chain._haiku_schema`. `guidance()` gets two short lines describing them (no word lists).
- Unknown/invalid values → treated as `none` (repair, not reject).

### 5.3 Paths: what becomes fallback (verified list, Codex verification §2.1)
Say/ask_dm, decided today without the model; with a valid reading of `kind == "speak_to"` and no work/money decision they do **not** run, the speech call answers:

| # | Path (file: function/branch) | Ready line today | After |
|---|---|---|---|
| 108 | `game._run_player_turn_internal` shop presence branch (`_shop_presence_question`) | "Burada … dükkânlar var." / "X burada; tezgâhı açık." | runs only when reading `asks == "shop"` or no reading |
| 121 | `local_dialogue.unresolved_named_address` branch | "Burada {ad} adıyla tanıdığın biri görünmüyor." | reading's `person_word` not in list → same truth line (rule line kept); otherwise speech |
| 122 | `local_dialogue` place-name question branch | topic name line | speech |
| 123 | name disclosure (`local_dialogue` INTRO pool, `python_memory_response`) | "Dorin. Tamam." | Python still stores the name; speech voices it; pool only on speech failure |
| 124 | personal questions (`local_dialogue` personal answer) | fixed answers | speech (profile facts already in context) |
| 125 | small talk (`game` smalltalk function, cümleler 17351/17361/17369 area) | fixed lines | speech |
| 126, 127 | quest availability / unaddressed work (`local_dialogue.quest_availability_question`, unaddressed work) | fixed lines | speech with job note |
| 128 | lore gate (`_unverified_lore_response`, `_WORLD_SUBJECT_TERMS`) | "unverified lore" lines | speech with town knowledge; lore line only fallback |
| 129 | `_thread_gate` talk (decision None) | owner terms / talk | decision only from reading (5.4) |
| D-326 | role + "kim var?" falls to scene list | scene list | speech (reading `asks == "person"`) |
| 101 | "konuşmayı bitir" | unchanged (engine command) | unchanged |

Kept as engine owners regardless (rule/money/state): coin and vendor lines (D0/D1), shop creation (109/110), ağır eylem questions (106), inventory in ask_dm (133, reading `kind == "bag"` also accepted), slash commands, combat words.

Do mode (free text, reading already runs): `everyday_actions.classify` is called independent of the reading (`game._dispatch_player_turn`, everyday call site) — it runs only when there is no reading or the reading is `unclear`. Dead code removed: `everyday_actions._PERFORM` and the `perform` branch in `resolve` (unreachable, Codex verification §1.3), `game._with_job_news` (D-326, unused). Other do-mode post-reading owners (bold_acts, pocket, grounded_action, interaction_adventure.hint 115–120) are out of this slice → parked with a debt row.

`dialogue_runtime.resolve_turn` runs before the say branch but only when `dialogue_runtime.is_enabled(world)` (campaign config mode). Ruling: Task 1 checks whether new local campaigns enable it; if yes, it gets the same `old_owner_allowed` gate; if no, it is listed as unreachable in local play (debt row), not changed.

### 5.4 Thread gate (B1)
`_thread_gate(..., front=...)` already receives the reading. With a reading present:
- a work decision exists only when `talk_front.work_reading(front, person)` returns one: `kind in {"work", "offer_answer", "hand_over"}` or `job_id` is a job of this person, or `asks == "work"` addressed to the job owner;
- `about_person_id` naming someone else never starts this person's job talk;
- `world_threads.turn_gate` word checks run only when the reading is missing.
Money paths (`pay`, `give`, `take_up`) keep Python validation exactly as today. This task touches money → Opus independent review.

### 5.5 NPC speech context additions (`game._experimental_npc_dialogue_context` → built in `talk_front.speech_extras(world, npc)`)
- `zaman`: `{"gun": day_index, "vakit": dawn/day/evening/night word, "saat": "HH:MM"}` from `campaign_time.public_time`; prompt line: speak consistently with this time.
- `sahne_anlatimi`: the last arrival narration shown at this place, ≤ 600 chars, labelled "the player was shown this; you are here; do not deny what is in it, you may add little". Stored at arrival in `world["scene_state"]["arrival_text"] = {"place_id", "text", "turn"}` (one entry, replaced on each arrival). New key gets its default in `INITIAL_WORLD_STATE`; Undo works because it is world state (snapshot). Touches saved state → Opus review.
- `kendi_sozlerin`: this NPC's own heard rumours (`heard_rumours` entries where `town_rumours._spoke`), text with claim, first.
- `kendi_isin`: this NPC's own open/offered job public line and terms (already validated thread data), so the owner says it when asked about work (B5).
- `son_sozlerin`: the NPC's last 3 replies (from `npc_speech_log`) with "do not repeat the same refusal or excuse" (repeat table).
- `town_knowledge.public_knowledge`: own spoken rumours ordered before threads; `rumour_for` puts own heard rumours before a foreign trouble (B2). D-325: `heard_rumours.own_line` checked before `historical_claim_denial`.

### 5.6 Journal (B3)
- Speech schema gets `voiced`: enum of the knowledge item keys listed in the prompt (`k1`..`k10`) + `none`, array max 3. `speech_note` lists items as `k1: text / k2: text`.
- `town_knowledge.note_mention` marks a thread or rumour heard only when (a) it is in `voiced` **and** the reply carries at least half of the item's own words (`town_rumours.was_voiced` rule, generalized to threads), or (b) `voiced` is missing and (a)'s word overlap holds. Naming a place or owner alone never marks anything.
- `quest_log` heard-rumour trail shows the `heard_rumours` text ("Ad: iddia") and the speaker's public name; a thread trail keeps its public line (it was really voiced now).
- The `statement_heard` event stays in `interaction_adventure` state but is no longer copied into the journal as "Söylediklerin konuşmada duyuldu." (decision K-BM-4).
Journal is saved state → Opus review.

### 5.7 B7 road warning
`grounded_action.road_goes_on`: when the reading is `go_to way_out` with timing now, the first time the warning is said and the walk happens in the same turn (warning sentence + the normal walk result). Owner decision K-BM-2; if "no", B7 stays as designed (warn once) and Task 9 is dropped.

### 5.8 D-324
`arrival_narration.narrate`: when the Python entry fills the return budget (budget 0), no model call is made and the source is written `python`. Saves a wasted call and keeps the measure honest.

### 5.9 Measurement
- `front_proposal.log_turn` adds `narration_source` (from the turn's engine telemetry, the same value `campaign_history_sources` stores) and `model_calls`.
- `front_proposal.ready_line_share(rows) -> dict` counts rows whose `narration_source` is engine/Python (`deterministic_*`, `python_*`) and whose `owner` is not in `ENGINE_OWNERS` (money, dice, XP, purchase, rule: `shop_economy`, `death_save`, `character_query`, combat owners — exact set fixed in Task 11 from route-log owners), over all player rows. Kadir's next play is measured with it; target ≤ 10%.

## 6. Call budget per turn (approach A)

| Turn | Call 1 | Call 2 |
|---|---|---|
| Conversation, plain talk | front reading | NPC speech |
| Conversation, job accept/pay | front reading | NPC voices the Python result |
| Conversation, reading failed | (failed reading counts) | NPC speech; old classifier calls skipped |
| Flag off | old chain unchanged | |
| Do mode | unchanged (reading + narration) | |
| Go to place | reading | arrival narration (none when D-324 budget 0) |

A test pins "≤ 2 calls" for each row (`MAX_MODEL_CALLS_PER_TURN`).

## 7. Constraints
- ≤ 2 model calls per turn; no new word/regex routing lists; model proposes, Python validates and commits; old path only as fallback.
- Every new-campaign test pins the town (`api/tests/town_seed.fixed_town`; journeys `campaign_seed`).
- Neighbour set in every task: `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys`.
- Tasks touching money (thread gate), saved state (scene_state, journal) or Undo: independent Opus review. No fable.
- Tests that pin old ready lines are rewritten at equal strictness, marked "gevşetme olabilir", added to the approval list.
- Both `AI_DND_FRONT_PROPOSAL` on and off are tested for each routing change.
- No browser tests; touched routing code moves to `talk_front.py`.

## 8. Left to the builder (rulings made here)
- Ruling: module name `talk_front.py` — short, matches `front_proposal` — wrong name costs a rename.
- Ruling: `asks` enum as in 5.2 — covers the play's questions — a missing value costs one schema edit.
- Ruling: one stored arrival text, not a history — enough for B4 — a longer history costs one more key.
- Ruling: builder check by subagent skipped (token limit); the author re-read the doc as a builder — a missed question costs one round with Kadir.

## 9. Review Focus (for reviewers)
1. Reading present but wrong (model says `speak_to` for "5 altın veriyorum"): coin/vendor rules must still win (D0/D1 run before the gate).
2. Reading fails mid-turn after the call was counted: the turn still answers within 2 calls, no exception reaches the player.
3. `about_person_id` equal to the addressed person or not listed: ignored, no crash, no third-party lookup.
4. Undo after a turn that stored `arrival_text`, marked a rumour heard, or wrote a journal trail: all three return to the earlier state.
5. A line to a job owner that both asks something and accepts the job ("Tamam yaparım, Çarnuva nerede?"): accept is written once, the question is answered, no duplicate terms line.

## 10. Owner decisions (Kadir; yes/no)
Kadir answered all five "yes" on 2026-11-17 ("Hepsine evet"). The design is approved for implementation.
- K-BM-1: Approach A (every conversation line is read by the model first; local turns about +10 s, cloud about +2 s).
- K-BM-2: B7 — the road warning is said and the walk happens in the same turn.
- K-BM-3: NPC speech gets the arrival narration text the player saw (≤ 600 chars).
- K-BM-4: The generic "Söylediklerin konuşmada duyuldu." journal line is removed.
- K-BM-5: Target for the next play: ready-line moves (money/dice/rule excluded) ≤ 10%.

## 11. Not verified
- Which word fired in B1; why B2's rumour was missing in the play; B5's cause; whether `dialogue_runtime` is on in local play; the latency figures for this exact change; model behaviour with the new fields (small local model may fill `asks` poorly — measured in play).
