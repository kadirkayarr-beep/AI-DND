# game.py Split, Plan 3 (T4 low-impact areas: character_rules, places, intent, dialogue, lore, narration, narration_safety, living_world_turn, new_game, to spec TM3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the 241 non-sensitive names of spec stage T4 (about 7 363 lines; 15 names that reach a money, death or save/Undo writer, or are helpers of only those, held for Plan 4, appendix A "Fix-wave holds" and "Fix-wave 2 holds") out of `ai-dnd/game.py` into seven new parts and the existing `character_rules.py`, move `_EXPERIMENTAL_NPC_SPEECH_OPTIONS` to `schemas.py` as the live proof of the D-376 fix, and pass spec gate TM3. TM3 ends with Kadir playing for at least 10 minutes.

**Architecture:** Unchanged from Plans 1-2. Moved code lives in `ai-dnd/game_parts/`. It reaches engine names as `game.X` (centre rule), with the prefix added in place by the mover. `game.py` re-exports every moved name with explicit `from game_parts.<part> import ...` lines. Every new part with a re-exported function joins `_PART_MODULES`, so the session wrapper still binds it. Stage A first fixes the net debts that a T4 move can hit, then rehearses the whole move on a throwaway branch to measure the turn cost of the `game.X` reads before any real move.

**Tech Stack:** Python stdlib (`ast`, `symtable`, `tokenize`, `unittest`, `sys.monitoring`); guarded WSL runner `slot.sh`; repo gate runner `ai-dnd/scripts/engine_split/slot_gate.sh`; `ruff==0.17.5` through `uvx` (second opinion only, never `--fix`/`format`).

**Spec:** `docs/superpowers/specs/2026-11-17-game-py-bolme-design.md` (approved 2026-11-17). The spec is the authority; where this plan and the spec differ without a `Ruling` line, the spec wins. Plan 2 (`docs/superpowers/plans/2026-11-18-game-py-bolme-plan-2.md`) and its ledger (`C:/Users/Kadir/Desktop/AI-DND-k2-bolme-t3n/.superpowers/sdd/2026-11-18-game-py-bolme-plan-2/progress.md`) hold the rulings this plan builds on.

**Appendix:** `docs/superpowers/plans/2026-11-19-game-py-bolme-plan-3-appendix.md` holds the measured module map, the 14 batch lists with header imports and census targets, the risk checks and the commands. The read-only measurement scripts (`module_map.py`, `batches.py`, `t4_checks.py`, from the fix wave `money_scan.py`, `walrus_probe.py`, and from fix wave 2 `writer_scan.py`) and `overrides-extra.json` are in `docs/superpowers/plans/2026-11-19-game-py-bolme-plan-3-measure/`.

**Scope:** spec rows T4.1-T4.9 and gate TM3, plus every debt row whose trigger names Plan 3, T4 or TM3 (table "Debt rows this plan owns"). Sensitive names in T4 topics (27, appendix E) stay for Plan 4/5. Plans 4-6: outline at the end.

**Gates in this plan:** G4a = net gate (Task 6): Stage A reviewed, PR 6. TM3 = spec TM3 (Task 17): the N4/N7 bases and the gate suites, PR 7 stacked on PR 6, then Kadir's play.

**Measured base (2026-11-19, read-only, `origin/main` `b1150df8`, Windows Python 3.14; appendix B):**
- `game.py` 22 670 lines, 468 top-level names, 228 already re-exported.
- Parts: `terminal`, `character_rules`, `tables`, `schemas`, `text_rules_a`, `text_rules_b`.
- `_PART_MODULES = ("game_parts.character_rules", "game_parts.text_rules_a", "game_parts.text_rules_b")`.
- Comments 1 083.
- Speed:
  - TM0: suite 1 959 s flag off; turn bench 21.03 / 21.14 ms. Limits: 2 155 s, 23.13 / 23.25 ms.
  - TM2: suite 1 642 s off, 1 640 s fon; bench 22.93 / 21.02 ms.
  - Headroom on bench reading 1: 0.2 ms (D-380 item 8).
- `origin/main` is now `36daaa1b`: PR #133 merged, tests only, `game.py` unchanged. The flag-on job (`task/fon-a`, `task/fon-b`) changes `game.py` by about 65 lines in the turn and coin regions. Task 0 measures again after it merges.

## Global Constraints

- **Precondition and execution base.**
  - `origin/main` must contain `b1150df8` (Plan 2), `36daaa1b` (PR #133, fixed-town tests) and the merged flag-on PR (`task/fon-a` with `task/fon-b`; D-369/370/371). Kadir has approved this plan.
  - `P3BASE` = that main commit. Task 0 does three things on it:
    - regenerates N1 (`surface.json`), N2 (`patch_census.json`) and the size count, and expects them byte-equal to the committed locks;
    - checks `sensitive.json` against `sensitivity.classify`;
    - measures the module map again.
  - If the flag-on PR is not merged, Plan 3 does not start: Kadir is told.
- **The flag.** `AI_DND_FRONT_PROPOSAL=1` is the local-play default (`api.local_play`). Every targeted run of this plan happens twice:
  - **flag on:** label `<run>-fon`; `api.tests.gate_boot` first in the module list and `api.tests.test_engine_gate_boot` in it. The dash-separated token `fon` turns the flag on; `slot_gate.sh` refuses a glued token (949c3513).
  - **flag off:** label `<run>-off`. The label never contains the letters `fon`.
  - Labels follow one pattern, written by the controller: `p3t<task>-<batch or step>-<off|fon>`. `slot.sh` itself does not check labels (D-359).
  - Never `slot.sh ... par`: it mixes the flag state across shards (Plan 2 park P2).
- **`F_fon`.** The flag-on job's aim is `F_fon = ∅`. Task 0 reads its final state.
  - Pass rule at every gate: flag off `failing_ids 0` and flag on `failing_ids 0`.
  - Ruling: if Task 0 or the TM3 bases show a flag-on red, Plan 2's `F_fon` rule applies to those ids only. That means: trace the commit, write a debt row, tell Kadir; `failing_ids ⊆ F_fon`; no `LOST` id outside `F_fon`; a batch name an `F_fon` test reads is held. Any other red stops the plan. If wrong: a pre-existing flag-on fault rides one plan longer, visible in the register.
- **Worktrees and branches.**
  - Stage A: `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-t4n`, branch `task/game-py-bolme-t4-nets` off `P3BASE`.
  - Stage B: `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-t4`, branch `task/game-py-bolme-t4` cut from the Stage A tip.
  - Rehearsal (Task 5): `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-t4p`, local branch `tmp/game-py-bolme-t4-prova`; never pushed, not deleted.
  - TM3 bases (Task 17): detached worktree `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-t4b` at the Stage A tip merged (locally, detached) with the same `origin/main` commit Task 17 Step 1 merged into Stage B.
  - Ruling: Stage B is stacked on Stage A and does not wait for PR 6's merge (as Plans 1-2). If wrong: one rebase.
  - One writer per worktree.
- **Push, PR, merge:**
  - Only with Kadir's fresh approval for that action. No force push. Never delete a branch. Before a merge, check that the target tip is an ancestor of the merged branch (no commit lost).
  - After every push or merge: `gh run list --repo kadirkayarr-beep/AI-DND --limit 5`. "AI-DND bounded verification" must be green before "done".
  - CI wait: poll every 2-3 min for at most 25 min.
  - A red run is reported at once. Download its evidence (`gh run view <id> --log-failed` into the ledger dir) before any rerun. Rerun only the failed job.
  - A suspected flake is proven with a 40-fixed-town-seed probe of that test, never by bisect (CLAUDE.md flake rule).
  - Local work never waits for an approval; only the push does.
- **Freeze (spec decision 3):** while either branch is open, no other branch touches `ai-dnd/game.py` or `ai-dnd/game_parts/`.
- **Slots:** `SLOT = 2` for targeted runs, `FSLOT = 4` for `slot_gate.sh` and benches. Slots 3 and 5 belong to others: never take them. `WT` = worktree folder name only.
  - Targeted: `bash C:/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh <SLOT> <WT> test <label> 1800 <modules...> <NEIGHBOURS>`. Pass = a line `RESULT exit=0 Ran <n> tests`.
  - Pattern run, used when a module list exceeds 60 (Plan 2 M10 rule): `bash C:/Users/Kadir/Desktop/<WT>/ai-dnd/scripts/engine_split/slot_gate.sh <FSLOT> <WT> <label> 3 3600 '^(<mod1>|<mod2>|...)$'`. Pass = `PAR_EXIT=0` and `failing_ids 0`. The runner puts `api.tests.gate_boot` first in every shard.
    - **Base names only.** `slot_gate.sh` greps the regex against the `ls test_*.py` base names of `api/tests` and of the `ai-dnd` root. A dotted entry (`api.tests.test_x`) matches nothing, silently, while root names still match, so a mixed list loses modules and can still print `PAR_EXIT=0`. Strip `api.tests.` from every entry and build the regex from base names. Leave out `gate_boot` (not `test_*`; the runner adds it). Before reading the result, check that the printed `modules=<n> api=<a> top=<t>` has `n` equal to the intended list size minus `gate_boot`; otherwise the run does not count (Plan 2 Ruling).
  - Full suite: `bash C:/Users/Kadir/Desktop/<WT>/ai-dnd/scripts/engine_split/slot_gate.sh <FSLOT> <WT> <label> 3 3000 '.'`. Full suites run only in Task 17 (TM3): four bases and two gate suites, one at a time. No browser tests.
  - `NEIGHBOURS` = `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys`. They are in every targeted run and never dropped.
  - `ENGINE_SET` = `api.tests.test_engine_parts_pilot api.tests.test_engine_routing api.tests.test_engine_surface api.tests.test_engine_patch_census api.tests.test_engine_size_budget api.tests.test_engine_hash_parts api.tests.test_engine_sources api.tests.test_engine_split_inventory`. It is in every Stage B run and every Stage A run that touches engine-split tools.
  - Bench: `slot.sh <FSLOT> <WT> test <label> 1800 api.tests.bench_engine_turn`. Read the `TURN_BENCH` line from `target.log` (each reading is the median of 5 sessions). Labels end `-off`: the TM0 limits are flag-off measures.
- **Gate wait (strict; Plan 2 Task 1 broke it once).** Before every `slot_gate.sh` call and every bench, the controller runs the `SLOTPY` script `run-gatewait.sh`, which holds `pgrep -af linux_guarded_launcher; echo "RC=$?"; awk '/MemAvailable/{print "AVAIL_MB=" int($2/1024)}' /proc/meminfo`.
  - Go only on `RC=1`. For `slot_gate.sh`, also `AVAIL_MB` ≥ 3500.
  - Otherwise poll every 5 min for at most 35 min, then ask Kadir.
  - The output goes in the ledger every time, also for small pattern runs.
- **Scripts that are not tests (`SLOTPY`).** After a `slot.sh ... test` call has synced the tree, run them with the slot's Python 3.13 outside the guard: `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- bash /mnt/c/Users/Kadir/Desktop/AI-DND-k2-bolme-t4n/.superpowers/sdd/2026-11-19-game-py-bolme-plan-3/run-<name>.sh`.
  - The `.sh` holds `cd /root/aidnd-env-<SLOT>/src/ai-dnd && /root/aidnd-env-<SLOT>/proj/.venv/bin/python <script> <args>; echo "RC=$?"`.
  - Always a script file, never `bash -c '...'` (D-351). Never Windows Python 3.14 for the mover or the checker (D-358).
  - The Stage B worktree has no `.superpowers/sdd` folder; both stages use the Stage A ledger dir.
- **Measurement store:** `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p3/`. Seconds, bench readings and RESULT lines are copied raw from the run (`proof.json`, `target.log`), never estimated or paraphrased (speed rule 4; D-368 lesson).
- **Red first.** Every new test is seen failing for the stated reason before the change. A guard green on a clean tree is shown red with a planted fault, then restored.
  - Restore rule (as Plan 2): copy the file to `<ledger dir>/pre-plant/` with its sha256; plant; run; copy back; `git add` if `slot.sh` staged it. Then check the sha256 and that `git diff HEAD --stat` equals the pre-plant one.
  - A broad checkout is allowed only in the exam task (16) and the rehearsal.
  - Every new test that starts a campaign or a session wraps it in `fixed_town(self, <seed>)` from `api/tests/town_seed.py`. Seeds `20261201` and up, one per test.
- **Old-behaviour tests** are rewritten only with equal strictness and get a row in `docs/agents/onay-listesi-20261115.md`, section 21 (`Test | Değişiklik | İşaret`; mark "gevşetme olabilir" when a boundary moves). Unmarked loosening, skipping or deleting stops the work.
- **Findings** go to `docs/agents/debt-register.md`, rows with exactly 8 `|`, ids `D-430..D-449`. Before each push, read the highest id on `origin/main` and on open branches (`git grep -o "D-[34][0-9][0-9]" <ref> -- docs/agents/debt-register.md`). Main held D-393 on 2026-11-19. If D-430 is taken, use the next free block and write a `Ruling`.
- **Ledger:** `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-t4n/.superpowers/sdd/2026-11-19-game-py-bolme-plan-3/progress.md` (local, not committed; Stage B appends; `run-*.sh` and `pre-plant/` live there too).
  - Decisions are written as `Ruling: <karar> — <neden> — <yanlışsa maliyeti>`.
  - Small findings are parked; a park has an owner by the end of Task 17.
  - Each gate records N1/N4/N5/N7 output, suite seconds and the bench.
- **Review tiers (by content, spec §5 decision 11).** Every review is independent: a separate reviewer on a `git archive <sha>` copy that reruns M7 itself.
  - "strong" = Opus, whole-branch scope, with money/save/Undo reading. The fable model is never used (owner rule 2026-11-14).
  - "normal" = Opus review for moves and net code; Sonnet implementer for small tool tasks.
  - Ruling: no T4 move is strong. Every moved name is outside `sensitive.json`, and no moved name can reach a money, death or save/Undo writer in any number of hops (`writer_scan.py`, a transitive call graph over the whole engine: `SUMMARY held=0 missing=0 clean=241`, appendix A). N8 sees only a function's own text, so the names that reach a writer through other functions are held for Plan 4 (strong): fix wave 1 `create_npc_from_ai` (→ `equipment_economy.give_person_purse`), `commit_location_change` (→ `economic_actions.cancel_prepared`), `advance_campaign_time` (→ `process_supply_days`, death state) with `generate_npc_id`, `_ensure_location_entities`; fix wave 2 `_commit_travel_action`, `_adventure_travel_reply`, `_promote_scene_referent`, `_handle_query`, `update_world_state_from_player`, `_settle_spoken_commitment`, `_fallback_for_action_result`, `_states_the_failed_check` (travel death and supply paths through `timed_gameplay`/`weapon_attack`, quest gold through `evaluate_quest_events` → `adventure.rewards.apply_plan`, NPC coin through `economic_actions.npc_gift`, the purse, Undo snapshots, `ensure_death_state`) with `_fallback_narration`, `_stands_by_their_words` (helpers whose callers are all held). Every move review runs M12 (`writer_scan.py` on its archive copy with its committed batch file) and needs `SUMMARY held=0 missing=0 clean=<lines in NAMES>`, exit 0. The scan follows a moved name through its `game.py` re-export into `game_parts`; a name defined nowhere prints `MISSING` and fails (fix wave 3: before it, a moved held name printed `MISSING` and the summary read `held=0 clean=0`, so the check passed on nothing). Where a money, save, death or Undo test patches or reads a moved name (appendix D), the move's review confirms that the test file is unchanged since `BASE_SHA` and green in M10, and the task names it in M10 (Plan 2 Task 14 precedent). If wrong: one stronger review than needed is skipped; the TM3 whole-branch review (strong) reads the same tests again; a writer the scan cannot see (getattr, callbacks in data) is the scan's named blind spot, read by the whole-branch review. Where a money, save, death or Undo test patches or reads a moved name (appendix D), the move's review confirms that the test file is unchanged since `BASE_SHA` and green in M10, and the task names it in M10 (Plan 2 Task 14 precedent). If wrong: one stronger review than needed is skipped; the TM3 whole-branch review (strong) reads the same tests again.
- **Speed rule 1 (overlapping review)** only in Stage A, only between tasks with disjoint file lists. The reviewer uses `FSLOT` (no full suite runs in Stage A).
  - Ruling: in Stage A, implementers do not edit `docs/agents/debt-register.md`; the controller writes each task's rows in its own commit after that task's review, so overlapping tasks keep disjoint file lists (Plan 2 had this conflict). If wrong: one extra small commit per task. Stage B runs strictly one task after another, review finished before the next move.
- **Tools.** Stdlib only in CI. Forbidden: `ast.unparse`, formatters, `ruff --fix`, `ruff format`, rope, libcst codegen, import-linter, desloppify. Moved source is edited in place only. `sensitivity.py --write` is never run. A name enters `sensitive.json` only by a hand edit under the strong review (Task 0 Step 4, Task 6) and never leaves it in Plan 3.
- **Centre rule (spec §4).** A part never calls another engine function or class bare; it writes `game.X`, also for a function of its own part (R9). A constant read by code in the same part stays bare. No part imports a sibling part or writes `from game import`. Only `game.py` imports `game_parts.*`; tests never do.
- **Never moved** (`move_block.NEVER_MOVED`, 18): `world_state, messages, RULE_ORDER, GameSession, _session, _bind_session_engine, create_session, _GameModule, _speech_debug_trail, DEFAULT_SAVE_PATH, start_terminal_game, _DEFAULT_SESSION, _ACTIVE_SESSION, _ENGINE_FUNCTIONS, _ENGINE_NAMESPACE, _CHARACTER_GLOBALS, _PART_MODULES, recent_dm_narrations`.
- **Key files** (`.env`, `apikeys*`, `*.pem`, `~/.aidnd-*-key`) are never read or printed. Old saves do not matter: no compatibility work.
- **Every implementer brief carries:**
  - `docs/agents/implementer-preamble.md`;
  - the graphify rule (`graphify query "<question>"` before the first grep or source read; raw files only for lines the graph or an earlier read located; `graphify update .` once at the end of the task);
  - "a move task changes nothing else";
  - "the prefix is added in place; source is never regenerated";
  - function and file names, never line numbers;
  - `game.py` is about 22 700 lines: never read it whole.
- **Stop and ask** only for: an irreversible or destructive action, a security-sensitive action, a side effect outside the worktree (push, merge, publish), a plan so broken every path is a guess. The spec adds one more: a speed limit exceeded (spec §7, "dur ve bildir"). Everything else: decide, write a `Ruling`, continue.
- **Play gate (spec decision 7, §12).** TM3 ends with Kadir playing at least 10 minutes. The ledger's last line is "oynayış bekliyor" until he has played. Plan 4 does not start before that.

## Move procedure (binding for Tasks 7-15; goes into every move brief word for word)

Definitions:
- `B` = batch name, `P` = part file.
- `NAMES` = `/mnt/c/Users/Kadir/Desktop/<WT>/ai-dnd/scripts/engine_split/batches/<B>.txt` (committed in Task 4).
- `WTROOT` = `/mnt/c/Users/Kadir/Desktop/<WT>/ai-dnd`.
- `STORE` = `/mnt/c/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p3`.

The mover and the checker run from the slot copy against `WTROOT`; other `SLOTPY` steps read the slot copy after a sync.

- **M1 Base.** `BASE_SHA` = the commit right before the move. `git archive <BASE_SHA> ai-dnd/game.py ai-dnd/game_parts | tar -x -C C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p3/base-<B>/`.
- **M2 Measure before cutting.** For every name in `NAMES`, check four things:
  - not in `NEVER_MOVED`;
  - not in `sensitive.json`;
  - still a top-level name of `game.py`;
  - in the file order of the batch file.
  
  For every constant, run the N8 patterns of `sensitivity.py` over its source text. A hit **and** a reader in `sensitive.json` → hold it.
  
  **`F_fon` hold:** only if `p3/F_fon.txt` is not empty (Global Constraints).
  
  Any surprise means hold that name and write a `Ruling`. Surprises are: a decorator, a non-constant default naming an engine name, an identity name, a module-level mutation, a top-level `if`/`try` around it (D-363). A hold edits the batch file in the same commit and adds a row to the ledger's held table.
- **M3 Red test.** Add the batch's tests (given in the task) to `api/tests/test_engine_parts_pilot.py`; run both flags with `ENGINE_SET` + `NEIGHBOURS` (labels `p3t<N>-<B>-red-off`, `p3t<N>-<B>-red-fon`); see the membership test fail because the names are not re-exported from `P` yet.
- **M4 Move with the CLI** (`SLOTPY`):

  ```
  move_block.py --game WTROOT/game.py --part WTROOT/game_parts/<P> --names-file <NAMES> --census WTROOT/api/tests/engine_split_locks/patch_census.json --report STORE/move-<B>.json
  ```

  Expected: `MOVED names=<n> ...`, `RC=0`.
  
  `REFUSED <reason>` (exit 2, files untouched): hold the named name, write a `Ruling`, run again.
- **M5 Part header by hand.**
  - A new part starts with `import game` (it has functions).
  - Then, for each module the moved code reads (the appendix lists the expected header per batch), copy the import statement **exactly as `game.py` spells it**.
  - Ruling (new in Plan 3): a multi-name `from X import (...)` keeps its form and name order but lists only the names the batch reads, and never a census target. R3 refuses a part that binds a patched name; `cr` would otherwise import `resolve_saving_throw`. If wrong: one import line differs in shape from `game.py`; no behaviour change.
  - Census `import`/`absent` targets get no header line; the mover writes `game.<x>`.
  - In-function imports move untouched.
  - `allowed_imports.json` stays byte-equal.
- **M6 Sync, then bookkeeping in the same commit.** Sync the slot by rerunning the M3 test (green now), both flags with `ENGINE_SET` + `NEIGHBOURS` (Plan 2 Task 9 Ruling). Then:
  - `size_budget.json`: `files["game.py"]` = the new real line count. A moved long function's key changes from `game.py::<name>` to `game_parts/<P>::<name>`, value unchanged (`test_long_functions_are_keyed_by_file_and_name`).
  - `surface.json`: regenerate in the slot (`SLOTPY surface.py --write WTROOT/api/tests/engine_split_locks/surface.json`).
  - If `P` is a new part with a re-exported function and this is its first batch: add `"game_parts.<p>"` to `_PART_MODULES` by hand, keeping the tuple sorted. M7 then needs one `--manual "game.py:new:<N>:_PART_MODULES value"` and its `base` twin.
  - Nothing else changes: an import of `game.py` whose users all left stays (ruff F401 is noted, not fixed).
- **M7 N5.**

  ```
  SLOTPY move_check.py --base-root STORE/base-<B>/ai-dnd --root WTROOT --moved-file <NAMES> --part <P> --tier normal [--manual ...]
  ```

  Expected: `CHANGED 0 names=<lines in NAMES>`, `RC=0`. Then `--comments-only` prints `COMMENTS base=<C> now=<C>`, where `<C>` is the count Task 0 measured on `P3BASE` (1 083 unless the flag-on job changed comments). Paste both in the ledger.
  
  A recheck of an older batch uses that batch's own move commit's parent as root. Since Task 1 the tool says `WRONG ROOT?` when it is not; never read a `CHANGED` from a wrong root as a finding.
  
  If `CHANGED` is above zero: never patch forward, never a broad checkout. Restore only what M4-M6 wrote:
  - `git checkout HEAD -- ai-dnd/game.py ai-dnd/api/tests/engine_split_locks/size_budget.json ai-dnd/api/tests/engine_split_locks/surface.json`;
  - an existing part: `git checkout HEAD -- ai-dnd/game_parts/<P>`;
  - a new part: `git rm -f -q --ignore-unmatch ai-dnd/game_parts/<P>`, and delete the file if it is still on disk.
  
  Then redo from M4.
- **M8 N1 and N3.** `SLOTPY surface.py --diff --old <golden at BASE_SHA> --new <new golden> --moved <function names of the batch>`: no output, `RC=0`. `SLOTPY routing_audit.py`: `clean`, `RC=0`.
- **M9 Outside-guard probe** (D-341). `SLOTPY outside_probe.py` on a slot copy whose `game.py` sha256 equals the worktree's. Last line: `PROBE ok parts=<sorted part modules>`, which must list `P`.
- **M10 Targeted runs, both flags.** Module list = `ENGINE_SET` + the output of `SLOTPY inventory.py --touching <NAMES>` + the task's named modules + `NEIGHBOURS`; the flag-on run adds `api.tests.gate_boot` first and `api.tests.test_engine_gate_boot`.
  - Up to 60 modules: `slot.sh` twice, labels `p3t<N>-<B>-off` and `p3t<N>-<B>-fon`.
  - Over 60: `slot_gate.sh` pattern runs with the same labels, each after the gate wait.
  - Pass: `RESULT exit=0` (or `PAR_EXIT=0`, `failing_ids 0`) in both. In the flag-on run, `test_the_fon_token_turns_the_flag_on_inside_the_child` is `ok`, not `skip` (Review Focus 2).
  - If `test_engine_patch_census` is red only because a moved target's `kind` changed: regenerate the lock and explain each changed target in the ledger. Any other census difference stops the task.
- **M10b Bench (once per task, after its last batch).** Gate wait, then two flag-off readings `p3t<N>bench1-off`, `p3t<N>bench2-off`.
  - A reading over its TM0 limit (23.13 ms reading 1, 23.25 ms reading 2) stops the plan, and Kadir is told (spec §7). No retake to pass.
  - The delta against Task 0's readings goes in the ledger (Review Focus 1).
- **M11 Commit** with the message the task gives. One batch = one commit. A tool fix found by a review is its own earlier commit (Step 0 of the next task).
- **M12 Writer scan (the reviewer, every batch).** `SLOTPY <M>/writer_scan.py <ARCH> <ARCH>/ai-dnd/scripts/engine_split/batches/<B>.txt`, where `<ARCH>` = the root of the `git archive <move sha>` copy and `<M>` = the plan's measure folder. The scan starts each name where `game.py`'s re-export points (`game_parts.<P>:<name>`).
  - Pass: `SUMMARY held=0 missing=0 clean=<lines in NAMES>`, exit 0. The count each task gives is the measured batch size; after an M2 hold it is the lines left in `NAMES`.
  - A `HELD` line fails the review: the name goes back to `game.py` for Plan 4 (`Ruling`, debt row). A `MISSING` line fails it too: the batch file names something defined nowhere (a typo or a lost re-export).

## Review Focus

These are failure modes the spec implies but none of its listed checks exercises. Each is pinned to a test or a gate step in the task named.

1. **Turn latency from `game.X` on hot paths.** 107 moved functions read `game._session()` through the Python-level `_GameModule.__getattribute__`, and bench reading 1 has 0.2 ms of headroom. Pinned by: Task 5 (four readings on the fully moved throwaway tree, stop before any real move), M10b in every move task, Task 17 Step 6.
2. **The game Kadir plays runs flag on.** A moved helper used only on the flag-on path must run in a flag-on test. Pinned by: every M10 flag-on run includes `test_the_fon_token_turns_the_flag_on_inside_the_child` (`ok` there), and the TM3 flag-on bases and gate suite (Task 17).
3. **The import-time game is built by a moved function.** `initialize_game` runs while `game.py` is still importing. Pinned by: `test_the_import_time_game_is_initialized_by_the_moved_function` (Task 15), M9 both import orders and `python game.py`, and Task 17 Step 7 with the `start_local.ps1` interpreter.
4. **Moved `session=` helpers still bind the given session** (15 names, appendix D). Pinned by: `test_<part>_session_helpers_use_the_given_session` (Tasks 7, 8, 9, 10, 12, 14), checked red in Task 16 Fault 8.
5. **Production rebinding reaches moved callers.** `trace_ai_pipeline.py` assigns `game.validate_intent`; one caller (`analyze_player_action`) moves to `intent` (`update_world_state_from_player` is held, fix wave 2). Pinned by: `test_a_rebound_validate_intent_reaches_a_moved_caller` (Task 9) and Task 16 Fault 4 (frozen alias, N4).

---

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `ai-dnd/scripts/engine_split/move_check.py` | D-376 false alarm and wrong-root warning; D-360 other parts and stale exemptions | 1 |
| `ai-dnd/scripts/engine_split/ledger_diff.py`, `ai-dnd/api/tests/engine_probe.py` | D-361 (1, 2, 4, 5), D-372 (outermost outcome of a repeated id) | 2 |
| `ai-dnd/api/tests/test_engine_gate_boot.py` | D-359 relative and dynamic engine imports | 2 |
| `ai-dnd/scripts/engine_split/routing_audit.py` | D-349 item M9: walrus target in a module-level generator (false R5; no T4 mover has one, measured) | 3 |
| `ai-dnd/scripts/engine_split/inventory.py`, `surface.py` | D-364 public `bound_names`, empty `--diff` line; D-366 two-step import chain | 4 |
| `ai-dnd/scripts/engine_split/batches/*.txt` | the 14 name lists (appendix C) | 4 |
| `ai-dnd/game_parts/character_rules.py` | + batch `cr` | 7 |
| `ai-dnd/game_parts/places.py` | batches `places-1`, `places-2` | 8 |
| `ai-dnd/game_parts/intent.py`; `schemas.py` | batches `intent-1`, `intent-2`; `schemas-options` | 9 |
| `ai-dnd/game_parts/dialogue.py` | batches `dialogue-1`, `dialogue-2` | 10 |
| `ai-dnd/game_parts/lore.py` | batch `lore` | 11 |
| `ai-dnd/game_parts/narration.py` | batch `narration` | 12 |
| `ai-dnd/game_parts/narration_safety.py` | batches `nsafety-1`, `nsafety-2`; frozen at arrival size (spec §11) | 13 |
| `ai-dnd/game_parts/living_world_turn.py` | batch `lwt` | 14 |
| `ai-dnd/game_parts/new_game.py` | batch `newgame` (`initialize_game`) | 15 |
| `ai-dnd/api/tests/test_engine_parts_pilot.py` | membership, behaviour, session and rebinding tests of every move | 7-15 |
| `ai-dnd/api/tests/test_talk_mode_writers.py` | file-set pin gains `game_parts/dialogue.py` (approval §21) | 10 |

Tests import the tooling the way `api/tests/test_engine_move_tool.py` does. Tool functions take paths as arguments so tests run on small fixtures in a temp dir.

**Batches (Ruling R1).** Region map, then misfit correction, then CAP 1 000 lines per batch. The method is in appendix A, the lists in appendix C.
- One task per spec row (T4.1-T4.9).
- A task's batches are steps, each with its own M1-M11 cycle and commit, and one review per task. This keeps review count at nine while each M7 diff stays under about 1 000 lines (the largest Plan 2 batch was 544).
- If wrong: a reviewer reads up to two commits at once; the whole-branch review rereads all.

Measurement wins over the appendix (Task 4 Step 3).

---

# Stage A — nets and rehearsal (worktree `AI-DND-k2-bolme-t4n`, PR 6). `ai-dnd/game.py` and `ai-dnd/game_parts/` do not change in this stage.

### Task 0: Open the stage

**Review tier:** none (no code).

- [ ] **Step 1: One batched message to Kadir** (information, nothing waits on it except (a) before Task 17):
  - (0) The freeze starts now and holds until PR 7 merges: no other job edits `ai-dnd/game.py` or `ai-dnd/game_parts/` (for example the D-377/D-381 fixes wait).
  - (a) A time window for TM3: six full suites, one after another, about 3 h of machine time. Ruling: the N4/N7 bases are taken at TM3, on the Stage A tip merged with the same `origin/main` commit as the gate tree, in a detached worktree. This keeps "full suites only at TM3" and still gives TM3 a like-for-like base. If wrong: a pre-existing flag-on red shows only at TM3; it is traced and excluded by the `F_fon` rule.
  - (b) D-387/D-393: the fixed-town slice proposed "before Plan 3 bases". Plan 3 does not wait: two bases per flag measure the noise and N4/N7 subtract it. If Kadir wants the slice first, it must merge before Task 17 Step 3.
  - (c) News: seven new parts; a rehearsal measures the turn cost before any real move; a speed stop is possible (Review Focus 1).
- [ ] **Step 2: Precondition.**
  - `git fetch origin`; `git merge-base --is-ancestor <x> origin/main` for `b1150df8`, `36daaa1b`, `origin/task/fon-a` and `origin/task/fon-b` (a squash merge or a fon-b outside fon-a would hide from a `git log --merges | grep fon`; if a squash leaves the branch tips non-ancestors, find the squash commit by its PR number and write that `Ruling`). Write the shas in the ledger.
  - Read the D-369, D-370, D-371 rows on `origin/main`.
  - Read the flag-on job's final gate lines: `F_fon` empty or the remaining ids. Write `p3/F_fon.txt` (empty file if none).
  - D-380 item 4: if `F_fon` is empty, close it ("no `F_fon` checks left"). Otherwise move the alias-id check of `run-B9-ffon.py` into `ai-dnd/scripts/engine_split/` in Task 2 and say so.
- [ ] **Step 3: Worktree and ledger.**
  - `git worktree add ../AI-DND-k2-bolme-t4n -b task/game-py-bolme-t4-nets origin/main`; create the ledger.
  - Bring the plan: `git checkout task/game-py-bolme-plan3 -- docs/superpowers/plans/2026-11-19-game-py-bolme-plan-3.md docs/superpowers/plans/2026-11-19-game-py-bolme-plan-3-appendix.md docs/superpowers/plans/2026-11-19-game-py-bolme-plan-3-measure`.
  - Add one line to `docs/design/INDEX.md`. Write Kadir's answers when they come.
- [ ] **Step 4: Locks on `P3BASE`.**
  - Targeted runs `p3t0-base-off` and `p3t0-base-fon`, modules `ENGINE_SET` + `NEIGHBOURS` (flag on: plus `gate_boot` and `test_engine_gate_boot`). Expected: `RESULT exit=0` twice. Record the seconds.
  - Then, with `SLOTPY` into `STORE`:
    - `surface.py --write STORE/surface-p3base.json`;
    - `patch_census.py --write --lock STORE/census-p3base.json --report STORE/census-p3base.md`;
    - `wc -l game.py`;
    - `move_check.py --comments-only` (records `<C>`);
    - a script that calls `sensitivity.classify` on `game.py` and every part and prints the set difference against `sensitive.json` names.
  - Expected: `cmp` equal with the committed locks, `wc -l` equal to `size_budget.json` `files["game.py"]`, and the classify difference (minus the names in `sensitive.json["removed"]`) only `game_parts/terminal.py: run ['save']` (moved in T1 under the strong review; measured 2026-11-19): record it, do not add it.
  - A lock difference means main itself is out of step: trace it to its commit, write a debt row, regenerate the lock in Task 4's commit, and say so in the ledger.
  - A name the classifier flags that `sensitive.json` lacks: add it by hand in this task's commit (it never moves in Plan 3), with a `Ruling` naming the pattern hit. The Task 6 strong review reads that edit. Never remove a name.
- [ ] **Step 5: Bench base.** Gate wait. Two readings `p3t0bench1-off`, `p3t0bench2-off`, one `p3t0bench-fon` (`gate_boot` first; recorded, not a limit). Write all three and the headroom to 23.13 / 23.25 ms.
- [ ] **Step 6: Debt bookkeeping** (rows keep 8 `|`):
  - D-368 closed: "Plan 3 copies raw RESULT/PAR_EXIT lines and runs the strict gate wait before every `slot_gate.sh` and bench. The historic Stage A report items need no action."
  - D-379: `Ruling: the mover keeps leaving blank lines; one layout commit in Plan 6 — changing the mover now changes every later M7 base and comment count mid-split — if wrong: game.py reads with more blank runs until Plan 6`. Trigger text → "Plan 6 kapanış düzeni".
  - D-351 open item (`import game` unused in `text_rules_a.py`): Plan 3 does not touch `text_rules_a`. Trigger → "Plan 6".
  - D-380 item 3 (subtest keyword `raw`): trigger → "Plan 6" (a rename, no behaviour).
  - D-380 item 7 (autosave log noise): trigger → "sonraki test altyapısı işi".
- [ ] **Step 7: Commit** `game.py split plan 3: plan, appendix and measure scripts; debt bookkeeping (D-368, D-379, D-351, D-380)`.

### Task 1: `move_check` fixes (D-376, D-360)

**Review tier:** normal (Sonnet implementer, Opus review). Money/save/Undo: no.

**Files:**
- Modify: `ai-dnd/scripts/engine_split/move_check.py`
- Test: `ai-dnd/api/tests/test_engine_move_check.py` (the module that covers `move_check`; `test_engine_move_tool.py` covers the mover)
- Approval row §21: N5 matching becomes span-anchored instead of a whole-file `SequenceMatcher`: "gevşetme olabilir" unless the review shows equal strictness (every Plan 2 fixture still fails as before).

**Interfaces — Consumes:** `move_check.check_move`, `_game_py_findings`, `_import_group_problem` (read first; reuse, do not redesign).

**Interfaces — Produces:**
- No false alarm for a held block followed by a moved block with an identical closing line. The base `game.py` minus the moved blocks' exact line spans must equal the new `game.py` minus the re-export lines, line for line. Matching is anchored on the spans, not on a whole-file `SequenceMatcher`.
- **Wrong-root warning.** The deleted-outside-moved-blocks lines can all be covered by whole top-level blocks of names that the new tree re-exports from parts. In that case the tool prints `WRONG ROOT? <n> base lines belong to <k> names moved by later batches; use the parent of this batch's move commit` and exits 2, with no `CHANGED` list.
- **D-360.**
  - Every part file other than `--part` whose bytes differ from the base is a finding, `CHANGED other part <file> differs from base`, unless a `--manual` names it.
  - A `--manual` exemption on a valid import line inside a failing import group is reported as stale.

- [ ] **Step 1: Write the failing tests** (fixtures in a temp dir):

```python
def test_a_held_block_before_a_moved_block_with_the_same_last_line_is_no_change(self):   # D-376: two dict blocks ending "}", first held, second moved
def test_an_old_batch_checked_against_an_older_root_says_wrong_root(self):               # base has A and B; batch moved A; later B moved too
def test_a_hand_edit_in_another_part_is_a_finding(self):                                  # D-360 (1)
def test_a_stale_exemption_in_a_failing_import_group_is_reported(self):                   # D-360 (2)
```

- [ ] **Step 2:** Run the test module + `ENGINE_SET` + `NEIGHBOURS`, labels `p3t1-red-off`, `p3t1-red-fon`. Expected: FAIL on the four new tests.
- [ ] **Step 3:** Implement. Run again (`p3t1-off`, `p3t1-fon`): `RESULT exit=0` twice.
- [ ] **Step 4: Live proofs.**
  - (a) Recheck the six Plan 2 batches with each move commit's parent as root (the commits are in Plan 2's ledger): `CHANGED 0` each.
  - (b) Recheck `text-a1` against `b1150df8`'s tree: `WRONG ROOT?`, exit 2.
  - (c) On a throwaway copy of `P3BASE`, move `_EXPERIMENTAL_NPC_SPEECH_OPTIONS` alone with the CLI and check it: `CHANGED 0`. This is the D-376 case; the real move is Task 9.
  - Record all output.
- [ ] **Step 5:** D-376 and D-360 rows: closed with the test names (D-376 keeps "live proof: Task 9").
- [ ] **Step 6: Commit** `game.py split plan 3: move_check without the identical-line false alarm, with a wrong-root warning and other-part checks (D-376, D-360)`.

### Task 2: N4 ledger fixes and engine-import guard (D-361, D-372, D-359)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no.

**Files:**
- Modify: `ai-dnd/scripts/engine_split/ledger_diff.py`, `ai-dnd/api/tests/engine_probe.py`, `ai-dnd/api/tests/test_engine_gate_boot.py`
- Test: `ai-dnd/api/tests/test_engine_probe_tools.py`, `ai-dnd/api/tests/test_engine_gate_boot.py`

**Interfaces — Produces:**
- `engine_probe` outcome records carry `"depth"`: the stack depth when the run started, 0 = outermost.
- `ledger_diff._outcomes` takes, per id, the outcome of its depth-0 records (worst of those). Ids with no depth-0 record keep today's worst-of rule (D-372: the 42 `test_contract_parity` re-runs no longer turn an outer `ok` into `fail`).
- `--collect` prints `MIXED TREE` and exits 1 when the shards of one run do not share one `total_digest_sha256` (D-361 item 2).
- `--diff` prints `SUBCRASH <n>`: ids with broken subtests in a base that fail or error whole in new without any subtest record. Exit 1 when above 0 (D-361 item 4).
- `test_engine_gate_boot._engine_import` also sees `from . import game`, `importlib.import_module("game")` and `__import__("game")` (D-359). Approval row §21: "`_engine_import` genişledi; iddia eklendi, gevşetme değil".
- If Task 0 Step 2 left D-380 item 4 open (`F_fon` not empty): the alias-id check moved from `run-B9-ffon.py` gets its own red-first test in `test_engine_probe_tools.py`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_lost_tests_honours_noise_keys(self):                   # D-361 (1): red against a planted lost_tests that ignores noise_keys (pre-plant rule), then green
def test_a_test_missing_in_new_is_not_ok(self):                 # D-361 (5): lost_tests({"a": "ok"}, {}, set()) == ["a"], named as its own pin
def test_shards_of_one_run_share_one_tree(self):                # D-361 (2): two fixture shards with different digests -> MIXED TREE, exit 1
def test_a_test_that_crashes_before_its_subtests_is_subcrash(self):   # D-361 (4)
def test_an_outer_ok_wins_over_inner_reruns_of_the_same_id(self):     # D-372: records depth 1 fail, depth 0 ok -> "ok"
def test_the_record_carries_its_depth(self):                     # tiny TestCase run inside a TestCase: inner depth 1, outer depth 0
def test_relative_and_dynamic_engine_imports_are_seen(self):     # D-359: three fixture sources -> each flagged
```

- [ ] **Step 2:** Run `api.tests.test_engine_probe_tools api.tests.test_engine_gate_boot` + `ENGINE_SET` + `NEIGHBOURS` (`p3t2-red-off`, `p3t2-red-fon`): FAIL on the new tests. Implement. Run again: `RESULT exit=0` twice.
- [ ] **Step 3: Smoke in the child.** Targeted run `p3t2-smoke-n4-off` with modules `api.tests.gate_boot api.tests.test_engine_parts_pilot` + `NEIGHBOURS`, then `SLOTPY ledger_diff.py --collect`. Every outcome record has `depth`; no `MIXED TREE`.
- [ ] **Step 4:** Rows: D-361 closed (items 1, 2, 4, 5 with test names; item 3 was closed in Plan 2). D-372 closed. D-359: `_engine_import` part closed. Write this `Ruling` into the row: `slot.sh labels stay unchecked — slot.sh is shared with another session and is not edited — the controller writes labels from the fixed pattern and the ledger lists each — if wrong: one run with a mixed flag, visible in its proof.json`. Trigger → "slot.sh'ye dokunan ilk iş".
- [ ] **Step 5: Commit** `game.py split plan 3: N4 outcomes per outermost run, mixed-tree and subcrash checks, engine-import guard sees dynamic imports (D-361, D-372, D-359)`.

### Task 3: N3 binds a module-level walrus target in a generator (D-349 item M9)

**Review tier:** normal (Sonnet implementer, Opus review). Money/save/Undo: no.

**Why (measured 2026-11-19 in the fix wave, `<M>/walrus_probe.py`, `<M>` = the plan's measure folder, the same result on Windows Python 3.14.2 and slot 2's Python 3.13.16):** on today's `routing_audit.audit`:
- a walrus inside a generator or a list comprehension **inside a function** gives no finding. `_narration_safety_decision` (batch `nsafety-2`) has this shape, so `nsafety-2` is not blocked;
- a walrus inside a **module-level generator expression** gives `R5 game_parts/p.py:3: p is not bound in this part, its imports or builtins`: a false finding, and `identity_allowlist.json` cannot exempt R5. A module-level list comprehension gives none (3.12+ inlines it). This is the real M9 bug;
- no top-level statement of `game.py` holds a walrus outside a function (`<M>/money_scan.py`: `GAMEPY_MODULE_LEVEL_WALRUS_LINES []`), so no T4 mover hits it. The fix is for later plans and for the net's honesty, not a T4 blocker.

**Files:**
- Modify: `ai-dnd/scripts/engine_split/routing_audit.py` (`_Walker._comprehension`)
- Test: `ai-dnd/api/tests/test_engine_routing.py`

**Interfaces — Produces:** a name bound by `:=` inside a comprehension or generator counts as bound in the scope that contains it (PEP 572): the enclosing function, or the part's module scope when there is none. Reads of it are neither R5 nor R7.

- [ ] **Step 1: Tests** (both with `run_audit(self.tree(src))`, the full audit minus R8):

```python
def test_a_walrus_inside_a_generator_binds_the_enclosing_function(self):   # guard: green today (measured)
    src = 'import game\n\n\ndef f(text):\n    return min((p for m in ".!?" if (p := text.find(m)) >= 0), default=0)\n'
    self.assertEqual(self.run_audit(self.tree(src)), [])

def test_a_module_level_walrus_inside_a_generator_binds_the_part(self):    # red today: R5 "p is not bound" (measured)
    src = 'import game\n\nFIRST = min((p for m in ".!?" if (p := "a.b".find(m)) >= 0), default=0)\n'
    self.assertEqual(self.run_audit(self.tree(src)), [])
```

  Run `api.tests.test_engine_routing` + `ENGINE_SET` + `NEIGHBOURS` (`p3t3-red-off`, `p3t3-red-fon`): the guard passes, the module-level test fails with the R5 line above. Paste the red line. If the slot run shows the guard red or the module test green, the measurement above is wrong: stop the task, write the line and a `Ruling`.
- [ ] **Step 2:** Implement in `_comprehension`: bind each `NamedExpr` target of the comprehension in the containing scope's bindings before walking it (red-first; no other rule changes). Run again (`p3t3-off`, `p3t3-fon`): `RESULT exit=0` twice. Record `routing_audit.py` time (D-349 tracks it: 1.8-1.9 s).
- [ ] **Step 3: D-349 row.** M9 item closed with both test names and the measured line "hiçbir T4 adının modül düzeyinde walrus'u yok (ölçüldü)". Carry-forward line, written into the row: "Plan 3 ölçtü: hiçbir T4 adı şunlara dokunmuyor: `builtins.eval/exec`, `__builtins__.open`, iki adımlı zincir, `getattr(<modül>, "uuid4")`, atamayla bağlanan işlev (R9), R8 durağan boşluk, eksik `__init__.py` (R13), başka modülde içe aktarma anı `game.X`; kimlik testi ile `narrative_director` (üç ad hassas, taşınmıyor)". Trigger → "Plan 4 Görev 0".
- [ ] **Step 4: Commit** `game.py split plan 3: routing audit binds a module-level generator walrus in the part (D-349 M9)`.

### Task 4: Measure again, write the batch files, small tool debts (D-364, D-366)

**Review tier:** normal (Sonnet implementer, Opus review: the review checks the batch lists against measurement). Money/save/Undo: no.

**Files:**
- Create: `ai-dnd/scripts/engine_split/batches/{cr,places-1,places-2,intent-1,intent-2,schemas-options,dialogue-1,dialogue-2,lore,narration,nsafety-1,nsafety-2,lwt,newgame}.txt`
- Modify: `ai-dnd/scripts/engine_split/inventory.py`, `ai-dnd/scripts/engine_split/surface.py`, `ai-dnd/api/tests/test_engine_surface.py`, `ai-dnd/api/tests/test_engine_split_inventory.py`
- Regenerate: `docs/engine-split/inventory.json`, `docs/engine-split/patch-census.md`; any lock Task 0 Step 4 found out of step

**Interfaces — Produces:**
- `inventory.bound_names(node: ast.stmt) -> tuple[str, list[str]]`: the public name of today's `_bound`, same signature (its callers use the kind) (D-364). Callers are updated; `_bound` is removed (only its own rename makes it unused).
- `inventory.touching_tests(root, names)` also lists a test module that imports a module which reads `game.<name>` at import time (one step; D-366).
- `surface.py --diff` prints nothing when there is no finding (D-364).
- `test_engine_surface.test_t4_batches_are_movable`: the Plan 2 rules of `test_t3_batches_are_movable` over the 14 T4 batch files, written once as a helper both tests call. The `first_cut` clause gets the comment "unreachable through import order; kept as a guard" (D-364 Ruling kept). Approval row §21: "`test_t3_batches_are_movable` ortak yardımcıya taşındı; aynı kurallar, eşit sıkılık".

- [ ] **Step 1: Write the failing tests:** `test_bound_names_is_public`, `test_touching_tests_follows_one_import_step` (fixture: `a.py` with `T = game.X`, `test_b.py` imports `a`), `test_surface_diff_is_silent_when_clean`, `test_t4_batches_are_movable` (red: no batch files).
- [ ] **Step 2: Measure on `P3BASE` with the slot Python.** Write three `SLOTPY` scripts against `WTROOT` (appendix A commands, outputs to `STORE`). Plus one script that reruns `t4_checks.py` with the map. Record the module summary, the misfit list and the batch table.
- [ ] **Step 3: Compare with the appendix. Measurement wins.**
  - Equal names and lines within ±5 % per batch: write "appendix holds".
  - A changed line count (the flag-on job's edits): take the measured one.
  - A name in another module than the appendix says: `Ruling` with the measured callers.
  - A new top-level name in a T4 region: it follows the map. If `sensitivity.classify` flags it, it stays (Task 0 Step 4).
  - A batch over 1 000 lines: re-cut with `batches.py`; the task numbers stay.
  - A name inside a top-level `if`/`try` (D-363): hold it, `Ruling`.
  - `_empty_lore_authority_context` goes into `lore.txt` only if `p3/F_fon.txt` is empty.
  - The 15 fix-wave holds stay held: `overrides-extra.json` maps twelve of them to `held_plan4` (fix wave 1: `create_npc_from_ai`, `commit_location_change`, `advance_campaign_time`; fix wave 2: `_commit_travel_action`, `_adventure_travel_reply`, `_promote_scene_referent`, `_handle_query`, `update_world_state_from_player`, `_settle_spoken_commitment`, `_fallback_for_action_result`, `_states_the_failed_check`, `_stands_by_their_words`), and the misfit rule adds `generate_npc_id`, `_ensure_location_entities`, `_fallback_narration`. The measured batches leave all 15 out (appendix A).
  - **Transitive money/death/save writer scan (N8 blind spot, D-355 class; controller Ruling 2026-11-19: any number of hops).** `SLOTPY <M>/writer_scan.py WTROOT/.. <OUT>/batches.json` (`<M>` = the plan's measure folder). Method: one call graph over every engine module under `ai-dnd/` (tests, scripts, `legacy_debug`, docs left out), edges from names, module attributes (module-level and in-function imports, `game.X`), `self`/`cls` methods, `session.X(...)` through `GameSession.__getattr__` to the `game.py` function, and a by-name fallback for other called `obj.meth(...)` (meth not a builtin container method, defined in at most three classes); a *writer* stores into or mutates a money key (currency, purse, coin, ledger, offer records), a player death key (`death_state`, `dead`, death saves, `condition_death`) or save/Undo state (N8 save/snapshot names, file writes, SQL writes); log writers are not save state; a breadth-first search from every batch name prints `HELD <batch> <name> <writer kinds> hops=<n> <path>`. Expected after the holds: `SUMMARY held=0 missing=0 clean=241` (measured 2026-11-19 on `b1150df8`, Windows 3.14; before the fix-wave 2 holds it printed `held=8`, appendix A). Any `HELD` line: hold that name, apply the misfit rule to helpers whose callers are then all held, rerun `module_map.py`, `batches.py` and the scan until `held=0 missing=0`, `Ruling` per name. `<M>/money_scan.py` still runs for the module-level walrus line (Task 3) and lists direct calls into `equipment_economy`/`economic_actions`/`bold_acts`; measured after the holds: `update_inventory_from_player` (`containers`, `legacy_sword_move`: a sword move, no coin), `_stealth_skill` (`bold_acts._door_out`, read), `known_player_action_narration`, `resolve_python_world_action` (`labels`, read); `writer_scan.py` confirms none of them reaches a writer. Write one debt row (next free `D-43x`) "N8 dolaylı para/ölüm/kayıt yazıcılarını görmüyor (D-355 sınıfı); Plan 3 geçişli taramayla 15 adı tuttu (`writer_scan.py`), taramayı Plan 4 Görev 0 D-355 ile kapatır; kör noktalar: getattr/dize, veride saklı geri çağrı, yaygın adlı yöntem", trigger "Plan 4 Görev 0", and link it from the D-355 row.
  - Under Python 3.13 `symtable` has no annotation scopes. A reads-list difference against the 3.14 prototype is expected; check that it changes no batch.
- [ ] **Step 4:** Write the 14 batch files, one name per line, in `game.py` order. Rerun the scan with the 14 files in place of `batches.json` (`SLOTPY <M>/writer_scan.py WTROOT/.. WTROOT/scripts/engine_split/batches/<B>.txt ...`, all 14): `SUMMARY held=0 missing=0 clean=<lines in the 14 files>`, 242 as measured (241 + `_EXPERIMENTAL_NPC_SPEECH_OPTIONS`, clean), exit 0. Implement the three tool changes. Regenerate `inventory.json` and `patch-census.md` (`SLOTPY patch_census.py --write --lock WTROOT/api/tests/engine_split_locks/patch_census.json --report WTROOT/../docs/engine-split/patch-census.md`). Run the four test modules + `ENGINE_SET` + `NEIGHBOURS` (`p3t4-off`, `p3t4-fon`): `RESULT exit=0` twice.
- [ ] **Step 5:** Rows D-364, D-366 closed with test names.
- [ ] **Step 6: Commit** `game.py split plan 3: T4 batch files from a fresh measurement, public bound_names, one-step import chains in touching_tests (D-364, D-366)`.

### Task 5: Rehearsal — the whole T4 move on a throwaway branch (refusals, imports, turn cost)

**Review tier:** none (Opus runner, no review; nothing reaches a plan branch). Money/save/Undo: no.

**Files:** none committed to a plan branch. Worktree `AI-DND-k2-bolme-t4p`, branch `tmp/game-py-bolme-t4-prova` from the Stage A tip. Local commits there are allowed (one per batch, for traceability). Never pushed, not deleted.

- [ ] **Step 1: Move everything.** First sync slot `SLOT` from `t4p` with one `slot.sh <SLOT> AI-DND-k2-bolme-t4p test p3t5-presync-off 1800 <NEIGHBOURS>` (the mover runs from the slot copy). Then, for the 14 batches in table order (appendix C): M4, M5 (headers from appendix C with the M5 Ruling), and the `_PART_MODULES` edit for each new part. No membership tests, no M6 bookkeeping. Commit locally.
  - Every `REFUSED` name: write it down, hold it, run again.
  - Every header gap found later: write it down.
- [ ] **Step 2: Static and outside checks.** Sync with one `slot.sh <SLOT> AI-DND-k2-bolme-t4p test p3t5-sync-off 1800 api.tests.test_engine_routing <NEIGHBOURS>`. Its result is information: the locks are stale by design. Then:
  - `SLOTPY routing_audit.py`: expected `clean`; every finding goes in the ledger with its batch;
  - `SLOTPY outside_probe.py`: `PROBE ok parts=` with all parts;
  - targeted runs of `test_sessions test_startup` + `NEIGHBOURS`, both flags.
- [ ] **Step 3: Turn cost.** Gate wait before each reading. Four readings `p3t5bench{1..4}-off` on this tree.
  - Record the mean, the max, and the delta to Task 0's readings.
  - **Stop rule (spec §7).** Stop if the mean is above 23.13 ms, or any reading is above 23.25 ms, or the mean delta to Task 0 is above the TM0 headroom Task 0 measured. Then do not start Stage B.
  - Before reporting, measure the one alternative on the same tree, as the same four readings: `_GameModule` without a Python-level `__getattribute__`, with class-level properties (getter and setter) for the names in `_CHARACTER_GLOBALS` mapping to `_DEFAULT_SESSION.character`.
  - Tell Kadir both numbers. The alternative touches session core (`_GameModule` is NEVER_MOVED): if he picks it, it becomes its own strong-tier task before Task 7, red-first. Its test: every character name read and written through the module still maps to the default session, also after `create_session`.
- [ ] **Step 4: Feed back into Stage A.**
  - Every refusal or audit finding becomes a hold in the batch file, a `Ruling`, and a commit on `task/game-py-bolme-t4-nets` (`game.py split plan 3: holds found by the rehearsal`).
  - A tool fault becomes a red-first fix in the owning task's files.
  - The ledger gets the line "prova: <n> red, <m> tutuldu, tur <mean> ms".
- [ ] **Step 5:** Back on the Stage A worktree: `git status` clean.

### Task 6: Gate G4a — Stage A review, PR 6

**Review tier:** strong (whole-branch review on Opus). Money/save/Undo: reads any `sensitive.json` edit of Task 0.

- [ ] **Step 1:** `git fetch origin`. If `origin/main` moved, merge it, then rerun Tasks 1-4's test modules + `ENGINE_SET` + `NEIGHBOURS` (both flags). If it changed `game.py`, repeat Task 4 Steps 2-4 and Task 5 Step 3. `git diff P3BASE..HEAD -- ai-dnd/game.py ai-dnd/game_parts` is empty.
- [ ] **Step 2: Whole-branch review** of `$(git merge-base origin/main HEAD)..HEAD`. One fix wave, red-first (Opus); scoped re-review (Opus). No second wave: remaining minors become debt rows.
- [ ] **Step 3: Checks without a suite.**
  - `SLOTPY outside_probe.py` → `PROBE ok` (D-341).
  - `python test_regression.py` as a `SLOTPY` script → `Results: 30 passed, 0 failed out of 30` (D-342).
  - `routing_audit.py` → `clean`.
  - ruff once (`uvx --from ruff==0.17.5 ruff check --select F821,F401,F811 --no-fix` over `game.py game_parts scripts/engine_split`); output in the ledger. F821 above 0 is looked at now; the rest is noted (D-380 item 5).
- [ ] **Step 4:** Recheck the free debt ids. Ask Kadir: push + PR 6. The PR text holds the rehearsal numbers and the debt rows closed. After the push: the CI rules of Global Constraints. Stage B starts without waiting for the push or the merge. Ledger line "G4a geçti".

---

# Stage B — T4 moves (worktree `AI-DND-k2-bolme-t4`, branch `task/game-py-bolme-t4` from the Stage A tip, PR 7). Each task is a pure move: the Move procedure applies in full; each batch is one M1-M11 cycle.

### Task 7: `character_rules.py` + batch `cr` — 19 names, about 427 lines (spec T4.1)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no money code moves. The `test_action_economy*` modules patch `roll_attack`/`roll_damage`; they cover combat action economy, not money. Save/death tests patch moved names too (appendix D, measured in the fix wave): `test_persistence_idempotency` (`roll_attack`, `roll_damage`), `test_death_system` and `test_dilim4a_death_audit` (`roll_damage`), `test_roadmap_k07_condition_persistence` (`roll_attack`). The reviewer reads those patch sites and confirms each file is unchanged since `BASE_SHA` and green in M10 in both flags. M12: `SUMMARY held=0 missing=0 clean=19`.

**Files:**
- Modify: `ai-dnd/game_parts/character_rules.py`, `ai-dnd/game.py`, `surface.json`, `size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

**Interfaces — Consumes:** `engine_sources.batch_names("cr")`, `routing_audit.re_exports(ROOT)`, `town_seed.fixed_town`.

**Interfaces — Produces:** `game.<name>` for the 19 names, each re-exported from `game_parts.character_rules`. `_PART_MODULES` is unchanged (the part is already listed).

**Batch:** header per appendix C with the M5 Ruling. It becomes `from api.core_resolution import (` / `    resolve_skill_check,` / `)`, then `import copy`, `import timed_gameplay`, `import weapon_attack`. `roll_attack` and the `roll_initiative*` names call `roll_d20` of the same part: the mover writes `game.roll_d20` (R9). Census targets moved: `roll_attack` (131 sites), `roll_damage` (65), `roll_initiative` (59), `roll_initiative_player` (55), `roll_initiative_npc` (6).

- [ ] **Step 1: Write the tests** (M3):

```python
CR = tuple(batch_names("cr"))
def test_cr_lives_in_the_part(self):                                     # red before the move
    self.assertEqual(set(CR) - set(routing_audit.re_exports(ROOT)["character_rules"]), set())
def test_a_patched_roll_d20_reaches_a_moved_roll_attack(self):           # the new path: part -> game.roll_d20
    # patch.object(game, "roll_d20", return_value=20); game.roll_attack() takes no arguments: assert it returns 20
    # and the patched roll_d20 was called once
def test_character_rules_session_helpers_use_the_given_session(self):    # Review Focus 4
    # for roll_stat and initialize_species_trait_state: with fixed_town(self, 20261201): s = game.create_session(seed=11);
    # record every value game._session() returns during game.<name>(..., session=s) (patch.object with a side_effect that calls
    # the real one and appends); assert the list is not empty and every entry is s. A name that never reads game._session():
    # assert instead that the call changes s.character / s.world_state and not game._DEFAULT_SESSION's (measure which, write it)
def test_cr_helpers_answer_as_before(self):
    # get_modifier(8/10/15/20), calculate_hp and calculate_ac on one fixed character: values captured on BASE_SHA, pinned as literals
```

- [ ] **Step 2:** Run (FAIL on membership only). M4-M9.
- [ ] **Step 3:** M10 (114 touching modules: pattern runs `p3t7-cr-off`, `p3t7-cr-fon`) with the named modules `api.tests.test_action_economy api.tests.test_action_economy_reactions api.tests.test_action_economy_end_turn api.tests.test_persistence_idempotency api.tests.test_death_system api.tests.test_dilim4a_death_audit api.tests.test_roadmap_k07_condition_persistence` (base names in the pattern regex). M10b.
- [ ] **Step 4: Commit** `game.py split T4.1: character, skill and dice helpers live in game_parts/character_rules.py`.

### Task 8: `places.py` — batches `places-1` (43 names, about 991 lines) and `places-2` (15, about 222) (spec T4.2)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no money code moves. The names of this topic that reach a money, death or save/Undo writer stay in `game.py` for Plan 4 (fix waves 1 and 2, measured with `writer_scan.py`): `create_npc_from_ai` (→ `equipment_economy.give_person_purse`, which writes `world["currency"][npc_id]`), `commit_location_change` (→ `economic_actions.cancel_prepared`), `_commit_travel_action` (→ `commit_location_change`, and → `timed_gameplay.start_travel` → `advance_walking` → `weapon_attack.add_exhaustion` → `_finalize_player_death`, and → `process_supply_days` → `consume_daily_supplies`), `_adventure_travel_reply` (the same travel paths, → `perform_skill_check` snapshots, and `session.evaluate_quest_events` → `adventure.rewards.apply_plan`, quest gold), `_promote_scene_referent` (→ `create_npc_from_ai`), with the helpers `generate_npc_id`, `_ensure_location_entities`. No moved name references any of the 15 held names or `execute_intent` (measured on `0e5257e7` over all 241 batch names: names, attributes and strings; none). M12 for each batch: `SUMMARY held=0 missing=0 clean=43` (`places-1`), `clean=15` (`places-2`). The reviewer reads `update_inventory_from_player`'s call into `equipment_economy.legacy_sword_move` (a sword move, no coin) and confirms no coin, wallet, ledger, death or save write; if one exists: hold it, `Ruling`, debt row, Plan 4. `test_d207_written_purse` guards the purse that `create_npc_from_ai` gives; `test_economic_room` patches the held `commit_location_change`; `test_persistence_idempotency` patches the held `_promote_scene_referent`. No moved name calls those held names; the three files stay named in M10 only as files that must stay unchanged: the reviewer confirms they are unchanged since `BASE_SHA` and green in M10.

**Files:**
- Create: `ai-dnd/game_parts/places.py`
- Modify: `ai-dnd/game.py` (`_PART_MODULES` gains `"game_parts.places"` in `places-1`), `surface.json`, `size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

**Batch:** headers per appendix C. Plan 2 held names that move here: `_venue_door_id`, `_mark_lock_seen`, `_lock_known_to_player`, `_local_place_access`, `_a_walk`, `_is_canonical_city_id`. `_adventure_travel_reply` (Plan 2 held it for Plan 3) is held again, for Plan 4 (fix wave 2). Non-constant default `_has_unregistered_person_name(..., ...=())` names no engine name: it moves.

- [ ] **Step 1: Tests for `places-1`:**
  - `test_places_1_lives_in_the_part` (red).
  - `test_places_session_helpers_use_the_given_session` for `resolve_location_reference`, `update_inventory_from_player`; `_walked_there` is added in `places-2`. Same contract as Task 7, seed `20261202`.
  - `test_places_helpers_answer_as_before`: `normalize_location_id`, `location_display_name`, `_reference_token_matches`, two inputs each, one with Turkish letters, pinned on `BASE_SHA`.
- [ ] **Step 2:** Run (FAIL on membership). M4-M6 with the `_PART_MODULES` edit, then M7 (with the `--manual` pair), M8, M9 (`PROBE ok` lists `game_parts.places`).
- [ ] **Step 3: Seeded proof for the wrapper** (once in this plan; Plan 2 Task 13 did it for `text_rules_b`). Save `game.py` by the pre-plant rule. Take `"game_parts.places"` out of `_PART_MODULES` in the working tree. `test_every_re_export_is_the_parts_own_object` and `test_engine_routing` (R2) go red. Restore, check the sha256, record.
- [ ] **Step 4:** M10 (pattern runs `p3t8-places-1-off/-fon`, named `api.tests.test_economic_room api.tests.test_d207_written_purse`). M11 `game.py split T4.2a: doors, features and location helpers live in game_parts/places.py`.
- [ ] **Step 5: `places-2`.** `test_places_2_lives_in_the_part` (red); add `_walked_there` to the session test. M1-M10 (`p3t8-places-2-off/-fon`, named `api.tests.test_persistence_idempotency api.tests.test_d207_written_purse`). M10b. M11 `game.py split T4.2b: scene and local-place helpers live in game_parts/places.py`.

### Task 9: `intent.py` — batches `intent-1` (39, about 932) and `intent-2` (5, about 188); `_EXPERIMENTAL_NPC_SPEECH_OPTIONS` to `schemas.py` (spec T4.3)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no money code moves. Held for Plan 4 (fix wave 2, `writer_scan.py`): `_handle_query` (→ `create_npc_from_ai` → purse) and `update_world_state_from_player` (→ `execute_intent`, runtime snapshot and restore). M12 for each batch: `SUMMARY held=0 missing=0 clean=39` (`intent-1`), `clean=5` (`intent-2`), `clean=1` (`schemas-options`). `test_shops.py` patches `validate_intent`: the reviewer confirms the file is unchanged and green.

**Files:**
- Create: `ai-dnd/game_parts/intent.py`
- Modify: `ai-dnd/game_parts/schemas.py`, `ai-dnd/game.py` (`_PART_MODULES` gains `"game_parts.intent"` in `intent-1`), `surface.json`, `size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

**Batch notes:**
- `IntentInfrastructureError` is a class: it moves as a definition and is re-exported (identity: `game.IntentInfrastructureError is` the class the staying `except` clauses name).
- `validate_intent` is a census target (4 sites) and a production rebinding target (`trace_ai_pipeline.py`).
- `parse_player_intent`, `normalize_intent`, `execute_intent` are sensitive and stay.
- `schemas-options` is data only: no header, not in `_PART_MODULES`.

- [ ] **Step 1: Tests for `intent-1`:**
  - `test_intent_1_lives_in_the_part` (red).
  - `test_intent_session_helpers_use_the_given_session` for `is_npc_historical_claim`, `known_character_answer` (seed `20261203`).
  - `test_intent_helpers_answer_as_before`: `is_dialogue_or_emotion`, `_reads_as_question`, `_normalize_turkish_location`, two inputs each, pinned.
  - `test_the_intent_error_is_one_class`: `game.IntentInfrastructureError` is the class that the staying `except` clauses catch (find them with graphify: "who raises and catches IntentInfrastructureError"). Raise it from a moved caller's path and see it caught by the staying handler.
- [ ] **Step 2:** M1-M10 for `intent-1` (`p3t9-intent-1-off/-fon`; 10 touching modules + `ENGINE_SET` + `NEIGHBOURS`: plain `slot.sh`). M11 `game.py split T4.3a: intent reading helpers live in game_parts/intent.py`.
- [ ] **Step 3: `intent-2`.** Tests:

```python
def test_intent_2_lives_in_the_part(self):                               # red
def test_a_rebound_validate_intent_reaches_a_moved_caller(self):          # Review Focus 5
    # No test calls analyze_player_action today, and it calls parse_player_intent (the model) first. So patch the way
    # test_shops.py does (its patch block around run_player_turn): no session, no model, no campaign, no fixed_town needed.
    # seen = []
    # def validate(intent, player_input):
    #     seen.append((intent, player_input))
    #     return {"intent": "perception", "skill": "Perception", "difficulty": "hard"}
    # with patch.object(game, "parse_player_intent", return_value={"raw": 1}) as parse, \
    #      patch.object(game, "normalize_intent", return_value={"norm": 1}) as norm, \
    #      patch.object(game, "validate_intent", side_effect=validate):
    #     out = game.analyze_player_action("Etrafa bakıyorum.", "Fighter", [])   # moved to intent in intent-1
    # parse.assert_called_once_with("Etrafa bakıyorum.")
    # norm.assert_called_once_with({"raw": 1}, "Etrafa bakıyorum.")
    # self.assertEqual(seen, [({"norm": 1}, "Etrafa bakıyorum.")])
    # self.assertEqual(out, {"action_type": "check", "skill": "Perception", "difficulty": "hard"})
    # This reaches 3 of the 4 names trace_ai_pipeline.py rebinds (parse_player_intent, normalize_intent, validate_intent).
    # The 4th, execute_intent, is read by no mover: update_world_state_from_player is held (fix wave 2). Nothing to rebind-test.
```

  M1-M10 (`p3t9-intent-2-off/-fon`, named `test_shops api.tests.test_lr00_p1_intent`). M11 `game.py split T4.3b: intent validation helpers live in game_parts/intent.py`.
- [ ] **Step 4: `schemas-options` (D-376 live proof).**
  - Tests: `test_the_npc_speech_options_live_in_schemas` (red); `test_the_npc_speech_options_did_not_change` (`value_digest(("_EXPERIMENTAL_NPC_SPEECH_OPTIONS",))` pinned on `BASE_SHA`).
  - D-380 item 2: in `SchemasPart.test_the_system_prompt_is_one_object_for_module_and_sessions`, the session half becomes `assertIs`. Show it red first with a planted equal but distinct copy (`s.messages[0]["content"] = "".join(list(game.system_prompt))` in the test body, pre-plant rule). Not `game.system_prompt + ""`: CPython returns the same object for `s + ""` (measured `True`), so that plant stays green. Approval row §21: stricter.
  - M1-M10 (`p3t9-schemas-options-off/-fon`, named: the `inventory.py --touching` output for a names file `STORE/touching-options.txt` holding `parse_player_intent` and `_EXPERIMENTAL_NPC_SPEECH_OPTIONS`). M7 must print `CHANGED 0` with `_EXPERIMENTAL_NPC_SPEECH_SCHEMA` held right above: record it as the D-376 live proof.
  - M10b. M11 `game.py split T4.3c: NPC speech sampling options live in game_parts/schemas.py (D-376 live proof)`.

### Task 10: `dialogue.py` — batches `dialogue-1` (54, about 995) and `dialogue-2` (11, about 232) (spec T4.4)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no money code moves.
- `test_equipment_economy` patches `resolve_npc_reference`: the reviewer confirms the file is unchanged and green.
- `_settle_spoken_commitment` is held for Plan 4 (fix wave 2, measured): it reaches `town_knowledge.settle_reply` → `economic_actions.npc_gift` → `apply_resolution`, a coin move from an NPC purse to the player (`test_money_path_repair` names it). Its move would have been a money move under a normal review.
- The reviewer runs M12 for each batch (`SUMMARY held=0 missing=0 clean=54` for `dialogue-1`, `clean=11` for `dialogue-2`), reads `_job_talk_with` and `_offer_terms_shown` and confirms that neither writes coin, a wallet or a ledger (they are not in `sensitive.json`). If one does: hold it, `Ruling`, debt row, Plan 4.
- `_experimental_npc_dialogue_context` (census target, 8 sites) is now in `dialogue-1` (re-cut after the hold).

**Files:**
- Create: `ai-dnd/game_parts/dialogue.py`
- Modify: `ai-dnd/game.py` (`_PART_MODULES` gains `"game_parts.dialogue"`), `surface.json`, `size_budget.json`, `ai-dnd/api/tests/test_talk_mode_writers.py`, `docs/agents/onay-listesi-20261115.md` (§21)
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

**Batch notes:**
- `_STOCK_SAID` (`collections.deque`) moves with `_stock_said`. Its only reader is in the same part, so it stays bare there; the re-export keeps one object. No outside reader (measured: 0 sites).
- `_npc_speech_enabled` reads `os` (census `import`): the mover writes `game.os`.
- Plan 2 held names that move here: `_said_to_someone_here`, `_town_in_play` (measured: dialogue).

- [ ] **Step 1: The file-set pin first** (red before `dialogue-1`). `test_talk_mode_writers.test_no_product_call_passes_a_people_list_to_current` expects `["api/serializers.py", "game.py", "game_parts/dialogue.py"]`: `_active_interlocutor` moves in `dialogue-1`, `_said_to_someone_here` in `dialogue-2`, `_run_player_turn_internal` stays.
  - Approval row §21: "dosya kümesi tam liste olarak kalır, bir dosya eklendi; eşit sıkılık".
  - `test_every_interlocutor_clear_names_its_reason` is unchanged (its callers stay; appendix D).
  - If `dialogue-1`'s M2 holds `_active_interlocutor`, the pin changes in `dialogue-2` instead; say so.
- [ ] **Step 2: Tests for `dialogue-1`:**
  - `test_dialogue_1_lives_in_the_part` (red).
  - `test_the_stock_said_deque_is_one_object`: `game._stock_said() is game._STOCK_SAID` for a call with no session.
  - `test_dialogue_session_helpers_use_the_given_session` for `record_npc_interaction`, `resolve_npc_reference`, `_npc_speech_is_claim_refusal` (seed `20261205`); `_direct_npc_smalltalk_response` is added in `dialogue-2`.
  - `test_dialogue_helpers_answer_as_before`: `_is_end_conversation_request`, `_words_fit_person`, `historical_claim_denial`, pinned.
- [ ] **Step 3:** M1-M10 (`p3t10-dialogue-1-off/-fon`, named `api.tests.test_talk_mode_writers api.tests.test_equipment_economy api.tests.test_talk_front`). M11 `game.py split T4.4a: conversation and NPC speech helpers live in game_parts/dialogue.py`.
- [ ] **Step 4: `dialogue-2`.** `test_dialogue_2_lives_in_the_part` (red); add `_direct_npc_smalltalk_response` to the session test. M1-M10 (`p3t10-dialogue-2-off/-fon`). M10b. M11 `game.py split T4.4b: player-name and small-talk helpers live in game_parts/dialogue.py`.

### Task 11: `lore.py` — batch `lore`, 14 names, about 999 lines (spec T4.5)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no. M12: `SUMMARY held=0 missing=0 clean=14` (13 if `_empty_lore_authority_context` stays out).

**Files:**
- Create: `ai-dnd/game_parts/lore.py`
- Modify: `ai-dnd/game.py` (`_PART_MODULES` gains `"game_parts.lore"`), `surface.json`, `size_budget.json` (keys `game_parts/lore.py::_supported_lore_question_response` 479, `::_player_question_has_unverified_lore_claim` 196)
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

**Batch notes:** `_empty_lore_authority_context` is in the batch only if `F_fon` is empty (Task 4 Step 3). `_lore_entity_names` is sensitive and stays.

- [ ] **Step 1: Tests:**
  - `test_lore_lives_in_the_part` (red).
  - `test_lore_helpers_answer_as_before`: `_stage_within_the_street`, `_shown_stage_direction`, `_names_the_district_here`, inputs from their existing tests, pinned.
  - `test_the_empty_lore_context_is_a_fresh_value_each_call` (if it moves): two calls give equal, not identical, objects; measure on `BASE_SHA` first and pin what is true.
- [ ] **Step 2:** M1-M10 (`p3t11-lore-off/-fon`; 306 touching modules: pattern runs). M10b. M11 `game.py split T4.5: lore authority helpers live in game_parts/lore.py`.

### Task 12: `narration.py` — batch `narration`, 21 names, about 484 lines (spec T4.6)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no. Held for Plan 4 (fix wave 2, `writer_scan.py`): `_fallback_for_action_result` and `_states_the_failed_check` (→ `_combat_narration` → `_death_closing` → `ensure_death_state`, which writes the default death state), with `_fallback_narration` (misfit: only caller held) and `_stands_by_their_words` (only caller `_fallback_narration`). M12: `SUMMARY held=0 missing=0 clean=21`. Ten sensitive narration names stay, among them `build_world_context`, `ask_dungeon_master` and `finalize_narration` (the narrative-adapter targets). No moved name calls them (measured).

**Files:**
- Create: `ai-dnd/game_parts/narration.py`
- Modify: `ai-dnd/game.py` (`_PART_MODULES` gains `"game_parts.narration"`), `surface.json`, `size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

- [ ] **Step 1: Tests:**
  - `test_narration_lives_in_the_part` (red).
  - `test_narration_session_helpers_use_the_given_session` for `_generic_no_change_response`, `_inspection_findings` (seed `20261206`).
  - `test_narration_helpers_answer_as_before`: `_repair_internal_marks`, `_drop_absent_counter_sentences`, pinned; at least one input with curly quotes (`_states_the_failed_check` is held, fix wave 2).
  - `test_a_patched_should_generate_npcs_reaches_its_staying_caller`: `patch.object(game, "should_generate_npcs", return_value=False)`, then the staying caller the existing census site exercises sees `False` (graphify: "who calls should_generate_npcs"). It replaces the `_fallback_narration` test: that census target is held (fix wave 2); `should_generate_npcs` is the batch's only census target left.
- [ ] **Step 2:** M1-M10 (`p3t12-narration-off/-fon`; 6 touching modules: `slot.sh`). M10b. M11 `game.py split T4.6: narration fallback and repair helpers live in game_parts/narration.py`.

### Task 13: `narration_safety.py` — batches `nsafety-1` (14, about 426) and `nsafety-2` (`_narration_safety_decision`, 1 054) (spec T4.7)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no money code moves. `_authorized_item_transfer_matches` and `_is_explicitly_negated_transfer` guard item transfers in narration. The reviewer confirms they only read state (no write), as `sensitive.json` says. M12 for each batch: `SUMMARY held=0 missing=0 clean=14` (`nsafety-1`), `clean=1` (`nsafety-2`).

**Files:**
- Create: `ai-dnd/game_parts/narration_safety.py`
- Modify: `ai-dnd/game.py` (`_PART_MODULES` gains `"game_parts.narration_safety"`), `surface.json`, `size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

**Frozen size (spec §11).** After `nsafety-2`, `size_budget.json` gains `files["game_parts/narration_safety.py"] = <its real line count>`. The existing `budget_findings` rule then refuses any growth. The long-function key becomes `game_parts/narration_safety.py::_narration_safety_decision` (1 054).

- [ ] **Step 1: `nsafety-1`.** `test_nsafety_1_lives_in_the_part` (red); `test_nsafety_helpers_answer_as_before` (`_remove_trigger_sentence`, `is_player_world_assertion`, pinned). M1-M10 (`p3t13-nsafety-1-off/-fon`; pattern runs). M11 `game.py split T4.7a: narration safety checks live in game_parts/narration_safety.py`.
- [ ] **Step 2: `nsafety-2`.**
  - Tests: `test_nsafety_2_lives_in_the_part` (red); `test_the_safety_decision_answers_as_before` (three inputs from its existing tests: one safe, one unsafe, one repaired; the decision tuples are pinned on `BASE_SHA`).
  - M1-M9. M8 `clean` also confirms Task 3's function-scope walrus guard on real code (`_narration_safety_decision`; this shape was already clean before the fix, measured).
  - Add the frozen `files` entry. Then plant one extra line in the part (pre-plant rule): `test_the_engine_fits_its_budget` goes red; restore; record.
  - M10 (`p3t13-nsafety-2-off/-fon`). M10b. M11 `game.py split T4.7b: the narration safety decision lives in game_parts/narration_safety.py, frozen at arrival size`.

### Task 14: `living_world_turn.py` — batch `lwt`, 4 names, about 216 lines (spec T4.8)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no money or death code moves. `advance_campaign_time` stays in `game.py` for Plan 4 (fix wave, measured): it calls `equipment_economy.process_supply_days`, which can return `condition_death`, and reads `ensure_death_state`, `heal_player`, `stabilize_player`, `_resolve_player_death_turn`. With it held, the touching list drops from 19 to 6 modules and holds no money, save or death test (measured; `test_economic_undo`, `test_economic_dialogue` and `test_death_bounded` read only `advance_campaign_time`). M12 with the `lwt` batch file: `SUMMARY held=0 missing=0 clean=4` (fix wave 3 moved the four names with `move_block.py` on a throwaway copy of `0e5257e7` and got exactly this line): no moved `lwt` name reaches a coin, supply, death or save writer in any number of hops (measured on `b1150df8`); the reviewer also reads the four names for a direct write. `plan_living_world_turn` (725 lines) is sensitive and stays.

**Files:**
- Create: `ai-dnd/game_parts/living_world_turn.py`
- Modify: `ai-dnd/game.py` (`_PART_MODULES` gains `"game_parts.living_world_turn"`), `surface.json`, `size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

**Batch notes:** no census `import` target and no census target moves in `lwt` (the `uuid4`/`effect_lifecycle` reads and the 12 patch sites belong to the held `advance_campaign_time`; its `uuid4` test goes with it to Plan 4).

- [ ] **Step 1: Tests:**
  - `test_lwt_lives_in_the_part` (red).
  - `test_living_world_session_helpers_use_the_given_session` for `ensure_campaign_clock`, `_living_world_prompt_context` (seed `20261207`).
- [ ] **Step 2:** M1-M10 (`p3t14-lwt-off/-fon`; 6 touching modules: `slot.sh`; named `api.tests.test_economic_undo api.tests.test_economic_dialogue api.tests.test_death_bounded`, kept as callers of the held clock). M10b. M11 `game.py split T4.8: campaign clock and scene seating live in game_parts/living_world_turn.py`.

### Task 15: `new_game.py` — batch `newgame`, `initialize_game` (spec T4.9)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no; the reviewer reads `initialize_game` for a save or wallet write and finds none, or holds it. M12: `SUMMARY held=0 missing=0 clean=1`.

**Files:**
- Create: `ai-dnd/game_parts/new_game.py`
- Modify: `ai-dnd/game.py` (`_PART_MODULES` gains `"game_parts.new_game"`), `surface.json`, `size_budget.json` (key `game_parts/new_game.py::initialize_game` 197)
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

**Batch notes.**
- `game.py` calls `initialize_game(creation_choice="2", print_fn=...)` at import time, after `_bind_session_engine()`. The re-export line lands at the cut position, above that call, so the call reads the re-exported, wrapped function.
- The defaults `input` and `print` are builtins: they move unchanged.
- The import-time call runs while `game` is still in `sys.modules` half-built. Every `game.X` it reads must be bound above the call. The rehearsal (Task 5 Step 2) and M9 prove this; a `NameError`/`AttributeError` there stops the task.

- [ ] **Step 1: Tests:**

```python
def test_newgame_lives_in_the_part(self):                                          # red
def test_the_import_time_game_is_initialized_by_the_moved_function(self):           # Review Focus 3
    # the wrapper's wrapped function (read _bind_session_engine for the attribute it sets; Plan 2 tests use __wrapped__)
    # has __module__ == "game_parts.new_game"; and game._DEFAULT_SESSION.character has a non-empty name and max_hp > 0
def test_both_import_orders_work_in_a_fresh_interpreter(self):                      # existing test (skipped in the slot, runs in CI)
    # extend its expected output with one function per new part (places, intent, dialogue, lore, narration,
    # narration_safety, living_world_turn, new_game): approval row §21, "iddia eklendi, gevşetme değil"
```

- [ ] **Step 2:** M1-M9. M9 must show `PROBE ok` with the `python game.py` dice turn (`D20 sonucu:`, `Oyun kapatılıyor`). M10 (`p3t15-newgame-off/-fon`, touching `test_sessions test_startup`). M10b. M11 `game.py split T4.9: initialize_game lives in game_parts/new_game.py`.
- [ ] **Step 3:** Ledger:
  - line counts of `game.py` and of every part (all at most 2 500; `narration_safety.py` at its frozen value);
  - the held table of Plan 3 (name, reason, target plan);
  - the list of D-378 names moved.

### Task 16: The net's exam on the moved tree

**Review tier:** none (Opus runner; nothing committed). Money/save/Undo: no.

**Files:** none committed. Worktree `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-t4x`, branch `tmp/game-py-bolme-ag-sinavi-p3` from the Stage B tip; never pushed, not deleted. Targeted runs on `SLOT` 2; N4 runs (Fault 4) on `FSLOT` 4 after the gate wait.

Routine: apply one fault alone, run the named check, see the stated red, `git checkout HEAD -- ai-dnd`, next fault. Record each failing line.

- [ ] **Fault 1 — bare call to a patched name.** In `character_rules.py`, `roll_attack` calls bare `roll_d20(...)`. Expected red: `test_engine_routing` (R3, R9).
- [ ] **Fault 2 — missing `_PART_MODULES` entry.** Remove `"game_parts.dialogue"`. Expected red: `test_every_re_export_is_the_parts_own_object`, `test_engine_routing` (R2).
- [ ] **Fault 3 — `global` in a part.** `global _STOCK_SAID` plus an assignment inside `_stock_said`. Expected red: `test_engine_routing` (R7).
- [ ] **Fault 4 — frozen alias (N4).** In `game.py`, `_VALIDATE = validate_intent` after the re-export, and `_run_player_turn_internal` calls `_VALIDATE`.
  - Clean pair first: labels `p3x-f4a-n4-off`, `p3x-f4b-n4-off`, modules `api.tests.gate_boot test_shops api.tests.test_lr00_p1_intent` + `NEIGHBOURS`; `--collect` both.
  - Fault run `p3x-f4-n4-off`; `--diff`. Expected: `DROPS` above 0 with keys ending `|validate_intent`.
- [ ] **Fault 5 — module-level `game.X` in a part.** `_ORDER = game.RULE_ORDER` at the top of `places.py`. Expected red: R4.
- [ ] **Fault 6 — default-argument capture.** One moved helper in `intent.py` gets `def f(x, check=game.validate_intent)`. Expected red: R4 (evaluated at import).
- [ ] **Fault 7 — deleted comment.** Remove one comment line from a block moved in Task 13. Expected: `move_check` `CHANGED` above 0 and `COMMENTS base=<C> now=<C-1>`.
- [ ] **Fault 8 — session dropped.** In `places.py`, make `resolve_location_reference` read `game._DEFAULT_SESSION` where it read `game._session()` (`commit_location_change` is held in `game.py`). Expected red: `test_places_session_helpers_use_the_given_session` (Review Focus 4).
- [ ] **Final step:** back on the Stage B branch: `git status` clean; `ENGINE_SET` + `NEIGHBOURS` green in both flags. A fault that stayed green stops the plan before the gate: fix the check red-first in its owning file, then repeat the exam.

### Task 17: Gate TM3 (spec TM3), PR 7 and Kadir's play

**Review tier:** strong (whole-branch review on Opus; the Stage B diff, the money/Undo tests named in Tasks 8-10, 12 and 14, and `writer_scan.py` on the gate tree with all 14 batch files: `SUMMARY held=0 missing=0 clean=<lines in the 14 files>`, 242 as measured, exit 0).

- [ ] **Step 1:** `git fetch origin`; merge `origin/main` if it moved. If `game.py` or a part changed underneath: rerun M7 for every batch against a fresh base, regenerate the locks, and tell Kadir which N4/N7 names the change touches before going on.
- [ ] **Step 2: Whole-branch review before the suites.** The reviewer reruns M7 for all 14 batches on the archive copy, each with its own move commit's parent as root, and the writer scan once on the gate tree with all 14 batch files (the review tier line). The reviewer also reads `analyze_player_action` (moved in `intent-1`): through `parse_player_intent` and the model adapter it reaches API spend (`api.model_chain:HaikuSpend.add`, `api.usage_ledger`). The scan counts those as telemetry, not save state (fix wave 2 Ruling 3), so it cannot see this path; the reviewer confirms the path writes no campaign, money, death or save state, or holds the name (`Ruling`, debt row, Plan 4). One fix wave, red-first (Opus); scoped re-review (Opus). From Step 3 on, only the ledger, debt rows and PR text change; any change to code, tests or locks reruns Steps 3-6 (`Ruling` with the reason).
- [ ] **Step 3: N4/N7 bases (Task 0 Ruling (a)).** `git worktree add --detach ../AI-DND-k2-bolme-t4b <Stage A tip>`; in it, `git merge --no-ff --no-edit <MAIN_SHA>`, where `<MAIN_SHA>` is the same `origin/main` commit Step 1 merged into Stage B (or no merge if Step 1 merged none). This is a local, detached merge: never pushed.
  - Check before the first suite: `git diff <t4b HEAD> <Stage B tip> --stat -- . ':!ai-dnd/game.py' ':!ai-dnd/game_parts'` lists only Stage B's own test and lock files (`test_engine_parts_pilot.py`, `test_talk_mode_writers.py`, `surface.json`, `size_budget.json`, `patch_census.json` if a task regenerated it, the docs). Any other file means base and gate differ in tests, so LOST/DROPS/DOWN would come from tests, not moves: stop and rebuild the base. Paste the list in the ledger.
  - Four suites, one at a time, each after the gate wait, `WT` = `AI-DND-k2-bolme-t4b`: `p3g0-off-n4-n7-b`, `p3g0-off-n4-n7-c`, `p3g0-fon-n4-n7-b`, `p3g0-fon-n4-n7-c`.
  - Pass: `PAR_EXIT=0`, `failing_ids 0` (flag on: the `F_fon` fallback of Global Constraints).
  - Probe completeness:
    - every shard has a non-empty `engine-probe/ledger-*.jsonl` and `lines-*.json`;
    - every shard's `proof.json` `selectors` starts with `api.tests.gate_boot` (closes D-367);
    - in both fon outcome ledgers `test_the_fon_token_turns_the_flag_on_inside_the_child` is `ok`, in both off ledgers `skip`.
  - Compute per flag: `ledger-{b,c}.json`, `lines-{b,c}.json` (`--engine-root` = archive of the `t4b` HEAD, the merged base), the noise sets, the seconds.
  - D-373's remainder and D-387/D-393 (unless closed by then) enter the flag-off noise list here; write their size.
- [ ] **Step 4: Gate suites** on the Stage B tip (`WT` = `AI-DND-k2-bolme-t4`): `p3tm3-off-n4-n7`, then `p3tm3-fon-n4-n7`. Pass: `PAR_EXIT=0`, `failing_ids 0` in both. A red stops the plan and Kadir is told.
  - An unseeded red (Plan 2 TM2 procedure, D-377): a 40-fixed-town-seed probe of that test on both the Stage B tip and the base tree (temporary, not committed); if both fail the same seeds, trace the origin commit, write a debt row, tell Kadir, and retake that flag's suite once. Accept the retake only when it is green or red with exactly the same id; any other red stops (the CLAUDE.md stop list stays the four cases).
- [ ] **Step 5: N4 and N7 per flag.**
  - `ledger_diff.py --diff --base <b> --base2 <c> --new <tm3>`: `DROPS 0`, `LOST 0`, `SUBLOST 0`, `SUBGONE 0`, `SUBCRASH 0`. Stage B never renames or deletes a test id.
  - `coverage_by_function.py --diff` with `--engine-root` = archive of the gate commit: `DOWN 0` outside the noise set. Every `UP` name goes in the ledger with the test that explains it.
  - Any drop, lost test or `DOWN` stops the plan and Kadir is told.
  - The PR text gives what N4 cannot see: `not_called_tests`, assignment sites, `kind other`, and the runtime blind spot of D-380 item 6 with this gate's own counts.
- [ ] **Step 6: Speed (spec §7).**
  - Flag off suite: at most 2 155 s (1.10 × TM0) and at most 1.10 × the mean of the two off bases. Flag on suite: at most 1.10 × the mean of the two fon bases.
  - Bench twice (gate wait first): reading 1 at most 23.13 ms and at most 1.10 × Task 0 reading 1; reading 2 at most 23.25 ms and at most 1.10 × Task 0 reading 2.
  - One flag-on reading `p3tm3bench-fon` (`gate_boot` first), against Task 0's `p3t0bench-fon`: recorded, not a limit (Kadir plays flag on).
  - Above any limit: stop and report; do not explain it away.
- [ ] **Step 7: Checks without a suite.**
  - `SLOTPY outside_probe.py` → `PROBE ok parts=` lists the Plan 2 parts plus `dialogue`, `intent`, `living_world_turn`, `lore`, `narration`, `narration_safety`, `new_game`, `places` (D-341).
  - `python test_regression.py` → `Results: 30 passed, 0 failed out of 30` (D-342).
  - `move_check.py --comments-only` against the `P3BASE` archive → `COMMENTS base=<C> now=<C>`.
  - `routing_audit.py` → `clean`.
  - `patch-census.md` regenerated if a task changed the lock.
  - ruff once; output in the ledger (D-380 item 5).
  - Review Focus 3: read `start_local.ps1` for the interpreter it starts. With it, from `ai-dnd`, run `-c "import game, game_parts"` and `-c "import game_parts, game"`: rc 0 twice.
  - Sizes: `game.py` real lines = `size_budget.json`; every part at most 2 500; `narration_safety.py` at its frozen value.
- [ ] **Step 8: Debt rows.**
  - D-378: Plan 3 names moved; the remaining names with Plans 4/5.
  - D-341, D-342, D-349, D-380 updated with this gate's lines. D-367 closed.
  - Every park gets a row (D-43x); no park without an owner.
  - `F_fon` rows: state.
- [ ] **Step 9:** Recheck the free debt ids. Ask Kadir: push + PR 7 (stacked on PR 6), then the merges in order. Before each merge, check the target tip is an ancestor. After each: the CI rules of Global Constraints.
- [ ] **Step 10: Play gate.** Ruling: Kadir plays on `main` after the merges with his normal start (`start_local.ps1`, flag on by default). His start script runs from the main checkout. If wrong: a fault found in play is fixed on a new branch instead of on PR 7.
  - Ledger line "oynayış bekliyor" until he has played at least 10 minutes. His notes go to the ledger and, if they name a fault, to a debt row.
  - Plan 4 does not start before his play.
- [ ] **Step 11:** Check for open `bash`/`sleep` processes and the `t4b`/`t4p` slots' runs. Five-line Turkish morning summary. Ledger lines "TM3 geçti", "oynayış bekliyor" (or the play result), "Plan 3 bitti; Plan 4 (T5) yazılabilir". The plan workspace is not deleted.

---

## Debt rows this plan owns (trigger names Plan 3, T4 or TM3) and what happens to each

| Row | Handling |
|---|---|
| D-341 outside probe at every gate | M9 every move; Task 6 Step 3; Task 17 Step 7; stays open (not a CI test) |
| D-342 `test_regression.py` as a script | Task 6 Step 3; Task 17 Step 7; fixed seed still missing: carry-forward, trigger unchanged |
| D-349 N3 blind spots, "Plan 3 Görev 0" | Task 3 closes item M9 red-first (module-level generator walrus gave a false R5; measured on 3.14 and 3.13; no T4 mover has one, and the function-scope shape of `nsafety-2` was already clean); the rest is carried to "Plan 4 Görev 0" with the measured "no T4 name hits it" line (Task 3 Step 3) |
| D-351 small tool gaps, "Plan 3 Görev 0" | open item (`import game` unused in `text_rules_a`) carried to Plan 6 (Task 0 Step 6); ruff state recorded at Tasks 6 and 17 |
| D-359 `gate_boot` tokens, "Plan 3 Görev 0" | Task 2 (`_engine_import`); `slot.sh` label check carried with a `Ruling` (Task 2 Step 4) |
| D-360 `move_check` other parts / stale exemption | Task 1 |
| D-361 items 1, 2, 4, 5, "Plan 3 Görev 0" | Task 2 |
| D-363 top-level `if`/`try` (N7) | not triggered: measured, no T4 name sits inside one (appendix D); Task 4 Step 3 rechecks; carry-forward |
| D-364 surface test helper, "en geç Plan 3 Görev 0" | Task 4 |
| D-366 `touching_tests` two-step chain | Task 4 (Task 4 touches `inventory.py`) |
| D-367 `slot_gate.sh` selectors in every shard | Task 17 Step 3 |
| D-368 Stage A process parks, "Plan 3 Görev 0" | Task 0 Step 6 (closed with the process rule) |
| D-369/370/371 flag-on job | precondition (Task 0 Step 2) |
| D-372 repeated-id outcomes, "Plan 3 Görev 0" | Task 2 |
| D-373 remainder, "Plan 3'ün bayrak kapalı gürültü listesi" | Task 17 Step 3 |
| D-376 `move_check` false alarm, "Plan 3 Görev 0, tabanlardan önce" | Task 1; live proof Task 9 Step 4 |
| D-378 held names with target plans | Tasks 7-15 move the Plan 3 rows; Task 17 Step 8 updates the row and adds the 15 fix-wave holds (Plan 4; `_adventure_travel_reply` moves from the Plan 3 row to Plan 4) |
| D-355 N8 sees moved names only by text | trigger stays "Plan 4 Görev 0"; Task 4 Step 3 adds the transitive writer scan (`writer_scan.py`) and a new linked row (`D-43x`) for the 15 holds |
| D-379 blank lines, "Plan 3 Görev 0 (taşıyıcı) ya da Plan 6" | carried to Plan 6 with a `Ruling` (Task 0 Step 6) |
| D-380 items 2-8, "Plan 3 Görev 0" | (2) Task 9 Step 4; (3) Plan 6; (4) Task 0 Step 2; (5) Tasks 6 and 17, no fix (spec §9); (6) Task 17 Step 5 PR text; (7) next test-infrastructure work; (8) Task 5, M10b, Task 17 Step 6 |
| D-387, D-393 "Plan 3 tabanlarından önce" | Task 0 Step 1 (b) tells Kadir; Task 17 Step 3 records them in the noise list if still open |

Rows whose triggers Plan 3 does not reach are carried unchanged: D-343 (T7), D-344 and D-345 (Plan 5), D-346 (scripts untouched), D-356, D-357, D-358, D-362, D-365 (`outside_probe.py` untouched).

---

## Plans 4-6 outline

Each is written after the previous gate and Kadir's play, as its own plan, worktree pair and PR pair. Each starts with the module map (appendix A scripts) measured again on its own base.

**Plan 4 — T5 money, save, combat and the sensitive leftovers, to spec TM4.**
- **Scope:** `combat_flow` (52 non-sensitive + 9 sensitive), `coin` (5 + 10), `savefile` (11 + 8), the 27 sensitive leftovers of T4 topics (appendix E, among them `parse_player_intent`, `ask_dungeon_master`, `finalize_narration`, `plan_living_world_turn`), `_EXPERIMENTAL_NPC_SPEECH_SCHEMA`, Plan 2's held savefile/death/money names (D-378), and Plan 3's 15 fix-wave holds (names that reach a money, death or save/Undo writer, measured transitively by `writer_scan.py`, and helpers whose callers are all held): `create_npc_from_ai`, `commit_location_change`, `advance_campaign_time`, `generate_npc_id`, `_ensure_location_entities`, `_commit_travel_action`, `_adventure_travel_reply`, `_promote_scene_referent`, `_handle_query`, `update_world_state_from_player`, `_settle_spoken_commitment`, `_fallback_for_action_result`, `_states_the_failed_check`, `_fallback_narration`, `_stands_by_their_words` (their `uuid4`, purse, travel, quest-reward, NPC-gift and death tests come with them).
- **Entry condition:** Kadir has played after TM3. D-355 is closed first (`sensitivity.classify` over the whole engine file set, so `test_engine_sensitivity` sees moved names; `writer_scan.py`'s transitive reach is the measured starting point, its blind spots named in the D-43x row). D-349's carried items are rechecked against the Plan 4 names (it moves dynamic code: `open`, `uuid4`, narrative adapters).
- **Strong-review points:** every task (money, save, Undo, death). The narrative-adapter identity test (D-349: `api/narrative_director.py` rebinding three names in the same process). N7 equality, which spec §6 makes due at TM4.
- **What Plan 3's ledger hands it:** the held table; the TM3 N4/N7 noise sets and run folders; the rehearsal and TM3 bench numbers; the M5 header Ruling; the list of money/Undo tests that read moved names; F_fon state.

**Plan 5 — T6 turn core, to spec TM5.**
- **Scope:** `turn` (38 non-sensitive + 31 sensitive, about 5 362 sensitive lines, `_run_player_turn_internal` 2 743 lines), `_has_session`, `DEBUG_MODE`, `turn_source_key`, `_intent_infrastructure_result`, `_dynamic_engine_transitions`, `_STOCK_SAID` if Plan 3 held it; `turn.py` frozen at arrival size (spec §11); D-344, D-345.
- **Entry condition:** TM4 passed and played. The identity allow-list state is known. The zero-tolerance journey list is fixed.
- **Strong-review points:** all of it (turn core, Undo, session binding). The `_GameModule` hook cost is measured again, since Plan 5 moves the hottest callers.
- **What Plan 3's ledger hands it:** the per-task M10b bench deltas (cost per moved batch); whether Task 5's alternative was taken; the session-binding test pattern; the walrus fix.

**Plan 6 — T7 closure.**
- **Scope:**
  - final sizes, then dead-code candidates with both-flag N7 evidence (`analyze_player_action` and `update_world_state_from_player` of spec §10, `_SHOP_CREATION_ACTION_PATTERN`);
  - D-343, D-379 (one layout commit for blank lines and the K02/K04 comments), D-351's `import game` in `text_rules_a`, D-380 item 3;
  - the dev-only pieces to remove or keep (`gate_boot.py`, `engine_probe.py`, `slot_gate.sh`, the `uvx` ruff cache);
  - Kadir's closing play.
- **Entry condition:** TM5 passed and played.
- **Strong-review points:** any deletion (dead code needs both-flag evidence and Kadir's yes); the closing whole-branch review.
- **What Plan 3's ledger hands it:** the parks carried to Plan 6 by name.

---

## Self-review

1. **Spec coverage.**
   - T4.1-T4.9 map to Tasks 7-15. Spec §8's verification ("the test modules that patch names in that module, N2 list") is M10's `--touching` list in both flags.
   - The T4.6-9 rebinding test is measured: the narrative-adapter names stay. It is Task 9's `validate_intent` test plus Task 16 Fault 4; the narrative-adapter test is handed to Plan 4.
   - TM3 (Task 17): suites ×2, N4, speed and bench, PR, 10-minute play.
   - Spec §11 sizes: Task 13 freezes `narration_safety.py`; Tasks 15 and 17 record sizes. §12 freeze and play: Global Constraints. §7 speed stop: Task 5, M10b, Task 17 Step 6.
2. **Step scan.** No step says "similar to" without its own content. Each move task names its batches, tests, labels, named M10 modules and commit messages. Test bodies whose arguments depend on existing tests name the graphify query that finds them.
3. **Name consistency.**
   - Batch names match appendix C and the batch file names of Task 4.
   - Labels follow `p3t<N>-<batch>-<off|fon>` everywhere. No off label contains "fon"; batch names contain no "fon".
   - Test names in Review Focus match the tasks.
   - `_PART_MODULES` additions: places, intent, dialogue, lore, narration, narration_safety, living_world_turn, new_game; not schemas (data only).
4. **Review Focus.** The five items each name a test or gate step in their owning task. Item 4's test is shown red in Task 16 Fault 8; item 5's path is shown red as N4 `DROPS` in Fault 4.
5. **Proportion.**
   - 18 tasks: Stage A 7 (4 small tool tasks, rehearsal, gate), Stage B 11 (9 moves, exam, gate). Review tiers: strong 2 (Tasks 6, 17), normal 13 (Tasks 1-4, 7-15), none 3 (Tasks 0, 5, 16).
   - Full suites: 6, all in Task 17, plus up to 2 if a change after Step 3 forces a rerun.
   - Pattern runs: about 20 (`cr`, `places-1`, `places-2`, `dialogue-1`, `dialogue-2`, `lore`, `nsafety-1`, `nsafety-2`, each ×2 flags), each well under a full suite. The largest wall-time cost is M10. It is bounded by the gate wait and slot 4 only.
6. **Measurement provenance.** Every list and number is in the appendix with its command. Task 0 and Task 4 measure again on `P3BASE` with the slot's Python, and the plan says what to do when a number moves.

## Execution

Subagent-driven, one task at a time in Stage B; speed rule 1 only in Stage A. The controller holds the ledger, the gate waits and the labels. Implementers get the Move procedure word for word and the task text.
