# Turn Split (tur bölme) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Kadir için kısa özet (sade Türkçe)

- **Ne:** Oyunun tur kodundaki dev işlevleri (en büyüğü 2 741 satır) küçük parçalara bölüyoruz. Oyunda görünür bir şey değişmez. Amaç, sonraki anlatıcı işinin (B2) dondurulmuş dev işlevlere dokunmak zorunda kalmaması.
- **Ölçtüm:** Bir betik her bloğun neyi okuyup neyi yazdığını saydı. Ana işlevde 165 blok var. Bunlardan 47'si (1 153 satır) kurala uyuyor ve güvenle kesilebilir. Kalan büyük bloklar fazla değişkene bağlı. Onlar bu dilimde kesilmez.
- **İki seçenek:**
  - **Küçük yol (yol 2):** yalnız B2'nin gerektirdiği iki parça bölünür: turun bittiği yer (`finish_turn`) ve anlatım işlevi (`_narrate_resolved_turn`). Tahmin: yaklaşık 1,5 gün ve 3,8 milyon token.
  - **Tam yol:** buna ek olarak ana tur işlevindeki bütün uygun bloklar kesilir. Tahmin: yaklaşık 3,5 gün ve 7,5 milyon token.
  - Plan iki aşamalı yazıldı. Küçük yol, tam yolun ilk aşamasıdır. Ortadaki oynayıştan sonra durmak mümkün.
- **Bu sayılar tahmin, ölçüm değil [T].** Gün ve token sayıları önceki bölme planlarına bakılarak verildi. Önceki planların toplam token kaydı yok; yalnız Plan 6'nın devam koşusu ölçüldü (1,87 milyon).
- **Senden beklenen:** küçük ya da tam yolu seçmen. Ortada ve sonda 10'ar dakika oynaman (kontrol listeleri Görev 7 ve Görev 14'te).

**Goal:** Cut the frozen turn core into helpers in new parts so that B2 (and later work) edits functions under the 151-line freeze threshold instead of frozen giant functions, with zero behaviour change.

**Architecture:** A new mechanical tool (`cut_block.py`) cuts one top-level statement block out of a function into a helper in a new `game_parts/` module. The block text is moved byte for byte. The only change is a `game.` prefix on names the receiving part does not bind, the same N3 rule `move_block.py` already applies. The call site follows one of two fixed shapes (class A: outputs returned; class B: exit sentinel). Nested closures (`finish_turn`) are lifted with a thin shim that keeps late binding. Order is "önce taşı, sonra düzelt": every cut is identity-only; no fix rides along.

**Tech Stack:** Python stdlib (`ast`, `tokenize`, `unittest`). `scripts/engine_split/` tools (`move_block.py`, `move_check.py`, `routing_audit.py`, `sensitivity.py`). Guarded WSL runners `AI-DND-TOOLS/slot.sh` and `ai-dnd/scripts/engine_split/slot_gate.sh`.

**Spec:** `docs/superpowers/specs/2026-11-17-game-py-bolme-design.md` §12 "Sonraki dilim". Also: `docs/adr/0001-game-parts-merkez-kurali.md` (size budget, Q1, Q3, Q4), `docs/superpowers/specs/2026-11-22-yol-haritasi-design.md` (§4 yol 1/2, §5 row 4, S1-S9), `docs/design/YENIDEN_TASARIM_PLANI_20261113.md` §B2 (what B2 edits), `ai-dnd/api/tests/engine_split_locks/size_budget.json`, debt rows D-474 and D-478 (`docs/agents/debt-register.md`).

**Measure folder:** `docs/superpowers/plans/2026-11-23-tur-bolme-measure/`.
- `block_io.py <source.py> <function> [<nested>] [--sub LINE] [--label T]` is the AST inventory. It never imports the measured module.
- `run_all.sh <ref> <tag> [sub lines...]` re-runs it on a git ref.
- `view_big.py <out.txt> <min lines>` is a reader.
- Raw outputs: `*_main.txt` and `*_149.txt`.

## Measured inventory

**What was measured.**
- `origin/main` `c9c4aac6` (tag `main`).
- `origin/task/d331-d332-20261123` `54835935` (tag `149`): PR #149, unmerged, the closest picture of the future `turn.py`.
- The cut list below uses the **`149` numbers**.
- Both were run with Python 3.14, `python -I`, rc 0.

`[D]` = measured by `block_io.py`. `[T]` = estimate.

| Target | main | #149 | Top-level blocks | Returns / raises | Nested defs |
|---|---|---|---|---|---|
| `turn.py::_run_player_turn_internal` | 2 756 lines [D] | 2 741 [D] | 165 / 165 [D] | 75 / 4 [D] | 7 [D] |
| ↳ nested `finish_turn` | 231 [D] | 231 [D] | 24 / 24 [D] | 3 / 1 [D] | 1 [D] |
| `turn.py::_dispatch_player_turn` | 493 [D] | 458 [D] | 77 / 74 [D] | 54 / 6 → 50 / 6 [D] | 0 |
| `game.py::_narrate_resolved_turn` | 351 [D] | (same file) | 52 [D] | 1 / 0 [D] | 0 |
| `narration_safety.py::_narration_safety_decision` | 1 054 [D] | — | 131 [D] | 72 / 0 [D] | 4 [D] |

**Facts that shape the plan [D]:**
- **`finish_turn` callers.** `finish_turn` is called 55 times, every time as `return finish_turn(...)`.
- **`finish_turn` captured names.** It reads 25 names of the enclosing function directly, 29 with its own nested helper.
- **Late binding.** Some of those names (`allow_new_npcs`, `allow_new_features`, `allow_new_locations`, `allow_new_shops`, `expected_location_change`) are rebound near the end of the function. `finish_turn` must see the value at call time.
- **The one `nonlocal`.** `nonlocal narration_model_calls` is in `finish_turn._incident_before_skipped_narration`. Its value is used only inside `finish_turn`, because every call is `return finish_turn(...)`.
- **The one `locals()`.** `locals().get("preparsed_scene_intent")` is in block `1948-2010` (#149 lines). `preparsed_scene_intent = None` runs unconditionally at function entry (main line 931, #149 line 896), so `locals().get(...)` always equals the plain name. `move_block.py` refuses `locals` (its `DYNAMIC_CALLS`), so any later move of that block is blocked until it is replaced.
- **Routing rules.** `routing_audit.py` R2: a part never imports another part. R8: every top-level name of a part is re-exported by `game.py`. R9: a part reaches its own functions through `game.`. So every helper is called as `game._name(...)`, and every new part adds one re-export line and one `_PART_MODULES` entry to `game.py`.
- **Size budgets.** `size_budget.json`: `turn.py` 3 667, `game.py` 1 447, `long_function_min` 151, `slack` 50. `_run_player_turn_internal` is 2 756, `_dispatch_player_turn` 493, `_narrate_resolved_turn` 351. A function of 151 lines or more is frozen and no new key may enter. **So every helper must be under 151 lines.** A budget more than 50 above the real size is red, so every cut task lowers the budgets in the same commit.
- **Patches.** Tests patch `game_parts.turn.<name>` once (`ResolvedTurn`); everything else goes through `game.` (patch census N2).
- **Marker false positives.** The `save` and `undo` markers inside the targets are death saves (`save_result`, `death_save`) and `talk_mode.snapshot` / procedural-id snapshots, not file saves or Undo. The real Undo snapshot is `_run_player_turn_owned` (`_capture_runtime_snapshot`), outside every target. **Money is real:**
  - `money_owner.read_answer`, `_settle_spoken_commitment`, `money_owner.haggle` and `settled_money` sit in the NPC speech region (#149 lines 2824-3464);
  - shop guards sit in 2276-2352 and 3474-3560;
  - `_coin_paid` and the thread gate sit in `_dispatch_player_turn` 529-569;
  - the money and Undo-marked block 481-598 sits in `_narrate_resolved_turn`.

### Cut rule (spec §12, made precise)

The rule is applied to blocks of 10 or more lines, at the top level of a function body, or one level down with `--sub`.

**Outputs.** A block's outputs are the names it may still have bound when it falls off its end (paths that `return` or `raise` do not count) and that a later block reads. Reads include the captured names of the nested helpers a later block calls.

**Classes:**
- **A:** no `return`, outputs ≤ 5.
- **B:** has a `return`, outputs 0.
- **C:** both (not cut in this slice).
- **D:** a nested `def` (lifted by the shim pattern, Task 4 and Task 8).

**Hazard:** the block calls a nested helper (`finish_turn`, …) and rebinds a name that helper reads from the enclosing scope. The helper would then see the old binding. Hazard blocks are not cut.

**A block is cut only if** it is class A or B, has outputs ≤ 5, has no hazard and contains no `locals()`.

| Function (level) | Rows ≥ 10 lines | Cut yes | Lines cut | A / B / C / D | Hazard |
|---|---|---|---|---|---|
| `_run_player_turn_internal` (top) | 46 | 30 | 752 | 10 / 23 / 8 / 5 | 8 |
| ↳ `--sub 1664` (`if target_id is not None:`) | 2 | 2 | 21 | 1 / 1 / 0 / 0 | 0 |
| ↳ `--sub 2824` (`else` arm of `if shop_request:`) | 7 | 4 | 77 | 2 / 3 / 2 / 0 | 1 |
| ↳ `--sub 2958` (`if experimental_npc_dialogue or …`) | 11 | 9 | 169 | 10 / 1 / 0 / 0 | 1 |
| ↳ `--sub 2984` (`if experimental_npc_dialogue:`) | 2 | 2 | 134 | 2 / 0 / 0 / 0 | 0 |
| `finish_turn` (nested body) | 12 | 11 | 158 | 9 / 2 / 0 / 1 | 0 |
| `_dispatch_player_turn` | 11 | 6 | 126 | 1 / 5 / 5 / 0 | 0 |
| `_narrate_resolved_turn` | 8 | 8 | 219 | 8 / 0 / 0 / 0 | 0 |
| `_narration_safety_decision` (out of scope) | 26 | 14 | 249 | 6 / 8 / 11 / 1 | 0 |

**Cut list:**
- **Full:** 72 block cuts (47 in `_run_player_turn_internal`, 11 in `finish_turn`, 8 in `_narrate_resolved_turn`, 6 in `_dispatch_player_turn`), plus the `finish_turn` shim lift, 4 nested-def lifts and the `_narrate_resolved_turn` move.
- **Minimum:** 19 block cuts plus the shim lift and the move.

**Projected sizes [T]** (call-site cost: about 3 lines per A cut, 4 per B cut):

| Function | Now (#149) | After minimum | After full |
|---|---|---|---|
| `finish_turn` body | 231 (nested) | ≈ 106 in `turn_finish.py`, not frozen | same |
| `_narrate_resolved_turn` | 351 | < 151 in `resolved_narration.py`, not frozen (the 8 cuts reach ≈ 156; Task 6 adds cuts under 10 lines until below 151) | same |
| `_run_player_turn_internal` | 2 741 | ≈ 2 550 (shim) | ≈ 1 500, still frozen |
| `_dispatch_player_turn` | 458 | 458 | ≈ 356, still frozen |
| `game.py` | 1 397 | ≈ 1 060 | ≈ 1 065 |

**Not cut in either version:** the 8 class-C and 8 hazard blocks of `_run_player_turn_internal` top level, including `1664-1902` (239 lines, 8 outputs), `2541-2648` (108, 7) and the 423-line `2958-3380` (hazard). They need either a deeper measurement or a context object, which is a design change. They stay frozen, and a later fix there uses ADR Q1 ("önce taşı, sonra düzelt") at that time.

### Scope of `_narration_safety_decision`: OUT

- B2's plan says new safety rules go into a new module and `_narration_safety_decision` is not grown (YENIDEN_TASARIM_PLANI §B2, "Önce ayrılacak bölge" (2)). B2 therefore does not need it cut.
- It has 72 returns in 131 blocks. Its 14 cuttable rows are only 249 of 1 054 lines, so cutting would not take it under 151.
- Ruling: out — B2 does not edit it and a cut would not unfreeze it — if wrong: one more stage of about 4 tasks, measured by `safety_decision_*.txt`.

## Global Constraints

**Base and order:**
- `TBBASE` is `origin/main` after PR #149 merges. Task 0 measures again on `TBBASE`, and measurement wins over every number above, with one `Ruling` per changed number.
- Freeze: while this slice's branch is open, no other branch touches `ai-dnd/game.py` or `ai-dnd/game_parts/` (spec §12 "Dondurma").

**Identity:**
- "Önce taşı, sonra düzelt" (ADR Q1): every cut is identity-only, with no behaviour change, no fix and no budget raise.
- A bug found during a cut is parked in the ledger and fixed in its own commit after the cut.

**Size:**
- Size budgets only go down. Frozen functions never grow.
- No new `long_functions` key ever appears.
- Every helper is under 151 lines. Each task lowers `files` and `long_functions` in the same commit so that no budget sits more than 50 above its real size.
- `_narrate_resolved_turn` keeps a count of 351 or less under its new key until Task 6 removes the key (ADR Q4).

**Tests:**
- Red test first for every tool and for every non-identity change (Tasks 1, 2, 5).
- A pure cut is proven by `cut_check.py` (Task 1) plus the targeted runs, not by a new red test.
- A new-campaign test fixes the town seed (`api/tests/town_seed.py` → `fixed_town`; travel scenarios use `campaign_seed`).

**Runs:**
- Targeted runs use only `AI-DND-TOOLS/slot.sh 9 <WT> test <label> <timeout> <modules>`.
- Full suites use only `ai-dnd/scripts/engine_split/slot_gate.sh 4 <WT> <label> 3 4500 '.'`.
- Never two full suites at once. Never slots 3 or 5. No browser tests.
- Every targeted run includes the fixed neighbour set: `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys`.
- Every targeted run also includes the engine locks: `api.tests.test_engine_surface api.tests.test_engine_patch_census api.tests.test_engine_routing api.tests.test_engine_sources api.tests.test_engine_size_budget api.tests.test_engine_layout`.
- Every targeted run happens in both flags (`AI_DND_FRONT_PROPOSAL` unset as `-off`; `=1` as `-fon` with `api.tests.gate_boot` first), as in Plan 6.
- Full suites in both flags run only at Task 0 (base), Task 7 (mid gate) and Task 13 (closing gate).

**Review:**
- A cut whose block hits a money marker, or that calls a function listed in `engine_split_locks/sensitive.json`, gets an independent **Opus** review. The same applies to every save-writer or Undo-adjacent change (Tasks 3, 4, 5, 6, 10, 11).
- Other cuts get a Sonnet review that receives the `cut_check.py` verdict.
- The whole-branch review is Opus.
- No Fable anywhere. Ruling: Opus instead of the roadmap's Fable (yol-haritasi §3) — the 2026-11-23 brief says no Fable — if wrong: swap the reviewer model, no task changes.

**Integration:**
- Push, PR and merge follow the S4 grant after green CI.
- No merge to `main` before Kadir's play (S1, S5: at most three slices waiting).
- After every push or merge, run `gh run list --repo kadirkayarr-beep/AI-DND --limit 5`. "AI-DND bounded verification" must be green before "done".
- No force push. Never delete a branch. Keys and `.env` are never read.
- Ledger: `.superpowers/sdd/tur-bolme/progress.md`. Labels: `tb<task>-<step>-<off|fon>`.

## Review Focus

1. **A conditionally rebound output.** Example: `if c: npc_target = x`, where `npc_target` was bound before. The helper must receive the old value as a parameter and return it unchanged on the other path. Without that, the helper raises `UnboundLocalError` where the original kept the old value. Pinned by `test_a_conditionally_rebound_output_is_also_an_input` (Task 1).
2. **Late-bound closure reads.** `finish_turn` reads `allow_new_*` and `expected_location_change` at call time. The shim must read them at call time too, never through a value captured at def time. Pinned by `test_shim_sees_names_rebound_after_its_def` (Task 4) and by `cut_block` refusing hazard blocks (`test_a_block_rebinding_a_captured_name_is_refused`, Task 1).
3. **Fall-through vs `return None`.** A class-B helper that falls off its end must be told apart from a block that `return`s `None`. Pinned by `test_bare_return_inside_a_b_block_is_not_fall_through` (Task 1). The sentinel is `game._TURN_FALL_THROUGH`, never `None`.
4. **A name the receiving part does not bind.** The name reaches the helper bare (a `turn.py` constant, an import alias such as `money_owner`). It must be imported by the new part or prefixed `game.`, as `move_block.py` does. Otherwise it is `NameError` at run time, only on that branch. Pinned by `routing_audit.py` R5/R7 in every task, and by `test_a_turn_py_constant_gets_the_game_prefix` (Task 1).
5. **Order of money side effects in NPC speech.** The order is `money_owner.read_answer`, then `_settle_spoken_commitment`, then `_show_coin_roll`, then `_record_spoken_coin_response`. Writes to `game._session()` must keep their order across the cut (Tasks 10, 11). Pinned by `cut_check.py` (statement order is part of `ast.dump`) plus the Opus review. The targeted set includes the money journeys (`test_journeys`) and the speech-money tests found by Task 0 Step 4.

---

### Task 0: Base, re-measure after #149, baselines

**Files:**
- Create: `.superpowers/sdd/tur-bolme/progress.md`
- Modify: `docs/superpowers/plans/2026-11-23-tur-bolme-measure/` (new `*_base.txt` outputs)

**Interfaces:**
- Produces:
  - `TBBASE` (sha);
  - `*_base.txt` inventories;
  - `cuts-base.json`, the cut list in block-anchor form, used by Tasks 3-12: rows `{function, sub, anchor, occurrence, class, outputs, inputs, flags, task}`. `anchor` is the block's first source line stripped; `occurrence` counts equal anchors in the function. Rule 3: no line numbers in briefs;
  - the targeted money/speech test list `money_tests.txt`.

- [ ] **Step 1: Precondition.** `git log origin/main --oneline -1` contains PR #149's merge. If not, stop the slice; it waits (do not measure on the PR branch again). Record `TBBASE` in the ledger.
- [ ] **Step 2: Re-measure.** From the worktree root run `bash docs/superpowers/plans/2026-11-23-tur-bolme-measure/run_all.sh origin/main base`. Then read the `--sub` start lines from `run_internal_base.txt` (the four statements named in the cut-rule table) and re-run with them. Expected: every `CUTSUM` within ±3 rows of the `149` numbers. A larger difference gets a `Ruling` per number and updates the plan's tables in this task's commit.
- [ ] **Step 3: Write `cuts-base.json`** from the `CUT yes` rows. Assign tasks: `finish_turn` rows → T3; `_narrate_resolved_turn` → T6; `_run_player_turn_internal` top level without money flags and starting before the `if held_plan is not None:` block, plus `--sub` of `if target_id is not None:` → T9a; the rest without money flags → T9b; money-flagged top-level rows → T10; `--sub` rows under `if shop_request:` → T11a (the `else` arm and `if experimental_npc_dialogue:`) and T11b (`if experimental_npc_dialogue or …`); `_dispatch_player_turn` → T12.
- [ ] **Step 4: Money tests.** Find the test modules that drive `_settle_spoken_commitment`, `money_owner.haggle` and `money_owner.read_answer`. Use `grep -l` over `ai-dnd/api/tests` for each name and for `coin_answer` and `price_negotiation`. Save the list as `money_tests.txt`.
- [ ] **Step 5: Baselines.** Run full suites `slot_gate.sh 4 <WT> tb0-base-off 3 4500 '.'` and then `tb0-base-fon`, one after the other. Expected: `failing_ids 0` in both. Any failure is traced to its commit (CLAUDE.md "Bilinen kırıklar") before Task 1.
- [ ] **Step 6: Commit** the measure outputs, `cuts-base.json`, `money_tests.txt` and the ledger: `git commit -m "Turn split T0: re-measure on TBBASE, cut list, baselines"`.

### Task 1: `cut_block.py` and `cut_check.py` (the cut tool)

**Files:**
- Create: `ai-dnd/scripts/engine_split/cut_block.py`
- Create: `ai-dnd/scripts/engine_split/cut_check.py`
- Test: `ai-dnd/api/tests/test_engine_cut_tool.py`

**Interfaces:**
- Consumes:
  - `block_io.py`'s analysis: copy `Scan`, `function_free`, `flow_stores` into `cut_block.py`; the measure folder is not importable;
  - `move_block.py`'s `game.`-prefix rule and census reading.
- Produces:
  - `python scripts/engine_split/cut_block.py --file F --function NAME[.NESTED] --anchor TEXT [--occurrence N] [--sub-anchor TEXT] --helper _NAME --part game_parts/X.py --census api/tests/engine_split_locks/patch_census.json [--report out.json]`. It edits `F`, `game_parts/X.py` (created with `import game` if missing) and `game.py` (re-export line and `_PART_MODULES` entry). On refusal it prints `REFUSED <reason>`, exits 2 and writes nothing.
  - `python scripts/engine_split/cut_check.py --base-root <archive>/ai-dnd --root . --report out.json`. It prints `CHANGED 0` on identity and exits 0.
  - Class A call shape: `o1, o2 = game._NAME(i1=i1, i2=i2)`. Helper: `def _NAME(*, i1, i2):`, then the block dedented, then `return o1, o2`. One output gives `o1 = game._NAME(...)` and `return o1`. Zero outputs give a bare call and no `return`.
  - Class B call shape: `_exit = game._NAME(...)`, then `if _exit is not game._TURN_FALL_THROUGH:`, then `return _exit`. Helper ends with `return _TURN_FALL_THROUGH`.
  - `_TURN_FALL_THROUGH = object()` lives in `game_parts/turn_cuts_common.py`, re-exported by `game.py`.
  - Parameters: every input; every output already bound before the block; every nested helper called (for example `finish_turn`). Sorted, keyword-only.

- [ ] **Step 1: Write the failing tests** in `test_engine_cut_tool.py`. Each test runs the tool on a small source fixture in a temp dir and asserts on the exit code, the `REFUSED` line, or the produced text:
  - `test_class_a_block_becomes_a_call_and_a_helper`: output text equals the expected fixture exactly;
  - `test_class_b_block_returns_through_the_sentinel`;
  - `test_bare_return_inside_a_b_block_is_not_fall_through`: execute both versions with the fixture inputs and assert the same return value `None`;
  - `test_a_conditionally_rebound_output_is_also_an_input`: execute both versions on both branch values;
  - `test_a_block_rebinding_a_captured_name_is_refused`: `REFUSED hazard npc_target`;
  - `test_more_than_five_outputs_is_refused`;
  - `test_class_c_is_refused`;
  - `test_locals_globals_vars_yield_await_nonlocal_global_are_refused`: one fixture each;
  - `test_break_or_continue_leaving_the_block_is_refused`;
  - `test_a_turn_py_constant_gets_the_game_prefix`;
  - `test_cut_check_reports_changed_0_for_a_clean_cut`;
  - `test_cut_check_reports_a_changed_statement`;
  - `test_cut_check_reports_a_lost_comment`.
- [ ] **Step 2: Run them to verify they fail.** Run `slot.sh 9 <WT> test tb1-2-off 900 api.tests.test_engine_cut_tool` and the `-fon` twin. Expected: FAIL / ERROR (module missing).
- [ ] **Step 3: Implement `cut_block.py`.** Byte-for-byte text cut: the block's source lines, dedented by the block's own indent. Refusal order: anchor not found or ambiguous; forbidden construct; class C; outputs above 5; hazard; resulting helper of 151 lines or more.
- [ ] **Step 4: Implement `cut_check.py`.** For each helper named in `--report`:
  - compare `ast.dump` of the helper body (without the added trailing `return`) with the original block (from `--base-root`), after folding added `game.X` back to `X`;
  - compare the comment token stream as `move_check.py` does;
  - check the call-site shape.
- [ ] **Step 5: Run the tests** (same two runs). Expected: PASS. Then the neighbour set and engine locks in both flags. Expected: `failing_ids 0`.
- [ ] **Step 6: Review.** Sonnet reviewer. Its brief: the five Review Focus items, and the question whether a refusal case is missing.
- [ ] **Step 7: Commit:** `git commit -m "Turn split T1: cut_block and cut_check tools with tests"`.

### Task 2: Replace `locals().get('preparsed_scene_intent')`

**Files:**
- Modify: `ai-dnd/game_parts/turn.py` (`_run_player_turn_internal`, the `if (` block that holds `locals()`)
- Test: `ai-dnd/api/tests/test_engine_routing.py` (new test), plus one characterization test in the module that already drives the preparsed local-person branch (find it with `grep -l "_validated_local_person_proposal" ai-dnd/api/tests`; if none, add it to `ai-dnd/api/tests/test_engine_cut_tool.py`)

- [ ] **Step 1: Write the failing test** `test_no_engine_file_calls_locals_globals_or_vars`. It scans `ai-dnd/game.py` and `ai-dnd/game_parts/*.py` with `ast` and asserts that no `Call` has a `Name` func in `{"locals", "globals", "vars"}`. It is red today with exactly one hit, in `turn.py`.
- [ ] **Step 2: Characterize.** Write `test_preparsed_local_person_still_materializes`. It uses a fixed town seed and a turn whose preparsed intent is a valid local-person proposal, and asserts the `"dialogue"` result with the created NPC id. It is green before the change.
- [ ] **Step 3: Replace the call.** Change `isinstance(locals().get("preparsed_scene_intent"), dict)` to `isinstance(preparsed_scene_intent, dict)`. Nothing else changes. Equivalence holds because the name is bound unconditionally at function entry [D].
- [ ] **Step 4: Run** both tests, the neighbour set and the engine locks in both flags. Expected: PASS, `failing_ids 0`. `_run_player_turn_internal` does not grow (the line count stays equal).
- [ ] **Step 5: Review.** Cheap Sonnet re-review (one-line change with a red-green test). Ledger `Ruling`.
- [ ] **Step 6: Commit:** `git commit -m "Turn split T2: preparsed_scene_intent read by name, not locals()"`.

### Stage 1: minimum set for B2 (Tasks 3-7)

### Task 3: Cut `finish_turn`'s inner blocks (11 cuts)

**Files:**
- Create: `ai-dnd/game_parts/turn_finish.py`
- Modify: `ai-dnd/game_parts/turn.py`, `ai-dnd/game.py` (re-export), `ai-dnd/api/tests/engine_split_locks/{surface.json,size_budget.json}`

**Interfaces:**
- Consumes: Task 1's tools; the `cuts-base.json` rows with `task: "T3"`.
- Produces: helpers named `_tf_<what>` in `turn_finish.py` (the implementer picks `<what>` from the block's job, for example `_tf_engine_event_evidence`). `finish_turn` stays nested and shrinks to about 106 lines [T].

- [ ] **Step 1: Cut each row.** For each T3 row, in file order from the bottom up (so the anchors above stay valid), run `cut_block.py --function _run_player_turn_internal.finish_turn --anchor ...`. A `REFUSED` row is parked with its reason and skipped.
- [ ] **Step 2: Check identity.** Run `cut_check.py --base-root <git archive TBBASE>/ai-dnd`. Expected: `CHANGED 0`.
- [ ] **Step 3: Update the locks.** Regenerate `surface.json` the way Plan 3 did (`surface.py`; added names only). Lower `size_budget.json` (`turn.py`, `_run_player_turn_internal`) to the real size + 0 (≤ 50 slack rule). Run `routing_audit.py`; expected: no finding.
- [ ] **Step 4: Run** the neighbour set, the engine locks, `money_tests.txt` and the modules that patch `_natural_unresolved_action_response` or `ResolvedTurn`, in both flags. Expected: `failing_ids 0`.
- [ ] **Step 5: Review.** Opus independent review (two blocks carry money markers; the `ResolvedTurn` build is in scope). Brief: the diff, the `cut_check` report and Review Focus 1-4.
- [ ] **Step 6: Commit:** `git commit -m "Turn split T3: finish_turn inner blocks cut into turn_finish.py"`.

### Task 4: Lift `finish_turn`'s body behind a shim

**Files:**
- Modify: `ai-dnd/game_parts/turn_finish.py`, `ai-dnd/game_parts/turn.py`, `ai-dnd/game.py`, the locks
- Test: `ai-dnd/api/tests/test_engine_cut_tool.py` (shim test)

**Interfaces:**
- Produces: `turn_finish._finish_turn(*, action_result, narration, quest_outcomes, safety_reason_code, safety_handling, record_safety, is_final, <the captured names from Task 0's finish_turn inputs list, sorted>)`. It returns what `finish_turn` returned.
- The nested `finish_turn` keeps its exact signature. Its body becomes one `return game._finish_turn(...)` call that passes every captured name by keyword. It reads them at call time, so late binding holds.
- `narration_model_calls` becomes a parameter of `_finish_turn`, so the inner `nonlocal` binds to it. No write-back is needed (every caller returns at once [D: 55 of 55]).

- [ ] **Step 1: Write the failing test** `test_shim_sees_names_rebound_after_its_def`. In a fixture, a nested function is defined, a captured name is rebound after it, and the function is called. Assert that the lifted version returns the rebound value. Run it with a second fixture where the shim captures at def time (wrong), and assert that the check fails.
- [ ] **Step 2: Hand edit or tool.** Prefer extending `cut_block.py` with `--lift-nested` if the shim can be generated mechanically (a body move plus a generated call). Otherwise do a hand edit, checked by `cut_check.py --nested`.
- [ ] **Step 3: Check identity.** `cut_check.py` expected `CHANGED 0`. The shim body is the only new code.
- [ ] **Step 4: Update the locks** as in Task 3. `_finish_turn` must be under 151 lines.
- [ ] **Step 5: Run** as in Task 3 Step 4.
- [ ] **Step 6: Review.** Opus independent review.
- [ ] **Step 7: Commit:** `git commit -m "Turn split T4: finish_turn body lives in turn_finish._finish_turn behind a shim"`.

### Task 5: Move `_narrate_resolved_turn` out of `game.py` (D-474)

**Files:**
- Create: `ai-dnd/game_parts/resolved_narration.py`
- Modify: `ai-dnd/game.py`, the locks
- Test: the module chosen in Step 1 (save-writer pin)

**Interfaces:**
- Produces: `game_parts/resolved_narration.py::_narrate_resolved_turn(resolved_turn: "ResolvedTurn", player_input, messages, target_id)`, re-exported as `game._narrate_resolved_turn`. The size key `game_parts/resolved_narration.py::_narrate_resolved_turn` is 351 or less.

- [ ] **Step 1: P5T5-8 pin (red first).** Trace whether any of `test_campaign_api`, `test_step0_commit_failures`, `test_stage10a_gameplay_repairs` or `test_adventure_session` drives the travel branch → `GameSession.evaluate_quest_events` → `_forfeit_unrecordable_xp`. If none does, write `test_travel_turn_forfeits_a_refused_quest_award`. It uses a fixed town seed: a travel turn completes a `visit_location` quest, the award is refused, and the XP is forfeited. Show it is red with the branch stubbed out, then green on `TBBASE`.
- [ ] **Step 2: P5T4-1 (red first).** Record the refusal first: `move_block.py --names _narrate_resolved_turn` on `TBBASE` prints `REFUSED engine name 'ResolvedTurn' in a annotation`. Then quote the annotation in `game.py` as `resolved_turn: "ResolvedTurn"`. `game.py` already has `from __future__ import annotations` (D-478), so `__annotations__` is unchanged. Pin that with `test_narrate_resolved_turn_annotations_are_unchanged` (`inspect.get_annotations(game._narrate_resolved_turn) == {"resolved_turn": "ResolvedTurn"}`; green before and after). Ruling: quote instead of adding the future import to parts — no N3 rule change — if wrong: the other D-478 option, its own task.
- [ ] **Step 3: Move.** `move_block.py --game game.py --part game_parts/resolved_narration.py --names _narrate_resolved_turn --census ...`. Then `move_check.py --tier strong`. Expected: `CHANGED 0`.
- [ ] **Step 4: Locks.**
  - Move the key from `game.py::_narrate_resolved_turn` to the new key with count 351 or less, and mark the approval row "gevşetme olabilir" (ADR Q4).
  - Lower `files["game.py"]`. Run `blank_runs.py` if the move leaves runs of more than 2 blank lines.
  - Update `surface.json` (module change of one name only, `test_only_the_module_of_a_moved_name_may_change`).
- [ ] **Step 5: Run** the neighbour set, the engine locks, `money_tests.txt` and the P5T5-8 pin, in both flags.
- [ ] **Step 6: Review.** Opus independent review (save-writer path).
- [ ] **Step 7: Commit** in two commits: first the pin and the annotation quote (`"Turn split T5a: save-writer pin and quoted ResolvedTurn annotation"`), then the move (`"Turn split T5b: _narrate_resolved_turn moves to resolved_narration.py"`).

### Task 6: Cut `_narrate_resolved_turn` below 151 lines

**Files:**
- Modify: `ai-dnd/game_parts/resolved_narration.py`, `ai-dnd/game.py` (re-exports), the locks

- [ ] **Step 1: Cut the 8 T6 rows**, bottom up, into helpers `_rn_<what>` in the same part. Then re-run `block_io.py` on the result. If the function is still 151 lines or more [T: ≈ 156], cut the next-largest class-A or class-B blocks under 10 lines (from `block_io.py`'s full table) until it is below 151.
- [ ] **Step 2: Check identity.** `cut_check.py` expected `CHANGED 0`.
- [ ] **Step 3: Remove the key.** Delete the `long_functions` key (the function is no longer long) and lower `files`.
- [ ] **Step 4: Run** as in Task 5 Step 5.
- [ ] **Step 5: Review.** Opus independent review (block `if not narration_only:` carries money, Undo-adjacent and session-write markers).
- [ ] **Step 6: Commit:** `git commit -m "Turn split T6: _narrate_resolved_turn below the freeze line"`.

### Task 7: Mid gate and Kadir's first play (end of the minimum version)

- [ ] **Step 1: Full suites.** Run `slot_gate.sh 4 <WT> tb7-gate-off 3 4500 '.'`, then `tb7-gate-fon`. Expected: `failing_ids 0` in both.
- [ ] **Step 2: Speed.** Repeat Plan 6 Ruling B's A/B speed pairs (`api.tests.bench_engine_turn`, OLD = `TBBASE`, NEW = the stage tip). A ratio above 1.10 stops the slice and is reported.
- [ ] **Step 3: Stage review.** Opus stage review on `git diff TBBASE...HEAD`.
- [ ] **Step 4: PR.** Push, open the PR "Turn split stage 1" and check CI. No merge before the play.
- [ ] **Step 5: Kadir plays at least 10 minutes.** Mid checklist (Turkish, for Kadir):
  - [ ] Bir NPC ile konuş; cevap sahneyle ilgili mi?
  - [ ] Bir dükkândan bir şey al ve sat; para doğru mu değişti?
  - [ ] Bilinen bir yere yürü; varış anlatımı geliyor mu?
  - [ ] Bir dövüş turu oyna; vuruş ve can doğru görünüyor mu?
  - [ ] Kaydet, çık, yükle; her şey yerinde mi?
  - [ ] Bir hamleyi Geri Al; önceki hâle döndü mü?
- [ ] **Step 6: Merge** after his "tamam" (S1). Ledger "oynayış yapıldı". **If Kadir chose the minimum version, the slice ends here.** Run `graphify update .` and write the morning summary.

### Stage 2: rest of the turn core (Tasks 8-14, full version only)

### Task 8: Lift the other nested defs

**Files:** `ai-dnd/game_parts/turn_exits.py` (create), `turn.py`, `game.py`, the locks.

- [ ] **Step 1: Lift the two closure-free defs.** `procedural_entity_ids` (1 enclosing input [D]) and `validate_interaction_conversation` (2 [D]) become module-level helpers in `turn_exits.py`. Their call sites pass the inputs.
- [ ] **Step 2: Shim the two closure defs.** `finish_conversation_rejection` and `finish_conversation_resolution` close over `finish_turn` and 2-3 names [D]. They get Task 4's shim pattern.
- [ ] **Step 3: Check and run.** `cut_check.py` expected `CHANGED 0`. Lower the locks. Run the neighbour set and engine locks in both flags.
- [ ] **Step 4: Review.** Sonnet review.
- [ ] **Step 5: Commit:** `git commit -m "Turn split T8: nested helpers lifted"`.

### Task 9a / 9b: Non-money cuts in `_run_player_turn_internal`

**Files:**
- `ai-dnd/game_parts/turn_exits.py`
- `turn.py`, `game.py`, the locks

**Task 9a (≈ 12 rows):**
- [ ] **Step 1: Cut** every `T9a` row from `cuts-base.json`, bottom up, into `_tx_<what>`. The rows are the top-level A/B rows before the `if held_plan is not None:` block plus the 2 rows of `--sub` `if target_id is not None:`. Rows whose block calls a `sensitive.json` function move to Task 10.
  - **T9a note:** two T9a rows are flagged `undo` (lines 1002-1011) and `save` (lines 1433-1506) in `cuts-base.json`. They are not money, but they touch Undo and save order. Check the order (Undo before save) and use the strong reviewer (Opus) for T9a.
  - **T9a note 2:** rows 27 and 29 (lines 1399-1430, 1508-1534) call `ensure_combat_state`, `_mark_combat_action_used`, `_resolve_player_death_turn`, which are `save` in `sensitive.json`. The whole of T9a gets the Opus review.
  - **Moved to T10 (fix round 2):** three rows call `sensitive.json` functions with no money flag: `plan_living_world_turn` (lines 1388-1398), `parse_player_intent` (2195-2211), `validate_world_updates` (3585-3601). They are in T10 and get the Opus review.
- [ ] **Step 2: Check identity.** `cut_check.py` expected `CHANGED 0`.
- [ ] **Step 3: Update the locks.** Lower them. Every helper is under 151 lines.
- [ ] **Step 4: Run** the neighbour set and engine locks in both flags.
- [ ] **Step 5: Review.** Opus review with the `cut_check` report (T9a holds `sensitive.json` save callers).
- [ ] **Step 6: Commit:** `git commit -m "Turn split T9a: turn exits cut (first half)"`.

**Task 9b (≈ 9 rows):** the same steps for the `T9b` rows. Commit message: `"Turn split T9b: turn exits cut (second half)"`.

### Task 10: Money-guard cuts in `_run_player_turn_internal` (≈ 11 rows)

**Files:** `ai-dnd/game_parts/turn_shop_guards.py` (create), `turn.py`, `game.py`, the locks.

- [ ] **Step 1: Cut** the `T10` rows (the shop guards and the findings blocks with money markers), bottom up, into `_tg_<what>`.
- [ ] **Step 2: Check identity.** `cut_check.py` expected `CHANGED 0`. Lower the locks.
- [ ] **Step 3: Run** the neighbour set, the engine locks and `money_tests.txt` in both flags.
- [ ] **Step 4: Review.** Opus independent review (Review Focus 5).
- [ ] **Step 5: Commit:** `git commit -m "Turn split T10: shop guards cut"`.

### Task 11a / 11b: NPC speech region sub-cuts (6 + 9 rows)

**Files:** `ai-dnd/game_parts/turn_speech.py` (create), `turn.py`, `game.py`, the locks.

- [ ] **Step 1: Cut.** Task 11a cuts the `T11a` rows (the `else` arm of `if shop_request:` and `if experimental_npc_dialogue:`; this includes `_settle_spoken_commitment`). Task 11b cuts the `T11b` rows. Use `cut_block.py --sub-anchor`, bottom up, into `_ts_<what>`.
- [ ] **Step 2: Check identity.** `cut_check.py` expected `CHANGED 0`. Lower the locks.
- [ ] **Step 3: Run** the neighbour set, the engine locks and `money_tests.txt` in both flags.
- [ ] **Step 4: Review.** Opus independent review per task (Review Focus 1 and 5).
- [ ] **Step 5: Commit:** `"Turn split T11a: speech money blocks cut"` / `"Turn split T11b: speech reply blocks cut"`.

### Task 12: `_dispatch_player_turn` cuts (6 rows)

**Files:** `ai-dnd/game_parts/turn_dispatch_steps.py` (create), `turn.py`, `game.py`, the locks.

- [ ] **Step 1: Cut** the `T12` rows into `_td_<what>`.
- [ ] **Step 2: Check identity.** `cut_check.py` expected `CHANGED 0`. Lower the locks (`_dispatch_player_turn` ≈ 356 [T]).
- [ ] **Step 3: Run** the neighbour set and engine locks in both flags.
- [ ] **Step 4: Review.** Sonnet review. Use Opus instead if a row calls a `sensitive.json` function (the death-turn block with session writes is the likely one).
- [ ] **Step 5: Commit:** `git commit -m "Turn split T12: dispatch steps cut"`.

### Task 13: Closing gate

- [ ] **Step 1: Final measurement.** Run `run_all.sh HEAD final` and save it. Confirm every new part is ≤ 2 500 lines and every helper is under 151 lines. Set the final budgets to the real sizes.
- [ ] **Step 2: Full suites.** Run `tb13-gate-off`, then `tb13-gate-fon`. Expected: `failing_ids 0`.
- [ ] **Step 3: Speed.** Speed pairs as in Task 7 (cumulative against `TBBASE`).
- [ ] **Step 4: Whole-branch review.** Opus reviews `git diff TBBASE...HEAD`.
- [ ] **Step 5: PR.** Push, open the PR "Turn split stage 2", check CI, then run `graphify update .`.

### Task 14: Kadir's closing play

- [ ] **Step 1: Kadir plays at least 10 minutes.** Closing checklist:
  - [ ] Bir NPC'ye para teklif et ya da pazarlık yap; para ve cevap doğru mu?
  - [ ] Bir NPC'ye bilmediği bir şey sor; uydurma bilgi vermiyor mu?
  - [ ] Bir dükkânda al-sat yap; fiş ve kese tutuyor mu?
  - [ ] Yeni bir yere git ve etrafı incele; sonuç anlatılıyor mu?
  - [ ] Dövüşte ölümle yüz yüze gel (ölüm zarı); tur doğru ilerliyor mu?
  - [ ] Kaydet, yükle, Geri Al; hepsi çalışıyor mu?
- [ ] **Step 2: Merge** after his "tamam". Ledger "oynayış yapıldı". Write the morning summary.

## Estimate [T] (all numbers are guesses, not measurements)

How the numbers were built:
- Plans 3-6 took 0.3-1.2 calendar days each (`docs/design/YOL_HARITASI.md`). Their total tokens were not measured. Plan 6's continuation run alone used about 1.87 M, with no moves.
- Assumed cost per dispatch:
  - Sonnet implementer ≈ 200 k tokens (reads the big function in ranges);
  - Sonnet review ≈ 80 k;
  - Opus review ≈ 150 k;
  - controller ≈ 60 k per task;
  - +25 % for fix loops.
- A full suite takes about 42 minutes (D-491: ~2 500 s).

| | Minimum (yol 2: Tasks 0-7) | Full (yol 1: Tasks 0-14) |
|---|---|---|
| Calendar days | 1-2 (≈ 1.5) | 3-4.5 (≈ 3.5) |
| Sonnet implementer dispatches | 8 | 16 |
| Sonnet review dispatches | 2 | 6 |
| Opus review dispatches | 5 (T3, T4, T5, T6, T7 stage) | 10 (+T10, T11a, T11b, T13 whole branch, T12 if sensitive) |
| Fable / Haiku | 0 / 0 | 0 / 0 |
| Tokens, Stage 0 (T0-T2) | ≈ 0.9 M | ≈ 0.9 M |
| Tokens, Stage 1 (T3-T7) | ≈ 2.9 M | ≈ 2.9 M |
| Tokens, Stage 2 (T8-T14) | — | ≈ 3.7 M |
| **Tokens total** | **≈ 3.8 M (range 3-5 M)** | **≈ 7.5 M (range 6-10 M)** |
| Full-suite runs (both flags) | 4 (T0 ×2, T7 ×2) | 6 (+T13 ×2) |
| Owner plays | 1 (mid) | 2 (mid, end) |

What each buys:
- **Minimum:** B2 edits `_finish_turn` and `_narrate_resolved_turn`, both unfrozen. `_run_player_turn_internal` (≈ 2 550) and `_dispatch_player_turn` (458) stay frozen. A later fix inside them pays a "move first" task at that time.
- **Full:** `_run_player_turn_internal` shrinks to ≈ 1 500 and `_dispatch_player_turn` to ≈ 356. Both are still frozen, so the full version does not unfreeze the core either. It only makes future "move first" tasks smaller and more frequent hits land in small helpers.

## When the plan stops early or shrinks

- **#149 not merged:** Task 0 does not start.
- **Stage boundary:** Kadir picks the minimum version, or the weekly token limit runs out during Stage 2. The slice ends after Task 7. Stage 2 rows go to the ledger as parks with their `cuts-base.json` rows, and nothing is half-cut. Each task is self-contained.
- **Refusals:** `cut_block.py` refuses more than 30 % of a task's rows. Park them and finish the task with the rest. If the minimum set cannot reach "under 151" for `_finish_turn` or `_narrate_resolved_turn`, stop and report: then B2 needs the context-object design (a new spec).
- **Identity:** `cut_check.py` shows `CHANGED` above 0. Redo the cut from scratch; never patch it forward.
- **Speed:** a speed ratio above 1.10 at Task 7 or Task 13 stops the slice and is reported.
- **New failures:** a targeted run shows a failure that `TBBASE` did not have. Trace it to its commit and fix or revert that cut. Never accept it as "zaten kırıktı".
- **Overrun:** an estimate overrun does not stop the slice (S3). It is written to the roadmap with its reason.

## Owner questions

1. **Minimum or full?** My recommendation: the minimum (Tasks 0-7) now, then B2. The full version costs about twice as much and still leaves both core functions frozen. Do Stage 2 later, only if B2 or B3 work keeps landing in those functions.
2. **Is a Sonnet review plus `cut_check.py` enough as the spec's "güçlü inceleme" for cuts without money, save or Undo?** My recommendation: yes. The tool proves identity mechanically, and Opus stays on every money/save/Undo cut and on the whole branch. This is on the approval list as "gevşetme olabilir".
3. **Opus instead of Fable for this slice?** The roadmap (§3) said Fable; the 2026-11-23 brief says no Fable. My recommendation: Opus.

## Self-review (writing-plans checklist)

- **Spec coverage:**
  - §12 block I/O dump: measure folder, Task 0.
  - Cut only blocks with ≤ 5 outputs: cut rule, `cut_block.py`.
  - `locals()` first, with its own red test: Task 2, before any cut.
  - Strong review per extraction: Tasks 3-12 (owner question 2).
  - ADR Q4 and `_narrate_resolved_turn` ≤ 351: Tasks 5-6.
  - Size budget only down: Global Constraints, every task.
  - Yol-haritasi row 4: plays in Tasks 7 and 14. S1/S5: no merge before play.
  - B2 reason: Stage 1.
- **Steps:**
  - Cut rows are named by anchor through `cuts-base.json`, not by line (rule 3).
  - Helper names are left to the implementer by prefix (`_tf_`, `_rn_`, `_tx_`, `_tg_`, `_ts_`, `_td_`); the tool and the re-export lock catch duplicates.
- **Type consistency:**
  - `_TURN_FALL_THROUGH`, `_finish_turn` and `cuts-base.json` fields are defined in Tasks 0, 1 and 4 and used with the same names later.
- **Review Focus:** each of the 5 lines names its pinning test and owning task.
- **Proportion:** no function bodies in the plan. The cut shapes are the only code-level decisions.
