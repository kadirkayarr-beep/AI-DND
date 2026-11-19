# Flag-on fixes (D-369, D-370, D-371) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** With `AI_DND_FRONT_PROPOSAL=1` (the local-play default since dc79b90b), the 304 F_fon tests pass and still check what they checked: money, save, rollback, receipt replay and Undo on the path local play really uses. Five real engine gaps are fixed red-first, and the owner's three decisions are built.

**Architecture:** Two lanes run in parallel, each in its own worktree with one writer:
- Lane A is money and save: the outage rule, the coin rule and the money and save test files.
- Lane B is the other engine gaps and the remaining test files.

Lane B is merged into lane A locally. Then both full suites run and the whole branch is reviewed. The result is one PR. Files the running fixed-town job also edits wait for its merge (Task Z).

**Spec:**
- The triage `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p2/F_fon-triage.md`: groups G1-G11, evidence per id, and the section "Owner decisions (Kadir, 2026-11-19, in chat)".
- Debt rows D-369, D-370 and D-371.
- The F_fon id list `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p2/F_fon.txt`. `#` lines are comments, and the id is the first tab field.

## Global Constraints

- **Base:** main `b1150df8`.
  - Lane A: `C:\Users\Kadir\Desktop\AI-DND-k2-fon-a`, branch `task/fon-a`, slot 3.
  - Lane B: `C:\Users\Kadir\Desktop\AI-DND-k2-fon-b`, branch `task/fon-b`, slot 5.
- **Owner decisions (verbatim intent):**
  - **G6, "Tekrar dene":** a provider outage during the front reading answers 503, rolls back and spends no line. A reading that comes back but is unusable still goes on through the old chain.
  - **G11, "Eski kural karar versin":** when the reading fails, the old structural coin rule still makes the coin decision and writes its note. Coin never vanishes silently.
  - **G1, "Testleri 1'e güncelle":** the 55 zero-call tests expect exactly one call (the reading). Each rewrite is equally strict and goes on the approval list marked "gevşetme olabilir".
- **Keep the flag on.** Money and save tests are fixed by updating their expectations, never by pinning the flag off. Pin the flag off only where a test's own subject is the flag-off path (old classifier prompt, legacy scripts), and give that pin a `Ruling` line.
- **Exact counts:** a count is updated to the exact new value (`assertEqual`), never to `>=`/`<=`. An update to a count or index needs evidence from the run (which calls happened, by kind).
- **The first failure is not the last.** After a test's first stale check is fixed, every later check (rollback, receipt replay, Undo, purse totals) must pass with the flag on. A later failure is either:
  - (a) a real gap: fix it red-first, money and save on Opus; or
  - (b) a stale expectation: show the evidence.

  The test must never be weakened to get past it.
- **Every targeted run is twice, on the lane's slot:**
  - Flag on: label `<task>-fon`, module list starting with `api.tests.gate_boot`.
  - Flag off: label `<task>-off`, without gate_boot.

  Both runs include NEIGHBOURS = `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys`. Pass is `RESULT exit=0`, except for the Task Z ids that are still deferred, which are named in the report.
- **Lanes never edit** `docs/agents/debt-register.md` or `docs/agents/onay-listesi-20261115.md`. They write the proposed rows into their report.
- **Debt ids:** this job uses D-400 and up. D-381..D-399 are left to the fixed-town job, which is running at the same time. The approval list section is 20; the fixed-town job uses 19.
- **Full suites:** only in Task G, one at a time, after the strict pgrep wait. No browser tests. Never read key files. Never push, merge to main/dev, or delete branches.

## Review Focus

1. **A timeout or a dropped connection in the middle of the reading counts as an outage:** 503, nothing saved, no coin moved. Partial or bad JSON counts as an unusable reply and goes to the old chain. FA1 tests both sides.
2. **Retrying the same line after a 503** spends one reading and moves coin once. Replaying the same action id spends no reading and moves no coin. FA1 adds this test.
3. **The G11 old coin rule runs only when the reading failed.** A successful reading never gets a second coin decision. FA2 tests both cases.
4. **Count updates must not hide a real extra call.** Each updated count names the call kinds it saw (for example `['front', 'speech']`).
5. **The first-assertion caveat:** the review checks that the later rollback, Undo and replay checks really ran with the flag on. The flag-on run log is the evidence.

## Lane A (fon-a, slot 3): money and save. Opus review.

### Task FA1: G6 outage rule (save)

**Files:**
- `api/ollama_adapter.py`: the swallowed front failure, near "the chain never fails a turn".
- All F_fon rows of `test_f04_frozen_faults`, `test_api`, `test_stage10b_model_boundary` and `test_model_failure_never_locks`. That includes their G1 and G2 rows.

- [ ] Red tests:
  - an outage during the reading gives 503 and rollback, and the saved state is unchanged;
  - an unusable reading goes on through the old chain;
  - Review Focus 1 and 2.
- [ ] Build the owner's rule. Fix every F_fon row in the four files.
- [ ] Run flag on and flag off. Commit.

### Task FA2: G11 plus G3 (money)

**Files:** the failed-reading coin path (find it with graphify: `front_proposal`, `money_owner`), plus `test_economic_bribe`, `test_coin_writers`, `test_economic_dialogue`, `test_economic_room` and `test_step0_ledger_play`.

- [ ] G11: a red test for a failed reading under arrest. Coin handed over must get the old structural decision and its note. Review Focus 3. Build it.
- [ ] G3: plant the test coin state after `front_proposal.begin()`, not before it, keeping the flag on. Every later purse and receipt check must run.
- [ ] Run flag on and flag off. Commit.

### Task FA3: G1/G2/G5 money files

**Files:** `test_haggle_speech`, `test_explicit_shop_creation`, `test_d231_person_gear`, `test_live_neverwinter_smoke_diagnostics`, `test_real_lead_fallback`, `test_f04_frozen_narrator_faults`, `test_witness_question_source`, `test_witness_review`, `test_intent_response_consistency`.

- [ ] Fix the F_fon rows: counts, picking calls by kind, scripted front replies. Commit.

### Task FA4: G1/G2/G5/G7 save files

**Files:** `test_real_death`, `test_narration_receipt_contract`, `test_dialogue_place_commit`, `test_repair_repetition_acceptance`, `test_meaning_boundary_acceptance`, `test_identity_entity_acceptance`, `test_public_door_focus`, `test_door_tool_acceptance`, `test_f04_creation_authority`, `test_bound_speech_label`, `test_stage_profile_contract`, `test_campaign_api`.

- [ ] Same as FA3. G7: check the refusal, not which function raised it. Commit.

## Lane B (fon-b, slot 5)

### Task FB1: G8 NPC initiative starved by the 2-call cap

**Files:** `dialogue_runtime.py` (`_append_initiative` and the cap check), `test_npc_initiative`.

- [ ] Write a red test: an NPC who saw the wound speaks up while the flag is on. The reading must not use up the initiative's room. Never raise `MAX_MODEL_CALLS_PER_TURN`, because it is the turn budget. Decide whether the reading or the initiative gets a cap exception, and write it as a Ruling.
- [ ] Build it. Run flag on and flag off. Commit.

### Task FB2: G9 plus G10 (`game.py`)

**Files:** `game.py` (the front read-ahead skip list and the intent-call counting), `test_dilim4c_4b_review_fixes`, `test_dilim4c_surrender_spells_http`, `test_ai_freedom_resolution_boundary`.

- [ ] G9 red test: "evet" to the surrender question spends no reading and the strike lands. Check whether `_blow_asked` needs the same exemption.
- [ ] G10 red test: a held reading is not counted as a second intent call.
- [ ] Build both. Commit.

### Task FB3: G1/G2 files with save rows

**Files:** `test_dialogue_runtime`, `test_npc_player_address`, `test_experimental_npc_dialogue`.

- [ ] Same rules as FA3. Opus review. Commit.

### Task FB4: G1/G5 other files, batch 1

**Files:** `test_compound_smalltalk_acceptance`, `test_default_focus_acceptance`, `test_default_npc_targeting`, `test_dialogue_live_context`, `test_equipment_native`, `test_f04_greeting_agency_quality`, `test_f04_n08_empty_narration_source`, `test_f04_n08_live_prose_guard`, `test_f04_n08_npc_memory`, `test_f04_transient_narration_memory`, `test_free_attempts`, `test_grounded_instrument_target`, `test_job6_compound_trace`, `test_lasting_consequences`, `test_legacy_script_isolation`, `test_lore_engine_integration`, `test_lr00_p1_intent`.

- [ ] Same rules. Commit.

### Task FB5: G1/G2 other files, batch 2

**Files:** `test_model_chain`, `test_npc_p2_continuity`, `test_npc_paired_history`, `test_npc_scene_places`, `test_query_request_acceptance`, `test_smoke_turn_diagnostics`, `test_spoken_plan`, `test_stage10a_narration_intent`, `test_untrusted_player_input`.

- [ ] Same rules. Commit.

## Task M: merge and rows

- [ ] In lane A: `git merge --no-ff task/fon-b`. Rerun every module of all tasks, flag on and flag off.
- [ ] Debt register:
  - update D-369, D-370 and D-371 with their state (all closed except the Task Z ids);
  - add new rows from D-400 on, for the parks.
- [ ] Approval list section 20 with every changed test. The G1 zero-call rewrites are marked "gevşetme olabilir". Commit.

## Task G: gate

- [ ] Two full suites on slot 3, one at a time:
  - `slot_gate.sh 3 AI-DND-k2-fon-a fon-off 3 3600 '.'`: pass is `failing_ids 0` and `PAR_EXIT=0`.
  - Then `fon-on-fon`: pass is failing ids ⊆ the Task Z set below.
- [ ] `python test_regression.py` as a script: 30/30.

## Task R: whole-branch review

- [ ] One Opus review of `b1150df8..HEAD`, focused on money and save and the Review Focus. Then one fix wave (red-first) and one scoped re-review.

## Task Z (after the fixed-town PR is merged to main): the deferred ids

- [ ] Merge main into `task/fon-a`. Fix the F_fon rows of the deferred files:
  - `test_step4_branches` (5 G1 rows);
  - `test_journey_runner` (1 G2 row);
  - the G4 group (14 ids): script the front reply in scenarios `03_room_sleep` and `08_talk_mode`, so they run the real flag-on path. Pin `front_proposal: false` only if the runner cannot script a front, with a Ruling.
- [ ] The flag-on full suite gives `failing_ids 0`.
