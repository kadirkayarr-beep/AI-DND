# BM — Model First Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every implementer prompt includes `docs/agents/implementer-preamble.md` and names the skills it must load (superpowers:test-driven-development, superpowers:verification-before-completion). If `graphify-out/graph.json` exists in the worktree, run `graphify query "<question>"` before the first grep or source read for a code question.

**Goal:** In conversation the model's front reading decides who answers and how; old word patterns answer only when the reading is missing; NPC speech gets time, scene and its own words; the journal shows what was heard; the ready-line share is measured.

**Architecture:** A new module `ai-dnd/talk_front.py` owns the conversation routing that this work touches (moved out of `game.py`). `front_proposal` gains two reading fields (`about_person_id`, `asks`). Say-mode word owners ask one gate (`talk_front.old_owner_allowed`). Context additions are built in `talk_front.speech_extras` and merged into `game._experimental_npc_dialogue_context`.

**Tech Stack:** Python 3, unittest, fake model doubles (`api/tests/test_experimental_npc_dialogue.ScriptedNpcSpeechClient`, `api/tests/test_front_proposal.FrontClient`), HTTP turn tests in the style of `api/tests/test_addressed_lines.py`, journey runner (`api/tests/journeys`).

**Spec:** `ai-dnd/docs/superpowers/specs/2026-11-17-bm-once-model-design.md` (approach A; Kadir decisions K-BM-1..5 open). If Kadir picks C, Tasks 1–4 are rewritten; Tasks 5–12 stay. If K-BM-2 is "no", drop Task 9. If K-BM-4 is "no", drop Step 7.4. If K-BM-3 is "no", drop `sahne_anlatimi` from Task 6.

**Branch/worktree:** `task/bm-once-model-20261117` in `C:\Users\Kadir\Desktop\AI-DND-k2-bm` (from origin/main e94d81a3). Parallel tasks get their own worktree from this branch tip, one writer each, own slot. Ledger: `.superpowers/sdd/2026-11-17-bm-once-model/progress.md`.

## Global Constraints

- At most 2 model calls per turn (`api/ollama_adapter.MAX_MODEL_CALLS_PER_TURN = 2`).
- No new word/regex list routes intent. Existing lists run only when the reading is missing.
- Model proposes, Python validates ids and commits; invalid reading values are repaired to `none`, not rejected.
- Money, dice, XP, purchase and rule refusals stay engine sentences.
- Haiku schema: new front/speech fields must pass `model_chain._haiku_schema`; no `temperature` change.
- Every new-campaign test pins the town: `api/tests/town_seed.fixed_town` (journeys: `campaign_seed`).
- Routing tests run with `AI_DND_FRONT_PROPOSAL=1` and with it unset.
- Tests only through the slot runner (Git Bash): `bash C:/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh <slot> AI-DND-k2-bm test <label> <timeout> <modules...>`; every run adds `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys`.
- Tests pinning old ready lines are rewritten at equal strictness, marked "gevşetme olabilir", added to `docs/agents/onay-listesi-20261115.md`.
- No old-save migration; new world keys get defaults in `INITIAL_WORLD_STATE`.
- Off-task bugs go to `docs/agents/debt-register.md` as park rows, not fixed in passing. No browser tests. No fable model.
- Opus independent review for Tasks 4, 6, 7 (money, saved state, journal, Undo); Opus whole-branch review at the end.

## Review Focus

1. A conversation line with coin ("Al şu 5 altını, Çarnuva nerede?") while the reading says `speak_to`: coin rules still win → test in Task 1 (`test_coin_line_still_goes_to_money_owner`).
2. Reading fails after the call was counted: still ≤ 2 calls, an answer is shown → Task 1 (`test_failed_reading_skips_old_classifier`).
3. `about_person_id` equal to the addressee or not listed: ignored → Task 1 (`test_bad_about_person_is_none`).
4. Undo after a turn that stored arrival text, marked a rumour heard and wrote a trail → Task 6 (`test_undo_drops_arrival_text`), Task 7 (`test_undo_drops_heard_trail`).
5. Accept-and-ask in one line to a job owner: accept written once, no repeated terms line → Task 4 (`test_accept_and_question_once`).

## Parallel map

| Wave | Tasks (own worktree each) | Files | Why safe |
|---|---|---|---|
| 1 | T1 | `talk_front.py` (new), `front_proposal.py`, `game.py` | only writer of game.py in wave 1 |
| 1 | T5 | `town_knowledge.py`, `town_rumours.py`, `heard_rumours.py` | no overlap with T1/T9/T10 |
| 1 | T9 | `grounded_action.py` | no overlap |
| 1 | T10 | `arrival_narration.py` | no overlap |
| 2 (serial) | T2 → T3 → T4 → T6 → T7 → T8 | all touch `game.py` / `talk_front.py` | one writer |
| 2 (side) | T11 | `front_proposal.py` (+ `game.py` call site only if Step 11.3 needs it) | after T1; parallel with T2–T8 only if it does not touch game.py |
| 3 | T12 | whole branch | slice end |

Merge order of wave 1: T1, then T5/T9/T10 (rebase on T1 tip). T6 needs T5 and T10 merged. T7 needs T5 merged.

## Model per task

| Task | Implementer | Review |
|---|---|---|
| T1 routing core | sonnet | opus (turn-flow centre, K37) |
| T2, T3 say owners | sonnet | sonnet |
| T4 thread gate (money) | sonnet | opus, independent |
| T5 own words first | sonnet | sonnet |
| T6 NPC context + stored arrival text | sonnet | opus, independent (saved state, Undo) |
| T7 journal | sonnet | opus, independent (saved state, Undo) |
| T8, T9, T10, T11 | sonnet | sonnet (T9/T10 red-green small: review may be skipped with a ledger Ruling) |
| T12 whole branch | — | opus |

---

### Task 1: Front reading in conversation (`talk_front` core)

**Files:**
- Create: `ai-dnd/talk_front.py`
- Modify: `ai-dnd/front_proposal.py` (`schema`, `guidance`, new `ASKS`, validation of the reply), `ai-dnd/game.py` (`_front_step` say/ask_dm skip rule; old-chain classifier skip after a failed reading in `_run_player_turn_internal`)
- Test: `ai-dnd/api/tests/test_talk_front.py`

**Interfaces:**
- Produces: `talk_front.reads_say_line(session, player_input, target_id, interaction_mode, combat_action, check_feature) -> bool`; `talk_front.is_plain_talk(front: dict | None) -> bool` (True when `kind == "speak_to"` and no `job_id`, no coin, `answer == "none"`); `talk_front.old_owner_allowed(front: dict | None, owner: str) -> bool`; `front_proposal.ASKS = ("place", "rumour", "work", "person", "shop", "name", "small_talk", "other", "none")`; reading dict keys `about_person_id: str` ("none" when absent/invalid), `asks: str`.
- `OWNERS` (in `talk_front`): `"shop_presence", "unknown_name", "place_name", "name_disclosure", "personal", "small_talk", "quest_availability", "unaddressed_work", "lore_gate", "thread_talk", "role_person_list"`. `old_owner_allowed(front, owner)` is True when `front is None`, or not `is_plain_talk(front)`, or (`owner == "shop_presence"` and `front["asks"] == "shop"`).

- [ ] **Step 1.1: Write failing tests** in `test_talk_front.py` (HTTP style of `test_addressed_lines.py`, `fixed_town(self, 4171)`, `FrontClient` with `front={"kind": "speak_to", "person_id": <npc>, "asks": "rumour", "about_person_id": "none"}`):
  - `test_say_line_is_read_once`: say mode to a chosen NPC, plain line → `client` front schema called exactly 1 time, speech called 1 time, total model calls == 2, route != `"skipped:typed"`.
  - `test_failed_reading_skips_old_classifier`: `client.fails = RuntimeError()` → total calls ≤ 2, response 200, narration non-empty.
  - `test_flag_off_keeps_old_chain`: `AI_DND_FRONT_PROPOSAL` unset → route `owner_first`/skipped and behaviour equal to today (same narration as before for the same scripted reply).
  - `test_coin_line_still_goes_to_money_owner`: "Al şu 5 altını, Çarnuva nerede?" to a vendor with reading `speak_to` + `coin_cp: 500` → money owner path runs (same action as current D1 test expects).
  - `test_bad_about_person_is_none`: reading `about_person_id` = addressee id, then = "npc_missing" → stored reading has `about_person_id == "none"`.
  - `test_schema_has_asks_and_about_early`: `front_proposal.schema(listed)["required"]` contains both within its first 10 entries; `model_chain._haiku_schema(schema)` does not raise.
- [ ] **Step 1.2: Run, expect FAIL** (`reads_say_line` missing; say line routed `skipped:typed`):
  `bash C:/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh 1 AI-DND-k2-bm test t1-red 1500 api.tests.test_talk_front api.tests.test_front_proposal api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys`
- [ ] **Step 1.3: Implement.** `front_proposal`: add `ASKS`, the two schema fields early in `properties`/`required`, two guidance lines (describe fields; no word lists), repair invalid values to `"none"`. `talk_front.reads_say_line`: True for say/ask_dm with or without a chosen person unless fight words, slash, journey not arrived, hideout, "konuşmayı bitir" (existing `front_read_ahead` exclusion). `game._front_step`: replace the `interaction_mode in {"say","ask_dm"} and not (said_coin or served)` and `target_id is not None and not typed_economic and not fought` skip clauses with `not talk_front.reads_say_line(...)`; keep `addressed` = chosen person in say mode. After a failed/absent reading in say mode set the old chain's `classifier_unusable` so it makes no classifier call.
- [ ] **Step 1.4: Check `dialogue_runtime`:** does a new local campaign set `dialogue_runtime.is_enabled(world)`? Write the answer and a ledger Ruling; if enabled, add `talk_front.old_owner_allowed` gate before `dialogue_runtime.resolve_turn` in `_dispatch_player_turn` and a test `test_dialogue_runtime_respects_reading`.
- [ ] **Step 1.5: Run, expect PASS** (same command, label `t1-green`); also `api.tests.test_addressed_lines api.tests.test_experimental_npc_dialogue api.tests.test_front_carries_more`. Rewrite any test pinning `skipped:typed` at equal strictness → approval list.
- [ ] **Step 1.6: Commit** `BM T1: conversation lines get the front reading; old classifier skipped after a failed reading`.

### Task 2: Say owners become fallback (shop presence, unknown name, place name, name disclosure)

**Files:**
- Modify: `ai-dnd/talk_front.py` (add `shop_presence_reply`), `ai-dnd/game.py` (`_run_player_turn_internal`: shop presence branch, unresolved named address branch, place-name branch, name disclosure branch)
- Test: `ai-dnd/api/tests/test_talk_front.py`

**Interfaces:**
- Consumes: T1 `old_owner_allowed`, reading on `session._front_read`.
- Produces: `talk_front.shop_presence_reply(world_state: dict, npc_target: dict | None) -> str` (moved body, same sentences).

- [ ] **Step 2.1: Failing tests:**
  - `test_shop_word_question_to_vendor_is_spoken`: Nivrek-like vendor chosen, "Satıcılar arasında ne dönüyor?", reading `speak_to/asks=rumour` → narration is the scripted speech, not `"… burada; tezgâhı açık."`; action != `shop_inquiry`.
  - `test_shop_list_when_reading_asks_shop`: reading `asks=shop` → shop line still printed.
  - `test_unknown_name_uses_reading`: "Zoltan, merhaba" with reading `person_word="Zoltan"` not listed → "Burada Zoltan adıyla tanıdığın biri görünmüyor."; with reading `person_id` = chosen NPC and line "Çavuş, merhaba" → speech.
  - `test_name_disclosure_is_spoken_and_stored`: "Adım Dorin." → NPC memory stores the name (as today), narration is the scripted speech, not any `local_dialogue` INTRODUCTION pool line; total calls == 2.
  - `test_place_name_question_is_spoken`: "Peki oranın adı ne?" with reading `speak_to/asks=place` → speech.
  - Each of the five also with `client.fails` set → today's line (fallback kept).
- [ ] **Step 2.2: Run, expect FAIL** (label `t2-red`, modules `api.tests.test_talk_front api.tests.test_addressed_lines api.tests.test_experimental_npc_dialogue` + neighbour set).
- [ ] **Step 2.3: Implement:** move the shop presence message builder into `talk_front.shop_presence_reply`; guard each of the four branches with `talk_front.old_owner_allowed(front, "<owner>")`; for name disclosure keep the memory write before the gate, skip only the pool reply.
- [ ] **Step 2.4: Run, expect PASS** (label `t2-green`). Old-line tests rewritten → approval list.
- [ ] **Step 2.5: Commit** `BM T2: shop presence, unknown name, place name and name disclosure answer by speech when the reading is plain talk`.

### Task 3: Say owners become fallback (personal, small talk, quest/work, lore gate, role + person), D-325, dead `_with_job_news`

**Files:**
- Modify: `ai-dnd/game.py` (personal answer branch, smalltalk function call site, quest availability and unaddressed work branches, lore gate branch, role+person scene-list branch, `historical_claim_denial` order vs `_town_fallback`; delete `_with_job_news`)
- Test: `ai-dnd/api/tests/test_talk_front.py`

- [ ] **Step 3.1: Failing tests** (reading `speak_to`, scripted speech; each also with `client.fails` → old line):
  - `test_personal_question_is_spoken` ("Nerelisin?"), `test_small_talk_is_spoken` ("Günün nasıl geçiyor?"), `test_quest_question_is_spoken` ("Burada iş var mı?", reading `asks=work`, NPC with no job), `test_lore_question_is_spoken` ("Kralın adı ne?"), `test_role_who_is_here_is_spoken` ("Çavuş, bu gece nöbette kim var?" — D-326).
  - `test_told_before_line_gets_own_rumour` (D-325): NPC with a `heard_rumours` entry she spoke ("Kespur Tapınağı: kilitte taze çizikler"), line "Bana Kespur Tapınağı'ndan bahsetmiştin" with reading failed → reply contains "kilitte taze çizikler", not the historical-claim denial.
  - `test_with_job_news_is_gone`: `hasattr(game, "_with_job_news") is False`.
- [ ] **Step 3.2: Run, expect FAIL** (label `t3-red`, + `api.tests.test_npc_never_bare_unknown api.tests.test_addressed_lines` + neighbour set).
- [ ] **Step 3.3: Implement:** same gate pattern as T2 with owners `personal`, `small_talk`, `quest_availability`, `unaddressed_work`, `lore_gate`, `role_person_list`; move `heard_rumours.own_line` check before `historical_claim_denial`; delete `_with_job_news` (verify no caller with `git grep -n _with_job_news`).
- [ ] **Step 3.4: Run, expect PASS** (label `t3-green`); close D-325 and the dead-code half of D-326 in the debt register.
- [ ] **Step 3.5: Commit** `BM T3: remaining say owners fall back behind the reading; own rumour before the denial (D-325); drop unused _with_job_news (D-326)`.

### Task 4: Thread gate decided by the reading (B1) — money, Opus review

**Files:**
- Modify: `ai-dnd/talk_front.py` (add `work_reading`), `ai-dnd/game.py` (`_thread_gate`)
- Test: `ai-dnd/api/tests/test_bm_thread_reading.py`

**Interfaces:**
- Produces: `talk_front.work_reading(front: dict | None, npc: dict, world: dict) -> dict | None` → `{"thread_id": str, "decision": str | None}` when the reading's `kind in {"work","offer_answer","hand_over"}`, or `job_id` is this NPC's job (`world_threads.jobs_of`), or `asks == "work"` to the job owner; else None. Python then calls the existing `world_threads` writers for that decision only.

- [ ] **Step 4.1: Failing tests** (`fixed_town(self, 4181)`, a delivery job owned by NPC A with recipient B, as the play's Nivrek/Çarnuva):
  - `test_question_naming_recipient_is_not_job_talk`: to A, "Çarnuva'nın söylediği gerginlik ne?" with reading `speak_to/asks=rumour/about_person_id=B` → narration has no "Teslim edene", no `thread_catalog` owner-terms text; thread status unchanged; purse unchanged.
  - `test_reading_job_id_still_opens_terms`: reading `job_id`=A's job, `asks=work` → owner terms voiced, thread `offered` as today.
  - `test_accept_and_question_once`: "Tamam yaparım, Çarnuva nerede?" with reading `offer_answer/answer=accept/job_id` → accepted once, quest count +1 exactly, no second terms line.
  - `test_pay_still_python`: done job, reading `kind=speak_to, asks=work` + line asking pay → pay decision written by Python with the stored amount (same assert as existing pay test).
  - `test_no_reading_old_words`: `client.fails` → `world_threads.turn_gate` result as today (B1 behaviour reproduced, documents which word fired; write it in the ledger).
  - Undo after accept → thread back to `offered`, quest removed.
- [ ] **Step 4.2: Run, expect FAIL** (label `t4-red`, + `api.tests.test_world_threads api.tests.test_thread_offer api.tests.test_town_knowledge` + neighbour set).
- [ ] **Step 4.3: Implement** `work_reading`; in `_thread_gate` with a reading present use it instead of `world_threads.turn_gate`; without a reading keep `turn_gate`. Money writers untouched.
- [ ] **Step 4.4: Run, expect PASS** (label `t4-green`). Opus independent review on a `git archive` copy.
- [ ] **Step 4.5: Commit** `BM T4: a job decision needs the reading; a question naming another person is not job talk (B1)`.

### Task 5: Own words first in what an NPC knows (B2) — wave 1, parallel

**Files:**
- Modify: `ai-dnd/town_knowledge.py` (`public_knowledge` order), `ai-dnd/town_rumours.py` (`rumour_for` order)
- Test: `ai-dnd/api/tests/test_own_words_first.py`

- [ ] **Step 5.1: Failing tests** (unit, world built with `fixed_town` campaign or the fixture style of `test_town_knowledge.py`):
  - `test_own_spoken_rumour_is_first`: NPC spoke rumour R; town has 3 threads → `public_knowledge(world, npc)[0..1]` contains R's text before any thread item.
  - `test_own_rumour_survives_the_cap`: 10 threads + R → R in result.
  - `test_rumour_for_own_before_trouble`: `rumour_for` returns own heard rumour before a foreign trouble.
- [ ] **Step 5.2: Run, expect FAIL** (slot 2, label `t5-red`, `api.tests.test_own_words_first api.tests.test_town_knowledge api.tests.test_heard_rumours` + neighbour set).
- [ ] **Step 5.3: Implement:** in `public_knowledge` put the NPC's own spoken heard rumours (`town_rumours._spoke`) right after the town item; in `rumour_for` sort own heard before the trouble item.
- [ ] **Step 5.4: Run, expect PASS** (label `t5-green`).
- [ ] **Step 5.5: Commit** `BM T5: what a person said themselves comes first in what they know (B2)`.

### Task 6: NPC speech context: time, arrival scene, own words, own work, last lines (B4, B5, B6, repeats) — Opus review

**Files:**
- Modify: `ai-dnd/talk_front.py` (add `speech_extras`), `ai-dnd/game.py` (`_experimental_npc_dialogue_context` merges it; `INITIAL_WORLD_STATE` default), `ai-dnd/arrival_narration.py` (`narrate` stores the shown text), `ai-dnd/town_knowledge.py` (closed-mouthed line: say the excuse once)
- Test: `ai-dnd/api/tests/test_npc_scene_time.py`

**Interfaces:**
- Consumes: T10 (`arrival_narration.narrate` final text and source), T5 order.
- Produces: `talk_front.speech_extras(world: dict, npc: dict) -> dict` with keys `zaman` (`{"gun": int, "vakit": "şafak|gündüz|akşam|gece", "saat": "HH:MM"}` or absent), `sahne_anlatimi` (str ≤ 600, only when `world["scene_state"]["arrival_text"]["place_id"] == world["location"]`), `kendi_sozlerin` (list[str] ≤ 3), `kendi_isin` (str | None), `son_sozlerin` (list[str] ≤ 3). Stored key: `world["scene_state"]["arrival_text"] = {"place_id": str, "text": str, "turn": int}`.

- [ ] **Step 6.1: Failing tests:**
  - `test_speech_prompt_has_evening_time`: clock at 17:10 → speech prompt (captured `message_batches`) contains `"vakit": "akşam"` and `"17:10"`.
  - `test_speech_prompt_has_arrival_scene`: arrival narration scripted with "çizelgede bir isim karalanmış" → next speech prompt at that place contains that phrase; after moving elsewhere it does not.
  - `test_speech_prompt_has_own_work`: NPC owns an offered job → `kendi_isin` equals its public line (B5).
  - `test_speech_prompt_has_last_lines`: after two replies, `son_sozlerin` holds both, newest last.
  - `test_undo_drops_arrival_text`: arrive, Undo → `scene_state.arrival_text` equals the earlier value.
  - `test_save_load_keeps_arrival_text`: save/load → same value.
- [ ] **Step 6.2: Run, expect FAIL** (label `t6-red`, + `api.tests.test_experimental_npc_dialogue api.tests.test_arrival_wiring api.tests.test_campaign_api` + neighbour set).
- [ ] **Step 6.3: Implement** `speech_extras` (time from `campaign_time.public_time`, period words as `arrival_narration._PERIODS`); store arrival text in `arrival_narration.narrate` after the final text is set; one prompt line each: speak consistent with the time; do not deny what the scene text shows; do not repeat the same refusal/excuse as in `son_sozlerin`; closed-mouthed line says the excuse may be said once.
- [ ] **Step 6.4: Run, expect PASS** (label `t6-green`). Opus independent review.
- [ ] **Step 6.5: Commit** `BM T6: NPC speech knows the hour, the scene the player saw, its own work and its last lines (B4, B5, B6)`.

### Task 7: Journal shows what was heard (B3) — Opus review

**Files:**
- Modify: `ai-dnd/game.py` (`_EXPERIMENTAL_NPC_SPEECH_SCHEMA` + per-turn enum fill: `voiced`), `ai-dnd/town_knowledge.py` (`speech_note` keys `k1..k10`; `note_mention`), `ai-dnd/quest_log.py` (`_trail_rows` heard-rumour trail text and speaker), `ai-dnd/interaction_adventure.py` or `ai-dnd/api/campaign_journal.py` (stop copying the generic `statement_heard` summary; K-BM-4)
- Test: `ai-dnd/api/tests/test_journal_heard.py`

**Interfaces:**
- Produces: speech packet field `voiced: list[str]` (enum `k1..k10` of the listed items + `"none"`, max 3, required); `town_knowledge.note_mention(world, npc, shown_text, *, voiced: list[str] | None = None, job_talk=False, offer_talk=False)`.

- [ ] **Step 7.1: Failing tests:**
  - `test_place_name_alone_marks_nothing`: reply names the place of thread T but says "gerginlik var" → T not `heard`; no `duyulan` trail with T's `public_line`.
  - `test_voiced_and_words_mark_heard`: reply carries T's words and `voiced=["k2"]` (T is k2) → T heard, trail text = T's public line.
  - `test_voiced_id_without_words_marks_nothing`: `voiced=["k2"]`, reply lacks T's words → not heard.
  - `test_heard_rumour_trail_shows_claim_and_speaker`: rumour "Kespur Tapınağı: kilitte taze çizikler" spoken by NPC X → trail text contains "kilitte taze çizikler" and X's public name.
  - `test_no_generic_heard_line_in_journal`: after a `statement_heard` event → no journal entry with "Söylediklerin konuşmada duyuldu."
  - `test_undo_drops_heard_trail`.
- [ ] **Step 7.2: Run, expect FAIL** (label `t7-red`, + `api.tests.test_campaign_journal api.tests.test_town_knowledge api.tests.test_interaction_adventure api.tests.test_heard_rumours_turn` + neighbour set).
- [ ] **Step 7.3: Implement:** schema field + enum fill per turn from the listed keys; `note_mention` marks only items that pass the word-overlap rule (generalize `town_rumours.was_voiced` to threads) and, when `voiced` is given, are also in it; remove the place/owner-name-only marking.
- [ ] **Step 7.4: Implement (K-BM-4):** the `statement_heard` summary is not written to the journal.
- [ ] **Step 7.5: Run, expect PASS** (label `t7-green`). Opus independent review.
- [ ] **Step 7.6: Commit** `BM T7: the journal keeps what was really said, by whom (B3)`.

### Task 8: Everyday actions wait for the reading; dead perform branch

**Files:**
- Modify: `ai-dnd/game.py` (`_dispatch_player_turn` everyday call site), `ai-dnd/everyday_actions.py` (remove `_PERFORM` and the `perform` branch in `resolve`)
- Test: `ai-dnd/api/tests/test_everyday_gate.py`

- [ ] **Step 8.1: Failing tests:** `test_everyday_waits_for_reading` ("Adamın peşinden gidiyorum" with reading `go_to` a listed place → go-to owner answers, not everyday follow); `test_everyday_without_reading` (reading fails → follow lines as today); `test_no_perform_branch` (`hasattr(everyday_actions, "_PERFORM") is False`).
- [ ] **Step 8.2: Run, expect FAIL** (label `t8-red`, + `api.tests.test_lr00_everyday_actions` + neighbour set).
- [ ] **Step 8.3: Implement:** everyday classify runs only when the reading is None or `kind in {"unclear", "attempt"}`; delete the dead branch.
- [ ] **Step 8.4: Run, expect PASS** (label `t8-green`). **Step 8.5: Commit** `BM T8: everyday words wait for the reading; drop unreachable perform branch`.

### Task 9: Road warning does not stop the walk (B7, K-BM-2) — wave 1, parallel

**Files:** Modify `ai-dnd/grounded_action.py` (`road_goes_on`); Test `ai-dnd/api/tests/test_road_on.py`

- [ ] **Step 9.1: Failing tests:** at an outdoor road place with a resident: `test_first_go_on_walks_and_warns` → narration starts with one `_ROAD_ON` sentence, then the walk result; location/time changed; `record["road_warned"] is True`. `test_second_go_on_no_warning`. Undo → location, time and `road_warned` back.
- [ ] **Step 9.2: Run, expect FAIL** (slot 3, label `t9-red`, + `api.tests.test_road_lines api.tests.test_lr00_grounded_human` + neighbour set).
- [ ] **Step 9.3: Implement:** on first warning, return None-equivalent walk with the warning prefixed (same `_Run` spend / next road place as the warned-already branch). **Step 9.4: PASS** (label `t9-green`). **Step 9.5: Commit** `BM T9: the road warning is said while the player walks on (B7)`.

### Task 10: No model call when the arrival budget is 0 (D-324) — wave 1, parallel

**Files:** Modify `ai-dnd/arrival_narration.py` (`narrate`); Test `ai-dnd/api/tests/test_arrival_budget_zero.py`

- [ ] **Step 10.1: Failing test:** `test_full_python_return_makes_no_call`: gated return where the Python entry already has 4 sentences → model client not called, result source `"python"`, text ≤ 4 sentences.
- [ ] **Step 10.2: FAIL** (slot 4, label `t10-red`, + `api.tests.test_arrival_wiring` + neighbour set). **Step 10.3: Implement** budget check before the call. **Step 10.4: PASS**. **Step 10.5: Commit** `BM T10: a full Python return spends no model call and says so (D-324)`.

### Task 11: Measure the ready-line share

**Files:** Modify `ai-dnd/front_proposal.py` (`log_turn`, new `ENGINE_OWNERS`, `ready_line_share`), possibly `ai-dnd/game.py` call site of `log_turn`; Test `ai-dnd/api/tests/test_ready_line_share.py`

**Interfaces:**
- Produces: route-log row keys `narration_source: str | None`, `model_calls: int`; `front_proposal.ready_line_share(rows: list[Mapping]) -> {"moves": int, "ready": int, "share": float}`; `ENGINE_OWNERS` frozenset, filled from the owners seen in the 2026-11-16 and 2026-11-17 route logs that are money/dice/XP/purchase/rule (list them in the ledger).

- [ ] **Step 11.1: Failing tests:** `test_share_counts_python_sources` (rows: 2 `qwen`, 1 `deterministic_fallback`, 1 `python_memory_response`, 1 `deterministic_system` with owner `shop_economy` → moves 4, ready 2, share 0.5); `test_log_turn_writes_source` (temp `AI_DND_ROUTE_LOG`, one HTTP say turn → row has `narration_source` and `model_calls`).
- [ ] **Step 11.2: FAIL** (label `t11-red`, + `api.tests.test_front_proposal` + neighbour set).
- [ ] **Step 11.3: Implement:** read the source from the turn result's engine telemetry; if it is not on the result at `log_turn` time, pass it from the `game` call site (then this task runs serial after T8).
- [ ] **Step 11.4: PASS**. **Step 11.5: Commit** `BM T11: route log records the narration source; ready-line share`.

### Task 12: Slice end

- [ ] **Step 12.1:** Full suite once through the slot runner; record time and result in the ledger. Any red: trace to the commit (CLAUDE.md "Bilinen kırıklar").
- [ ] **Step 12.2:** Opus whole-branch review (`git archive` copy); fix findings with red-green.
- [ ] **Step 12.3:** Debt register: park rows for do-mode owners left (bold_acts, pocket, grounded_action words, `interaction_adventure.hint` 115–120), arrival prefix repeats, anything parked in the ledger; close D-324, D-325, D-326.
- [ ] **Step 12.4:** Play script for Kadir (≥ 10 min, cloud chain): replay B1–B7 lines and the repeat table lines; after play, run `ready_line_share` on the route log and write the number next to the 11/28 baseline. Ledger: "oynayış bekliyor" until done.
- [ ] **Step 12.5:** `graphify update .`; morning summary (≤ 5 lines). No push/PR/merge without Kadir.
