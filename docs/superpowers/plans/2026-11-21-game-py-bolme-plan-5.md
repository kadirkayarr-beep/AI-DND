# game.py Split, Plan 5 (T6 turn core into `turn_front.py` and `turn.py`, to spec TM5; then the D-429 money fix) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: DRAFT, pre-flight review fixed** (section "Pre-flight review fixes" at the end). The numbers come from a read-only measurement of p4m `0b1dca5a` (Plan 4 Stage B after Task 9). Task 0 measures again on the tree that holds the TM4 merge and replaces the batch files where anything differs (Ruling M below).

**Goal:** Move the 67 names of spec stage T6 (6 153 lines, every one of them turn code) out of `ai-dnd/game.py` into two new parts: `game_parts/turn.py` (spec §5's turn core, 16 names, 3 974 lines, frozen at arrival) and `game_parts/turn_front.py` (the rest, 51 names, 2 179 lines, a normal part). Pass spec gate TM5. Then fix D-429 (coin decision without a reading) as its own red-green money task.

**Architecture:** Unchanged from Plans 1-4. Moved code lives in `ai-dnd/game_parts/` and reaches engine names as `game.X` (centre rule). The mover adds the prefix in place. `game.py` re-exports every moved name with explicit `from game_parts.turn_front import ...` and `from game_parts.turn import ...` lines. Both join `_PART_MODULES`.

Stage A builds the two tools the turn core needs and nothing else:
- `move_block` learns to move an identity name that an `identity_allowlist.json` row allows (the turn function keeps its `locals()` call; spec §7);
- `game.py` stops using `sys.modules[__name__]` in its two turn functions, in its own pinned, behaviour-neutral commit.

Then it writes the batch files and rehearses the whole move with a cumulative speed check. Stage B moves the six batches under the strong review. Stage C fixes D-429 after TM5.

**Tech Stack:** Python stdlib (`ast`, `symtable`, `tokenize`, `unittest`); guarded WSL runner `slot.sh`; repo gate runner `ai-dnd/scripts/engine_split/slot_gate.sh`; `ruff==0.17.5` through `uvx` (a second opinion only, never `--fix`/`format`).

**Spec:** `docs/superpowers/specs/2026-11-17-game-py-bolme-design.md` (approved 2026-11-17): §5 (`turn.py` content), §7 (identity names, speed), §8 rows T6.1, T6.2 and TM5, §11 (each part ≤ 2 500; `turn.py` frozen at arrival size). The spec is the authority: where this plan and the spec differ without a `Ruling` line, the spec wins.
- Plan 3 (`docs/superpowers/plans/2026-11-19-game-py-bolme-plan-3.md`) holds the Move procedure M1-M12.
- Plan 4 (`docs/superpowers/plans/2026-11-20-game-py-bolme-plan-4.md`) holds the deltas this plan builds on, and its ledger (`C:/Users/Kadir/Desktop/AI-DND-k2-bolme-p4n/.superpowers/sdd/2026-11-20-game-py-bolme-plan-4/progress.md`) the rulings.

**Appendix:** `docs/superpowers/plans/2026-11-21-game-py-bolme-plan-5-appendix.md` (measured map, the six batches, risk checks, writer scan, speed history, commands, `game.py` after Plan 5). Scripts, raw outputs, draft batch files and draft writer reading lists are in `docs/superpowers/plans/2026-11-21-game-py-bolme-plan-5-measure/`.

**Scope:**
- spec rows T6.1, T6.2 and gate TM5;
- D-344, D-345 (spec §7 identity names), D-429 (Stage C);
- every debt row whose trigger names Plan 5, T6 or TM5 (table "Debt rows this plan owns").

**Gates:**
- G6a = net gate (Task 5): Stage A reviewed, then PR A.
- TM5 = spec TM5 (Task 13): N4/N7 bases, gate suites, cumulative speed, then PR B, stacked on PR A.
- PR C = the D-429 fix (Task 14), stacked on PR B, merged after it.

**Measured draft base (2026-11-21, read-only, p4m `0b1dca5ad1e293956742d9c08b5aaaadc0c786e9`, WSL Python 3.12.3; appendix B-F, I):**
- `game.py` 11 971 lines, 130 top-level names. Plan 4 Tasks 10-15 (43 names, about 3 675 lines) are still in it; they leave before Plan 5 starts.
- `turn` topic: 69 names / 6 231 lines (37 names / 814 lines plus 32 sensitive / 5 417). Plan 4's outline said 38 / 815: `COIN_LEFT_BEHIND` went to `coin` in Plan 4.
- Two names stay in `game.py` (Ruling I): `_restore_in_place`, `_dynamic_engine_transitions`. Move set: 67 names / 6 153 lines, 31 sensitive.
- `_run_player_turn_internal` alone is 2 756 lines.
- `game.py` after Plan 5: 2 148 lines plus Plan 5's re-export lines; 1 292 of the 2 148 are blank and 97 comment-only (appendix I). What this means for ≤ 1 500: "Plan 6 outline".

## Global Constraints

- **Precondition and execution base.**
  - Plan 4 ledger ends with "TM4 geçti"; PR A and PR B of Plan 4 are merged; `origin/main` contains them.
  - `P5BASE` is the `origin/main` commit when Task 0 starts.
  - `TM0BASE` = `2e576967dda2fbfdf6a47d22d9313fbc76c195f8` (PR #128 merge, T0), unchanged from Plan 4.
  - `CUM_TM4` = Plan 4's binding cumulative ratio at TM4 (its ledger, Task 17 Step 6). It is the start value of this plan.
- **Ruling M (draft): measured on p4m `0b1dca5a`, not on the TM4 tree** — the TM4 tree does not exist yet and the controller asked for the draft now — if wrong: Task 0 Step 3 measures again on `P5BASE` and replaces the batch files and reading lists; measurement wins, with a `Ruling` per changed name.
- **Autonomy (Kadir 2026-11-20, Plans 3-6).**
  - Every "ask Kadir" or "tell Kadir" becomes a ledger entry plus a line in `kadir-notes.md`, with a `Ruling`. Nothing waits for an answer.
  - The controller pushes, opens PRs and merges under that grant. Workers never push, open PRs, merge, delete branches or force anything.
  - No force push. Never delete a branch.
  - Before a merge, check that the target tip is an ancestor of the merged branch.
  - After every push or merge, run `gh run list --repo kadirkayarr-beep/AI-DND --limit 5`. "AI-DND bounded verification" must be green before "done".
    - A red run is reported at once.
    - Before any rerun, save its `gh run view <id> --log-failed` in the ledger dir. Rerun only the failed job.
  - Real stops stay:
    - a speed limit exceeded (spec §7);
    - an irreversible or destructive action;
    - a security-sensitive action;
    - a plan so broken that every path is a guess.
- **Ruling B: cumulative speed, binding at every point.** Wherever this plan says "cumulative A/B":
  - OLD = the `TM0BASE` tree (worktree `p5o`); NEW = the tree under test. Method: Plan 4's fair A/B (below).
  - It runs at Task 0 (information; compared with `CUM_TM4`), Task 4 (binding, on the fully moved rehearsal tree), every M10b (binding), TM5 (Task 13, binding) and Task 14 (binding).
  - Ratio above 1.10 at a binding point: STOP and tell Kadir (spec §7 real stop). No retake to pass.
  - Ruling: M10b's OLD is `TM0BASE`, not the unmoved Stage A tip as in Plan 4 — the turn core is the hottest code and Plan 5 starts with the margin `CUM_TM4` has left; a stage-only ratio could pass while the cumulative one is over — if wrong: none; one series per task as before, the stage delta is still derived (NEW median against Task 0's NEW median) as information.
  - Approval §23 row 1 marks it as stricter, not a loosening.
- **Fair A/B method** (labels `<pfx>bench-warmold-off`, `<pfx>bench-warmnew-off`, `<pfx>bench-old<k>-off`, `<pfx>bench-new<k>-off`, k = 1..5, flag off, no `fon`):
  - Gate wait and foreign-load check before every run, `FSLOT` 4.
  - One warm-up each, discarded. Five pairs in the order O,N,N,O,O,N,N,O,O,N.
  - Each run: `slot.sh 4 <WT> test <label> 1800 api.tests.bench_engine_turn`. Read `TURN_BENCH median_ms_per_turn` from `target.log`.
  - Pass: median(NEW five) / median(OLD five) ≤ 1.10.
  - The absolute 23.13 / 23.25 ms limits are information only (Plan 3 G4a Ruling).
  - Every raw `RESULT` and `TURN_BENCH` line goes to the ledger, with the OLD sha and the NEW tree identity (`git rev-parse HEAD` and `git write-tree` of the staged tree).
  - A single run with `RESULT exit≠0` or no `TURN_BENCH` line is rerun once at the same position; the series is never rerun.
  - After a speed STOP: Stage A tasks may finish and commit locally; no PR, no push and no move task until Kadir's answer.
- **Ruling C: full suites.**
  - Shard timeout 4 500 s (foreign load; Plan 3 Task 17, D-448): `slot_gate.sh <FSLOT> <WT> <label> 3 4500 '.'`. Every pattern run uses 4 500 s too.
  - Suite speed is read as wall clock. The longest-shard ratio is recorded as information.
  - Limits: flag off ≤ 2 155 s (1.10 × TM0 1 959 s) and ≤ 1.10 × the mean of the two flag-off bases; flag on ≤ 1.10 × the mean of the two flag-on bases.
- **Ruling D: play gate deferred** to the end of Plan 6. TM5 writes "oynayış ertelendi (Kadir 2026-11-20)". The zero-tolerance journeys stand in: `NEIGHBOURS` in every run, plus Task 13 Step 7.
- **Ruling E: waits, long runs and continuation.**
  - No agent ever uses the Monitor tool or a background wait (`run_in_background` plus a notification).
  - Every wait is a foreground bash loop of at most 9 minutes per tool call (`sleep 60` between checks) and at most 150 minutes per agent.
  - A run that can outlive one call (pattern runs, full suites, bench series) is written into `<ledger>/run-<label>.sh` and started detached from Windows with exactly this form (Plan 4 ledger, Task 0 "method that worked"; `<ledger>` as a `/c/...` path):
    `powershell.exe -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath 'C:\Program Files\Git\bin\bash.exe' -ArgumentList '-lc','\"bash <ledger>/run-<label>.sh > <ledger>/<label>.out 2>&1\"'"`
    - The escaped inner quotes `\"...\"` are required: without them Windows PowerShell 5.1 joins the arguments unquoted, bash gets `-lc bash` and sits in an interactive shell. Plan 4 Task 10 lost two starts to that.
    - Start check: within 2 minutes `<ledger>/<label>.out` exists, and for a `slot_gate.sh` run `pgrep -af slot_gate` shows the label. Otherwise stop the stray bash processes (by pid, recorded), write it to the ledger and start once more with the form above.
    - Foreground loops poll the `.out` file for its final `PAR_EXIT=`/`RESULT`/`END` line.
  - At 150 minutes an agent returns **Status CONTINUE** with the run label, its start time and its `.out` path. The next agent polls that file. A running or finished run is never restarted.
  - **Continuation after a lost agent** (Plan 4 Task 10: a PC restart killed an agent mid-batch). The continuation agent:
    1. saves `git diff HEAD` and `git status --short` to `<ledger>/task-<N>-killed-partial.diff`;
    2. checks that no run of that task is still going (`pgrep -af slot_gate` empty; every `.out` of the task ends with a final line or is dead);
    3. restores only what M4-M6 write (M7's restore list);
    4. redoes the whole batch from M1 with labels suffixed `-r2`. A half-made move is never resumed.
- **Ruling F: test and safety.**
  - Tests run only through `slot.sh` / `slot_gate.sh`: `SLOT` 2 for targeted runs, `FSLOT` 4 for `slot_gate.sh` and benches. Slots 3 and 5 belong to others.
  - Ruling: slots 2 and 4 again — Plan 4 has finished with them at TM4 — if wrong: Task 0 Step 1 reads Plan 4's ledger end and `pgrep`; a slot in use waits.
  - Gate wait `run-gatewait.sh` before every `slot_gate.sh` call and every bench. Go only on `RC=1`, and for `slot_gate.sh` also `AVAIL_MB` ≥ 3 500. `pgrep -af slot_gate` must print nothing before any `slot_gate.sh`.
  - Never two full suites at once. No browser tests.
  - Debt rows have exactly 8 `|`. Keys and `.env` are never read. No branch deletion, no force push.
- **Foreign load (D-448).** `<ledger dir>/run-foreignload.sh` is copied unchanged from Plan 4's ledger dir. It reads CPU through the WMI class `Win32_PerfFormattedData_PerfOS_Processor` (`_Total`, 5 samples): the `typeperf` counter path fails on this Turkish Windows. It prints `FOREIGN_CPU_PCT=<n>` (-1 = read failed: fix before the series) and `NODE_PROCS=<n>`.
  - Before a bench series or a full suite, `FOREIGN_CPU_PCT` must be ≤ 25. Otherwise poll every 5 minutes for at most 35 minutes, then go and write "yük altında" next to the result (Plan 4 Ruling carried).
- **Ruling G: three stages, three PRs.**
  - Stage A (tools, identity prep, batch files, rehearsal) = PR A.
  - Stage B (moves, exam, TM5) = PR B, stacked on PR A. Stage B does not wait for PR A's merge.
  - Stage C (D-429) = PR C, cut from the Stage B tip after TM5 passes, merged after PR B.
  - Ruling: D-429 as its own stage and PR, not a last task inside PR B — the owner's trigger says "TM5 sonrası, ayrı kırmızı-yeşil para işi"; TM5's suites must prove a pure move, and a behaviour change inside PR B would make them prove both — if wrong: one more PR and one more CI run.
- **The flag.** Every targeted run happens twice:
  - flag on: label `<run>-fon`, `api.tests.gate_boot` first and `api.tests.test_engine_gate_boot` in the list;
  - flag off: label `<run>-off`, never containing the letters `fon`.
  - Labels: `p5t<task>-<batch or step>-<off|fon>`. No batch name contains `fon` (`front-1` does not: f-r-o-n-t). Never `slot.sh ... par`.
  - `F_fon` is read again in Task 0. Pass at every gate: `failing_ids 0` in both flags.
- **Behaviour pins in both flags.** A pin captured on `BASE_SHA` before a move runs in both flags, and its literal must hold in both. A pin whose value differs by flag is written as two literals with the flag named.
- **Worktrees** (one writer each; `WT` = folder name only):

  | Worktree | What | Used by |
  |---|---|---|
  | `AI-DND-k2-bolme-p5` | branch `task/game-py-bolme-p5` (this draft) | plan files only |
  | `AI-DND-k2-bolme-p5n` | branch `task/game-py-bolme-p5-nets` off `P5BASE` | Stage A |
  | `AI-DND-k2-bolme-p5m` | branch `task/game-py-bolme-p5-moves`, cut from the Stage A tip after Task 5 | Stage B |
  | `AI-DND-k2-bolme-p5c` | branch `task/game-py-bolme-p5-d429`, cut from the Stage B tip after TM5 | Stage C |
  | `AI-DND-k2-bolme-p5a` | detached at `P5BASE` | Task 0 bench |
  | `AI-DND-k2-bolme-p5o` | detached at `TM0BASE` | cumulative OLD |
  | `AI-DND-k2-bolme-p5p` | local branch `tmp/game-py-bolme-p5-prova` | rehearsal |
  | `AI-DND-k2-bolme-p5x` | local branch `tmp/game-py-bolme-ag-sinavi-p5` | exam |
  | `AI-DND-k2-bolme-p5b` | detached; the Stage A tip merged with the gate's `MAIN_SHA` | TM5 bases |

  - Ruling: a new `p5o`, not Plan 4's `p4o` — one plan never runs from another plan's worktree — if wrong: one more checkout on disk.
  - Throwaway branches are never pushed and never deleted.
- **Freeze (spec decision 3):** while PR A, B or C is open, no other branch touches `ai-dnd/game.py` or `ai-dnd/game_parts/`.
- **Run commands.**
  - Targeted run: `bash C:/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh <SLOT> <WT> test <label> 1800 <modules...> <NEIGHBOURS>`. Pass: `RESULT exit=0 Ran <n> tests`. Modules under `ai-dnd/api/tests/` are written `api.tests.<m>`; only root modules (`test_sessions`, `test_startup`, `test_shops`, `test_combat_v2_authoritative`) are bare.
  - Pattern run (more than 60 modules): `bash C:/Users/Kadir/Desktop/<WT>/ai-dnd/scripts/engine_split/slot_gate.sh <FSLOT> <WT> <label> 3 4500 '^(<b1>|<b2>|...)$'`. Pass: `PAR_EXIT=0` and `failing_ids 0`. Base names only (strip `api.tests.`, leave out `gate_boot`). Check that the printed `modules=<n>` equals the intended count; a surplus of exactly the top-level twins `test_spells_v1`/`test_xp_v1` is expected (Plan 4 Task 7 Ruling).
  - `NEIGHBOURS` = `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys`. In every targeted run.
  - `ENGINE_SET` = Plan 4's ten modules plus one: `api.tests.test_engine_parts_pilot api.tests.test_engine_routing api.tests.test_engine_surface api.tests.test_engine_patch_census api.tests.test_engine_size_budget api.tests.test_engine_hash_parts api.tests.test_engine_sources api.tests.test_engine_split_inventory api.tests.test_engine_sensitivity api.tests.test_engine_module_alias api.tests.test_engine_move_tool`.
    - Ruling: `test_engine_move_tool` joins — Task 1 changes `move_block` and every move uses it — if wrong: a few seconds per run.
- **`WTROOT`** = `/mnt/c/Users/Kadir/Desktop/AI-DND-k2-bolme-p5n/ai-dnd` in Stage A (Tasks 0-5), `.../AI-DND-k2-bolme-p5m/ai-dnd` in Stage B (Tasks 6-13), `.../AI-DND-k2-bolme-p5c/ai-dnd` in Stage C. "Slot copy" = `/root/aidnd-env-<SLOT>/src/ai-dnd` after a sync.
- **Scripts that are not tests (`SLOTPY`).** After a `slot.sh` call has synced the tree, run them with the slot's Python 3.13 as a script file: `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- bash <ledger dir>/run-<name>.sh < /dev/null`. Never `bash -c '...'` (D-351). Never Windows Python for the mover or the checker (D-358).
- **Stores.**
  - Measurement store: `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p5/` (`STORE`). It holds the draft measurement (`tree/`, `out/`) and the pre-flight re-measurement (`out-c1/`).
  - Shared worker rules: `STORE/common.md` (draft written with this plan).
  - Ledger: `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-p5n/.superpowers/sdd/2026-11-21-game-py-bolme-plan-5/progress.md`. It is local and not committed; Stages B and C append to it. `run-*.sh`, `pre-plant/`, `kadir-notes.md` and `task-<N>-report.md` live there.
  - Seconds, bench readings and `RESULT` lines are copied raw, never estimated.
  - Decisions are written as `Ruling: <karar> — <neden> — <yanlışsa maliyeti>`.
- **Red first.** Every new test is seen failing for the stated reason before the change.
  - A guard that is green on a clean tree is shown red with a planted fault, then restored with Plan 3's pre-plant rule: copy the file and its sha256 to `pre-plant/`; plant; run; copy back; check the sha256 and that `git diff HEAD --stat` is unchanged.
  - A test that is meant to be red but is green on its first run becomes a guard: show it red with a planted fault, keep it, and write a `Ruling`. A red is never forced.
  - New tests that start a campaign or a session use `fixed_town(self, <seed>)`, seeds `20261401` and up, one per test (ranges per task below).
- **Old-behaviour tests** are rewritten only with equal or greater strictness. Each rewrite gets a row in `docs/agents/onay-listesi-20261115.md` §23 (`Test | Değişiklik | İşaret`).
  - Ruling: a new section "## 23. game.py bölme Plan 5 (dal `task/game-py-bolme-p5-nets`)", as Plans 3 and 4 opened §21 and §22; Task 0 Step 8 creates it — if wrong: a heading.
  - A moved boundary is marked "gevşetme olabilir". Unmarked loosening, skipping or deleting stops the work.
- **Findings** go to `docs/agents/debt-register.md`, ids `D-470..D-489` (Plan 4 holds `D-450..D-469`). Before each push, read the highest id on `origin/main` and on open branches.
- **Review tiers.** Every task has an Opus implementer, or an Opus runner for Tasks 0, 4 and 12. Every committed change gets an independent Opus review on a `git archive <sha>` copy, and the reviewer reruns M7 itself.
  - "strong" = money/save/death/Undo reading, `move_check --tier strong`, and the reviewer runs M12.
  - Strong: Tasks 1, 2, 5, 6-11, 13, 14. Task 3 is reviewed by Opus with net scope.
  - Ruling: Task 1 (a tool) is strong — it decides which identity uses may leave `game.py` inside turn code — if wrong: one stronger review than needed.
  - The fable model is never used (owner rule 2026-11-14).
- **Speed rule 1 (overlapping review)** applies only in Stage A. Order: Task 1, Task 2, Task 3. The next implementer may start while the previous task is reviewed (Task 2 during Task 1's review, Task 3 during Task 2's review); their code and test files are disjoint. The one shared file is the approval list (Task 1 row 2, Task 3 row 4): Task 3 writes §23 only after Task 1's review and its fix wave are closed. Stage B runs strictly one task after another.
- **Tools.** Stdlib only in CI. Forbidden: `ast.unparse`, formatters, `ruff --fix`, `ruff format`, rope, libcst codegen, import-linter, desloppify.
  - Moved source is edited in place only, and never by hand inside a move. The identity edit is its own commit before the moves (Task 2), so every move stays pure.
  - `sensitivity.py --write` is never run. `sensitive.json` grows only by hand under a strong review and never shrinks.
- **Centre rule (spec §4).** A part never calls another engine function or class bare; it writes `game.X` (R9). A part constant read by the same part stays bare. No sibling-part imports, no `from game import`. Only `game.py` imports `game_parts.*`.
- **Never moved** (`move_block.NEVER_MOVED`, 18 names), plus the two names of Ruling I: `_restore_in_place`, `_dynamic_engine_transitions`. They are left out of the batch files; `NEVER_MOVED` itself does not change.
- **Ruling H (revised after pre-flight C1): two parts; `turn.py` holds spec §5's core and is frozen once, at arrival.**
  - Spec §5 gives `turn.py` one content: "`_dispatch_player_turn`, anahtarlı tur, `_run_player_turn_internal` (bütün hâlde)", about 3 900 lines. Spec §11: "her parça ≤ 2 500; `turn.py` ve `narration_safety.py` geldikleri boyutta dondurulur, yalnız küçülebilir."
  - `turn.py` (16 names, 3 974 lines, about 4 020 with header and separators): `_run_player_turn_internal`, `_dispatch_player_turn`, `_dispatch_turn_body`, `run_player_turn`, `_run_player_turn_owned`, `_run_player_turn`, `_run_player_turn_keyed`, `turn_source_key`, `_spoken_rest_of_turn`, `_current_procedural_entity_ids`, `_keep_town_portrait`, `_narrate_resolved_turn`, `_owner_module_reply`, `ResolvedTurn`, `TurnResolved`, `DEBUG_MODE` (`batches5.py` `CORE`).
  - `turn_front.py` (51 names, 2 179 lines, about 2 255 with header and separators): every other T6 name (front gates, thread, coin and intent-execution helpers, refusal and place turns). A normal part: `part_max` 2 500, no `files` entry.
  - `turn.py` alone stays over 2 500. The spec allows exactly that: §11 freezes `turn.py` at its arrival size instead of `part_max`. `size_budget.json` does it with a `files` entry. The entry is created once, in `turn-3` (Task 11), at the real size when `_run_player_turn_internal` arrives; before that `turn.py` is about 1 260 lines and needs no entry. After `turn-3` it only goes down.
  - Karar 10: creating a number above `part_max` counts as raising it. One approval §23 row (row 5) and one `kadir-notes.md` line: "turn.py <n> satırla geldi (tasarım 3 900 demişti), spec §11 gereği geldiği boyutta donduruldu; turn_front.py <m> satır, normal 2 500 sınırında."
  - Ruling: the name `turn_front.py` — it holds what the turn calls before and around the dispatch (the "front" gates and steps), it sorts next to `turn.py`, and it is the name the draft and the pre-flight review already used — if wrong: a rename is one pure move of one file plus its re-export lines.
  - Ruling: move order `front-1..3`, then `turn-1`, `turn-2`, `turn-3` (`_run_player_turn_internal` last) — `turn.py`'s frozen entry is then created once at its real size; `turn_front.py` is whole before the core lands; D-429's `_coin_without_a_reading` lands in a non-frozen part — if wrong: only the review order changes (every call goes through `game.X`).
- **Ruling I: two `turn` names stay in `game.py`.** `_restore_in_place` (sensitive, Undo) and `_dynamic_engine_transitions` are read inside `game.py` only by `GameSession`, which never moves (appendix C, `batches5.py` `STAY`).
  - This is the misfit rule (a name follows its only callers) applied to never-moved code. `plan4_map.py`'s call graph does not see `GameSession`'s methods.
  - It also keeps spec §5 "Geri Al anlık görüntüsü dokunulmadan kalır": Undo's in-place restore stays next to `GameSession.restore`.
  - If wrong: 78 more lines to move in Plan 6. They are not what keeps `game.py` over 1 500 (appendix I).
- **Ruling J: identity names (spec §7).**
  - `sys.modules[__name__]` is used twice in turn code: `_local_place_turn` (to `arrival_narration.arrive`) and `_run_player_turn_internal` (to `heard_rumours.record_mention`). After a move, `__name__` would name the part: these calls would get the part, not the engine.
  - Task 2 changes both to `sys.modules["game"]` in `game.py`, in its own commit, with pins first. It is behaviour-neutral: these functions run only in the module `game` (`python game.py` hands over to `import game`; spec T1).
  - Spec §7 says "→ `game`". Ruling: `sys.modules["game"]` keeps the moves pure (no hand edit inside a move) and names the engine module, which is what the spec's edit is for — the literal `game` would need an R12 allowlist row and a hand edit inside a moved span, which `move_check` cannot see (Plan 4 Task 9 note) — if wrong: a one-line edit per site in Plan 6, each with its own pin.
  - `locals().get("preparsed_scene_intent")` in `_run_player_turn_internal` stays as it is (spec §7). A function's `locals()` holds its own locals in any module.
  - `move_block` refuses `sys.modules` and `locals(` (N3 rule 6), and R6 flags them in a part. Task 1 lets `move_block` accept exactly the uses that an `identity_allowlist.json` row names. The rows are added in the move commit that needs them: `front-1` (`game_parts/turn_front.py`, `_local_place_turn`, `sys.modules`), `turn-3` (`game_parts/turn.py`, `_run_player_turn_internal`, `sys.modules` and `locals`).
- **Ruling K: `turn-3` is over CAP.** It is one function of 2 756 lines; spec T6.2 moves it whole ("bütün hâlde"). Plan 3's `nsafety-2` (1 054) is the precedent. If wrong: nothing smaller exists without editing the function.
- **Ruling L (pre-flight C2): `ResolvedTurn` moves with its `@dataclass` decorator** — `dataclass` is a stdlib decorator, not an engine name (N3 rule 4 concerns engine names); the decorator line is part of the moved block; `turn-1`'s header gets `from dataclasses import dataclass` only (M5 rule: list only the names read; `field` is not read) — if wrong: `move_block` refuses or M7 reports `CHANGED` in Task 4's rehearsal, and `ResolvedTurn` is held with a Ruling (it is 23 lines). This is the only decorated name in the move set (`p5_checks.py` `decorated 1`); no earlier part moved a decorated top-level name.
- **Every implementer brief carries:**
  - `docs/agents/implementer-preamble.md`;
  - `STORE/common.md`;
  - the graphify rule: run `graphify query "<question>"` (cwd = the main repo folder `C:/Users/Kadir/Desktop/AI - DND`; the graph is stale for line numbers) before the first grep or source read; read raw files only for lines the graph or an earlier read located; `graphify update .` once at the end, only where `graphify-out` is ignored;
  - "a move task changes nothing else";
  - "the prefix is added in place; source is never regenerated";
  - function and file names, never line numbers;
  - "`game.py` is about 8 300 lines at Plan 5 start, `turn_front.py` grows to about 2 255 and `turn.py` to about 4 020: never read any of them whole";
  - the superpowers skills to load: `test-driven-development`, `verification-before-completion`.

## Move procedure (binding for Tasks 6-11; Plan 3's M1-M12 with Plan 4's deltas and these, given to every move brief word for word together with Plan 3's and Plan 4's text)

Definitions:
- `B` = batch, `P` = the batch's part: `turn_front.py` for `front-*`, `turn.py` for `turn-*`.
- `NAMES` = `WTROOT/scripts/engine_split/batches/<B>.txt` (written in Task 3).
- Labels `p5t<N>-<B>-<off|fon>`. `STORE` is Plan 5's.

- **M2 (as Plan 4).** Every name in `NAMES`: not in `NEVER_MOVED`, not `_restore_in_place` or `_dynamic_engine_transitions`, still top-level in `game.py`, in file order. Sensitive names move; the batch note's count must match `sensitive.json` (appendix D, column S). Surprises (decorator other than `ResolvedTurn`'s `@dataclass` under Ruling L, non-constant default naming an engine name, module-level mutation, top-level `if`/`try`, identity name without an allowlist row) → hold the name and write a `Ruling`.
- **M3** as Plan 3. Behaviour pins are captured on `BASE_SHA` before the move, in both flags.
- **M4 (changed).** In `front-1` and `turn-3`, first add the batch's rows to `api/tests/engine_split_locks/identity_allowlist.json` (exact `file`, `function`, `name` as R6 reports them; `reason` names spec §7 and this plan). Then run the mover with `--identity-allowlist WTROOT/api/tests/engine_split_locks/identity_allowlist.json` (Task 1). The other batches pass the flag too; they need no row. `REFUSED` on any other identity use: hold, `Ruling`.
- **M5 (changed).** Header per appendix D. A multi-name `from X import (...)` keeps its form and lists only the names read (Plan 3's M5 Ruling): `turn-1` lists `Any, Dict, List, Optional` from `typing`, `dataclass` from `dataclasses` (Ruling L) and `resolution_action_scope` from `api.core_resolution`; no other batch reads a `from X import` name.
  - **Never reorder the existing header.** From `front-2` on (`turn_front.py`) and from `turn-2` on (`turn.py`), `P` already has a header: keep every existing line where it is and add each new import line after the last existing import line, spelled as `game.py` spells it. M7 rejects a reordered header (Plan 4 lesson).
- **M6 (changed).**
  - `_PART_MODULES` gains `"game_parts.turn_front"` in `front-1` and `"game_parts.turn"` in `turn-1`, sorted.
  - `size_budget.json`: `files["game.py"]` = the new real size; `files["game_parts/turn.py"]` only in `turn-3`, at its real size (Ruling H); long-function keys move from `game.py::<name>` to `game_parts/<P>::<name>` with the value unchanged (`_execute_intent_internal` 548 to `turn_front.py` in `front-1`, `_front_step` 235 to `turn_front.py` in `front-2`, `_dispatch_player_turn` 493 to `turn.py` in `turn-1`, `_narrate_resolved_turn` 351 to `turn.py` in `turn-2`, `_run_player_turn_internal` 2 756 to `turn.py` in `turn-3`).
  - `identity_allowlist.json` rows as M4.
- **M7:** `move_check.py ... --tier strong` always. Expected `CHANGED 0`, no `--manual` entry other than the `_PART_MODULES` pair, and `COMMENTS base=<C> now=<C>` with `<C>` measured in Task 0.
- **M8, M9** as Plan 3. `routing_audit.py` → `clean` (the allowlist rows are used, none is unused). M9's `PROBE ok parts=` lists `game_parts.turn_front` from `front-1` on and `game_parts.turn` from `turn-1` on.
- **M10 (as Plan 4).** Module list = `ENGINE_SET` + `SLOTPY inventory.py --touching <NAMES>` (measured about 398 for the whole set: always a pattern run) + the task's named modules + `STORE/writer-tests-<B>.txt` + `NEIGHBOURS`, in both flags.
  - In the flag-on run, `test_the_fon_token_turns_the_flag_on_inside_the_child` reads `ok`.
  - Every money, save, death or Undo test the task names is unchanged since `BASE_SHA` (`git diff --quiet BASE_SHA -- <files>`) and green in both flags.
  - Off and fon runs may be chained in one detached driver, each with its own gate wait, `pgrep` check and foreign-load line (Plan 4 Task 9 Ruling).
- **M10b (every task, after its batch; changed): cumulative A/B,** OLD `p5o` (`TM0BASE`), NEW the `p5m` working tree, prefix `p5t<N>cum`. Above 1.10 → STOP (Ruling B). Record the stage delta as information.
- **M11** commit: one batch, one commit. M11 may come before M10b (Plan 4 Task 7 Ruling); a speed stop then leaves the commit local and unpushed.
- **M12 (as Plan 4: a reading list).** The reviewer runs `SLOTPY <M3>/writer_scan.py <ARCH> <ARCH>/ai-dnd/scripts/engine_split/batches/<B>.txt`.
  - Pass: `missing=0`; the set of `HELD` names equals `STORE/writer-expected-<B>.txt` (Task 3) exactly; exit code 1 when that file is non-empty.
  - The comparison script reads the **name** column: a `HELD` line is `HELD <batch> <name> <writer kinds> hops=<n> <path>`, so the name is awk `$3`, never `$2` (the batch; Plan 4 lesson).
  - The reviewer reads every `HELD` path's writer in the moved code and confirms that the test in `STORE/writer-tests-<B>.txt` for that writer kind is in the task's M10 list and green.
  - A `HELD` name not in the expected file is a new writer reach: hold it, `Ruling`, debt row.

## Review Focus

These are failure modes the spec implies but no listed check exercises. Each is pinned to a test or gate step in the task named.

1. **The turn gets slower.** The whole turn core starts reading `game.X` (about 50 `_session()` reads alone in the moved set), and the cumulative margin left at TM4 is all Plan 5 has. Pinned by the cumulative A/B in Task 4, every M10b and Task 13, and by Plan 4's `test_reading_an_engine_name_through_the_module_runs_no_python_code` in `ENGINE_SET`.
2. **Arrival narration or heard rumours get the part instead of the engine.** `sys.modules[__name__]` would name the part after the move. Pinned by `test_a_local_place_turn_hands_the_game_module_to_arrival` and `test_heard_rumours_gets_the_game_module_from_the_turn` (Task 2, with a planted wrong module there), their planted red after `front-1` and `turn-3` (Tasks 6, 11), and Task 12 Fault 2.
3. **A failed turn is not rolled back.** `_run_player_turn_owned` and `_run_player_turn_keyed` snapshot and restore through `GameSession` from the part; `_restore_in_place` stays with `GameSession`. Pinned by `test_a_failed_turn_rolls_back_from_the_part` (Task 9), `test_the_undo_restore_stays_with_the_session` (Task 3), the Undo modules in every M10 list and Task 12 Fault 3.
4. **The production narrative adapter does not reach the moved turn.** `_narrate_resolved_turn` calls `ask_dungeon_master` and `finalize_narration`, which `install_narrative_context_adapter` rebinds. Pinned by `test_the_narrative_adapter_reaches_the_moved_narrate_turn` (Task 10) and Task 12 Fault 4.
5. **Money in the front binds the wrong session.** `_tell_the_coin`, `_the_rest_of_the_line` and `_sleep_after_walk` are called with `session=` by the money tests (appendix F). Pinned by `test_turn_money_helpers_use_the_given_session` with inputs only the given session has (Tasks 7, 8), `test_coin_writers` unchanged and green, and Task 12 Fault 5.

---

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `ai-dnd/scripts/engine_split/move_block.py` (`move`, `prefix_names`, `_Scan`, `main`) | identity uses allowed by an allowlist row | 1 |
| `ai-dnd/api/tests/test_engine_move_tool.py` | its tests | 1 |
| `ai-dnd/game.py` (`_local_place_turn`, `_run_player_turn_internal`, one expression each) | `sys.modules["game"]` | 2 |
| `ai-dnd/api/tests/test_engine_parts_pilot.py` | identity pins (2), membership, behaviour, session, rollback and adapter tests (6-11) | 2, 6-11 |
| `ai-dnd/scripts/engine_split/batches/{front-1,front-2,front-3,turn-1,turn-2,turn-3}.txt` (new) | batch lists (appendix D) | 3 |
| `ai-dnd/api/tests/test_engine_surface.py` | `test_t6_batches_are_movable`, `test_the_undo_restore_stays_with_the_session` | 3 |
| `ai-dnd/game_parts/turn_front.py` (new) | the turn's front: gates, thread, coin, intent-execution, refusal and place turns | 6-8, 14 |
| `ai-dnd/game_parts/turn.py` (new) | spec §5's turn core, frozen at arrival | 9-11 |
| `api/tests/engine_split_locks/{surface,size_budget,identity_allowlist}.json` | locks per batch | 6-11 |
| `ai-dnd/api/tests/test_engine_size_budget.py` (`test_long_functions_cannot_grow_or_appear`) | its literal key follows the move | 11 |
| `ai-dnd/api/tests/test_d429_coin_without_a_reading.py` (new) | D-429 | 14 |

Batches come from measurement (appendix A, D): the topic map, the misfit rule (with Ruling I), the two targets (Ruling H), CAP 1 000 (Ruling K).
- One task per batch. Ruling: six tasks, not one task per part as Plan 4 grouped — each batch is up to about 1 000 lines of turn code (31 of 67 names sensitive), each needs two pattern runs of about 20 minutes and a bench series; one batch per task keeps each review readable and each agent under 150 minutes — if wrong: six reviews instead of two or three.

---

# Stage A — tools, identity prep, batch files and rehearsal (worktree `AI-DND-k2-bolme-p5n`, PR A)

Only Task 2 changes `ai-dnd/game.py`, and only two expressions.

### Task 0: Open the stage, measure again

**Review tier:** none (Opus runner). Its commit is read by the G6a review.

- [ ] **Step 1: Precondition.**
  - `git fetch origin`. Plan 4's ledger ends with "TM4 geçti"; Plan 4's PR B is merged (`git merge-base --is-ancestor <Plan 4 Stage B tip> origin/main`). `P5BASE` = `origin/main`; write its sha. Read `CUM_TM4` from Plan 4's ledger.
  - `pgrep -af slot_gate` empty and no Plan 4 run on slots 2 and 4.
  - Write `STORE/F_fon.txt` from Plan 4's end state (empty if none).
- [ ] **Step 2: Worktrees and ledger.**
  - `git worktree add ../AI-DND-k2-bolme-p5n -b task/game-py-bolme-p5-nets <P5BASE>`; `--detach ../AI-DND-k2-bolme-p5a <P5BASE>`; `--detach ../AI-DND-k2-bolme-p5o 2e576967dda2fbfdf6a47d22d9313fbc76c195f8`.
  - Bring the plan into `p5n`: `git checkout task/game-py-bolme-p5 -- docs/superpowers/plans/2026-11-21-game-py-bolme-plan-5.md docs/superpowers/plans/2026-11-21-game-py-bolme-plan-5-appendix.md docs/superpowers/plans/2026-11-21-game-py-bolme-plan-5-measure`.
  - `docs/design/INDEX.md`: bring only this branch's one added line, never the whole file (`P5BASE` may hold newer INDEX lines from Plan 4): `git diff 45d2c690 task/game-py-bolme-p5 -- docs/design/INDEX.md | git apply`. Check: `git diff P5BASE -- docs/design/INDEX.md` shows exactly one added line and no removed line.
  - Create the ledger. Copy Plan 4's `run-gatewait.sh` and `run-foreignload.sh` unchanged.
- [ ] **Step 3: Measure again (Ruling M).** Appendix A steps 1-7 on a `git archive P5BASE` copy under `STORE/tree/p5base`, WSL Python, outputs to `STORE/out-p5base/`. The scripts are the fixed ones (`p5_checks.py` sees class decorators; `batches5.py` cuts two targets and counts decorator names as read). Compare with the draft (`-measure/out/`):
  - equal names in every batch and lines within ±5 % → "appendix holds";
  - otherwise measurement wins: replace `-measure/batches/*.txt`, `-measure/writer-expected/*` and `-measure/out/*` with the new outputs, with a `Ruling` per changed name;
  - a batch over 1 000 lines other than `turn-3` is cut again by `batches5.py`; a new `STAY` name gets a Ruling I line; a new decorated name is held (M2);
  - a name inside a top-level `if`/`try` (D-363) is held.
- [ ] **Step 4: Locks on `P5BASE`** (Plan 4 Task 0 Step 3 routine, in `p5n`): targeted `p5t0-base-off`/`-fon` with `ENGINE_SET` + `NEIGHBOURS`: `RESULT exit=0` twice; `surface.py --write`, `patch_census.py --write --lock STORE/census-p5base.json`, `wc -l game.py`, `move_check.py --comments-only` (gives `<C>`), `classify_all.py`. Expected: `cmp` equal with the committed locks; `wc -l` equal to `size_budget.json`; classify `DIFF not_in_lock=0`. Any difference: trace its commit, debt row, fix the lock in Task 3.
- [ ] **Step 5: OLD tree and detached smoke.**
  - `slot.sh 4 AI-DND-k2-bolme-p5o test p5t0-oldtree-off 1800 api.tests.bench_engine_turn`: `RESULT exit=0` and a `TURN_BENCH` line, or STOP (the cumulative rule cannot be checked).
  - Gate wait; write `run-p5t0-detach-off.sh` with `slot_gate.sh 4 AI-DND-k2-bolme-p5n p5t0-detach-off 3 4500 '^(test_engine_sources|test_engine_hash_parts)$'`; start it detached with Ruling E's exact form; the start check passes; poll; expected `PAR_EXIT=0`, `modules=2`.
  - `run-foreignload.sh` once: `FOREIGN_CPU_PCT=<0..100>`, `NODE_PROCS=<n>`.
- [ ] **Step 6: Speed base.** Cumulative A/B, OLD `p5o`, NEW `p5a`, prefix `p5t0cum` (information). Record it next to `CUM_TM4`. A reading above 1.10 here is not a stop, but it is written to `kadir-notes.md` at once: the stage cannot pass Task 4 without an improvement.
- [ ] **Step 7: Debt bookkeeping** (ledger only; Stage A never edits `debt-register.md`): read every row whose trigger names Plan 5, T6 or TM5 (Plan 4's D-450..D-469 included) and add it to this plan's table in the ledger with its task. D-349's "rest → Plan 5 Görev 0": run the recheck of Task 3 Step 4 here and write its result as a ledger line; the register row is updated in Task 13 Step 8.
- [ ] **Step 8: Approval list and commit.** Create "## 23. game.py bölme Plan 5 (dal `task/game-py-bolme-p5-nets`)" in `docs/agents/onay-listesi-20261115.md` with rows 1, 8 and 9 (table "Approval list §23 rows"). **Commit** `game.py split plan 5: plan, appendix and measure scripts (measured again on P5BASE)`.

### Task 1: `move_block` moves an identity use that an allowlist row names (Ruling J)

**Review tier:** strong (Opus implementer, Opus review). Code and test files are disjoint from Tasks 2 and 3; the approval list is shared with Task 3 (Speed rule 1).

**Files:**
- Modify: `ai-dnd/scripts/engine_split/move_block.py` (`_Scan`, `prefix_names`, `move`, `main`), `docs/agents/onay-listesi-20261115.md` §23 (row 2)
- Test: `ai-dnd/api/tests/test_engine_move_tool.py`

**Interfaces — Produces:**
- `move(game_py, part_py, names, surface_targets, identity_allow=frozenset())`; `prefix_names(block, engine_names, keep_bare, identity_allow=frozenset(), part_rel=None)`.
- `identity_allow` is a set of `(file, function, name)` tuples read from `identity_allowlist.json`, the same key R6 uses (`routing_audit` `ctx["allow"]`). `name` is `"locals"` or `"sys.modules"`.
- A `locals(`/`sys.modules` use inside a def is accepted when `(part_rel, <function>, <name>)` is in `identity_allow`, where `<function>` is the value R6 reports for that use (measure it with a fixture; do not guess). It moves unchanged. Every other N3 rule-6 refusal stays: `__name__`, `__file__`, `globals(`, `vars(`, and any unlisted use.
- CLI: `--identity-allowlist <path>` (optional; absent = today's behaviour).

- [ ] **Step 1: Tests (red today):**

```python
def test_move_block_moves_an_allowlisted_locals_call(self):        # MoveRefused today
    # fixture game.py with def f(): x = 1; return locals().get("x"); row (game_parts/p.py, f, locals)
    # -> MOVED, the part holds `locals().get("x")` unchanged
def test_move_block_moves_an_allowlisted_sys_modules_read(self):   # MoveRefused today
    # def f(): return sys.modules["game"]; row (game_parts/p.py, f, sys.modules) -> moved unchanged
def test_move_block_still_refuses_an_unlisted_locals_call(self):   # guard: green today
def test_move_block_refuses_a_row_for_another_part_or_function(self):  # guard
def test_move_block_still_refuses_dunder_name_even_with_a_row(self):   # guard: row (…, f, "__name__") does not help
```

  Run `api.tests.test_engine_move_tool` + `ENGINE_SET` + `NEIGHBOURS` (`p5t1-red-off`, `p5t1-red-fon`): only the first two fail, with `MoveRefused`.
- [ ] **Step 2: Implement.** Thread `identity_allow` through `_Scan`; read the file in `main`. Run again (`p5t1-off`, `p5t1-fon`): `RESULT exit=0`. Show each guard red once with a planted fault (pre-plant rule): accept every `locals(` → the unlisted guard goes red.
- [ ] **Step 3:** §23 row 2. **Commit** `game.py split plan 5: move_block moves an identity use that identity_allowlist.json names (spec §7, Ruling J)`.

### Task 2: The two `sys.modules[__name__]` uses name the engine (Ruling J)

**Review tier:** strong. This is turn code: arrival narration and remembered names, inside the turn that holds Undo.

**Files:**
- Modify: `ai-dnd/game.py` (`_local_place_turn`, `_run_player_turn_internal`: one expression each)
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py` (seeds `20261401`-`20261409`, one per test)

- [ ] **Step 1: Measure the shapes** (`SLOTPY` script on the `p5n` slot copy; graphify "test that walks into a local place and checks arrival narration", "test_heard_rumours_turn D-249 record_mention", "which turn input reaches _validated_local_person_proposal with preparsed_scene_intent"). Write in the ledger: the inputs that reach each of the three sites, in both flags.
- [ ] **Step 2: Pins (green on the Task 2 base, both flags):**

```python
def test_a_local_place_turn_hands_the_game_module_to_arrival(self):
    # patch.object(arrival_narration, "arrive", wraps=arrival_narration.arrive); walk into a local place (Step 1 input)
    # -> called once; call.args[0] is game
def test_heard_rumours_gets_the_game_module_from_the_turn(self):
    # patch.object(heard_rumours, "record_mention", wraps=...); the D-249 turn (Step 1 input) -> args[0] is game
def test_a_preparsed_local_person_reaches_the_turn(self):
    # the locals().get("preparsed_scene_intent") branch (Step 1 input): pin the resulting action and person id as literals
```

  If Step 1 finds no input that reaches the `locals()` branch: `Ruling` plus a ledger park (the register row is written in Task 13 Step 8), and the third pin asserts what is measurable (the branch's guard value for the closest input). Never skip it silently.
- [ ] **Step 3: Red proof before the edit** (pre-plant rule): in `game.py`, replace `sys.modules[__name__]` with `sys.modules["json"]` in `_local_place_turn` → the arrival pin red; restore, sha256; the same in `_run_player_turn_internal` → the heard-rumours pin red; restore, sha256. Both pins discriminate before G6a.
- [ ] **Step 4: Edit** both expressions to `sys.modules["game"]`. Run the pins + `ENGINE_SET` + `NEIGHBOURS` + `api.tests.test_arrival_wiring api.tests.test_arrival_narration api.tests.test_heard_rumours_turn api.tests.test_heard_rumours api.tests.test_local_place_travel` in both flags (`p5t2-off`, `p5t2-fon`): `RESULT exit=0`. `SLOTPY outside_probe.py` → `PROBE ok` (its `python game.py` turn).
  - The edit itself is behaviour-neutral (Plan 4 Task 9 Ruling); after `front-1` and `turn-3`, `sys.modules[__name__]` planted back in the part must turn the first two pins red again.
- [ ] **Step 5: Commit** `game.py split plan 5: turn code names the game module explicitly (spec §7, before T6)`.

### Task 3: Batch files, T6 movable test, Undo restore stays, writer reading lists

**Review tier:** Opus implementer, Opus review (net scope). The review checks the batch lists against measurement.

**Files:**
- Create: `ai-dnd/scripts/engine_split/batches/{front-1,front-2,front-3,turn-1,turn-2,turn-3}.txt` (from `-measure/batches/`)
- Modify: `ai-dnd/api/tests/test_engine_surface.py`, `docs/agents/onay-listesi-20261115.md` §23 (row 4; only after Task 1's review and fix wave are closed)

- [ ] **Step 1: Tests:**
  - `test_t6_batches_are_movable`: `self._batches_are_movable(T6_BATCHES, sensitive_allowed=True)`, `T6_BATCHES = {"front-1": "turn_front", "front-2": "turn_front", "front-3": "turn_front", "turn-1": "turn", "turn-2": "turn", "turn-3": "turn"}` (red: no batch files). §23 row 4.
  - `test_the_undo_restore_stays_with_the_session`: `_restore_in_place` and `_dynamic_engine_transitions` are top-level in `game.py` (`top_level_index`), in no batch file, and `game._restore_in_place.__module__ == "game"`. Green today; planted red: add `_restore_in_place` to `turn-2.txt`.
- [ ] **Step 2:** Write the six files from `-measure/batches/` (after Task 0 Step 3). Run `SLOTPY <M3>/writer_scan.py WTROOT/.. <batch>` per batch: `missing=0`; the `HELD` set equals `-measure/writer-expected/writer-expected-<B>.txt`; copy it to `STORE/writer-expected-<B>.txt`. For each writer kind in it, name one existing test that drives that writer through a batch name in `STORE/writer-tests-<B>.txt` (graphify per writer; the draft's `HELD` paths are in `-measure/out/writer-scan.out`).
- [ ] **Step 3:** `SLOTPY inventory.py --touching` per batch into `STORE/touching-<B>.txt`; record the counts (draft: 398 for the whole `turn` set).
- [ ] **Step 4: D-349 recheck** over the 67 names (the `p5_checks.py` output): `builtins.eval/exec`, `__builtins__.open`, the two-step chain, `getattr(<module>, "uuid4")`, an assignment-bound function, a missing `__init__.py`, an import-time `game.X`. Draft: none; 145 in-function imports, none of `game` or `game_parts`. Write the result as a ledger line (the register row is updated in Task 13 Step 8).
- [ ] **Step 5:** Run `api.tests.test_engine_surface` + `ENGINE_SET` + `NEIGHBOURS` (`p5t3-off/-fon`): `RESULT exit=0`. **Commit** `game.py split plan 5: T6 batch files, T6 movable test, Undo restore stays with the session`.

### Task 4: Rehearsal — the whole T6 move on a throwaway branch

**Review tier:** none (Opus runner; nothing reaches a plan branch). Worktree `p5p`, branch `tmp/game-py-bolme-p5-prova`, from the Stage A tip; local commits allowed, one per batch.

- [ ] **Step 1: Move everything.** For `front-1`, `front-2`, `front-3`, `turn-1`, `turn-2`, `turn-3`: M4 (with the allowlist rows), M5, M6 bookkeeping, M7 per batch against its parent commit (`CHANGED 0` expected). Every `REFUSED`, header gap or unexpected R6 key goes to the ledger as a hold or a tool gap.
  - Record for `ResolvedTurn` (Ruling L): `move_block` kept the `@dataclass` line inside the moved block, `turn.py`'s header has `from dataclasses import dataclass`, and M7 reports `CHANGED 0` for it.
  - Record both part sizes after each batch; `turn.py` before `turn-3` must stay under 2 500.
- [ ] **Step 2: Static and outside checks.** `routing_audit.py` → `clean`; `outside_probe.py` → `PROBE ok` listing `game_parts.turn_front` and `game_parts.turn`; `test_engine_size_budget` with the `turn.py` entry; targeted `test_sessions test_startup api.tests.test_narrative_director` + the Task 2 pins + `NEIGHBOURS`, both flags. Plant `sys.modules[__name__]` in `turn_front.py`'s `_local_place_turn`: the arrival pin goes red; restore.
- [ ] **Step 3: Speed (binding).** Cumulative A/B, OLD `p5o`, NEW `p5p`, prefix `p5t4cum`. Above 1.10 → STOP before Stage B, tell Kadir.
- [ ] **Step 4: Feed back.** Each finding becomes a hold or a red-first tool fix on `p5n` (commit `game.py split plan 5: holds found by the rehearsal`). Ledger line "prova: <n> red, <m> tutuldu, kümülatif <ratio>, turn_front <x>, turn <y> satır".

### Task 5: Gate G6a — Stage A review, PR A

**Review tier:** strong (whole-branch review on Opus). It reads Task 1's tool, Task 2's edit and pins.

- [ ] **Step 1:** `git fetch origin`. If `origin/main` moved: merge it, rerun Tasks 1-3's modules + `ENGINE_SET` + `NEIGHBOURS` in both flags; if `game.py` changed, repeat Task 0 Step 3 and Task 4 Step 3. These reruns are binding.
- [ ] **Step 2: Whole-branch review** of `$(git merge-base origin/main HEAD)..HEAD`. One fix wave, red-first (Opus); scoped re-review (Opus). Remaining minors become ledger parks for Task 13 Step 8.
- [ ] **Step 3: Checks without a suite:** `outside_probe.py` → `PROBE ok`; `python test_regression.py` → `Results: 30 passed, 0 failed out of 30`; `routing_audit.py` → `clean`; ruff once (`--select F821,F401,F811 --no-fix`).
- [ ] **Step 4:** Recheck the free debt ids. Push and open PR A (text: the speed numbers, the rehearsal line, the identity Rulings). CI rules. Ledger line "G6a geçti". Cut `p5m`: `git worktree add ../AI-DND-k2-bolme-p5m -b task/game-py-bolme-p5-moves task/game-py-bolme-p5-nets`.

---

# Stage B — T6 moves (worktree `AI-DND-k2-bolme-p5m`, PR B)

Each task is a pure move under the Move procedure. Every task is strong: every batch holds money, Undo or death writers (appendix E). Named modules below are added to the M10 list; most are already in the touching set, and naming them makes the reviewer's "unchanged and green" check explicit.

`UNDO` = `test_lr00_p7_undo test_d110_undo_after_lost_ack test_economic_undo test_undo_names_turn test_d112_ironman_undo test_d162_undo_status_contract`.
`DEATH` = `test_death_system test_real_death test_dilim4a_death_audit test_death_bounded test_d113_death_checkpoint_format test_d145_species_rest_death` (all exist at `0b1dca5a`; named where a batch holds death writers: Tasks 7, 8, 9, 11).

### Task 6: `turn_front.py` — batch `front-1` (13 names, 970 lines, 6 S) (spec T6.1)

**Content:** `_has_session`, thread turns (`_carry_out_thread_turn`, `_thread_gate`), `_world_snapshot`, `_changed_state_fields`, `_execute_intent_internal`, adventure and everyday turns (`_hideout_check`, `_adventure_scene_turn`, `_adventure_check_reply`, `_everyday_action_turn`), `_local_place_turn`, `_intent_infrastructure_result`, `_clear_turn_transients`. Sensitive: `_carry_out_thread_turn`, `_thread_gate`, `_world_snapshot`, `_changed_state_fields`, `_execute_intent_internal`, `_clear_turn_transients`.

**Files:** Create `ai-dnd/game_parts/turn_front.py`; modify `ai-dnd/game.py`, `surface.json`, `size_budget.json`, `identity_allowlist.json` (one row); test `test_engine_parts_pilot.py` (`test_both_import_orders_work_in_a_fresh_interpreter` and the wrapper-filter tuple test gain `turn_front`, §23 row 7).

**Batch notes:**
- `_has_session` (2 lines; only callers in `game_parts/dialogue.py`) moves as measured. Ruling: topic `turn` kept, not the misfit target `dialogue` — the misfit rule saw only `game.py`, and moving it into a Plan 3 part widens this plan — if wrong: one name in another part later.
- `_thread_gate`, `_adventure_scene_turn`, `_local_place_turn`, `_clear_turn_transients` are census targets. Long function `_execute_intent_internal` key moves.

- [ ] **Step 1: Tests** (seeds `20261410`-`20261419`):
  - `test_front_1_lives_in_the_part` (red).
  - `test_a_patched_thread_gate_reaches_its_moved_caller`: `patch.object(game, "_thread_gate", wraps=...)` sees the call from `_carry_out_thread_turn`'s caller path (graphify "test_thread_gate shape").
  - `test_turn_session_helpers_use_the_given_session` for `_execute_intent_internal`, `_clear_turn_transients`, with an input only the given session has (D-447).
- [ ] **Step 2:** M1-M10. Named: `test_thread_gate test_thread_offer test_thread_errand test_thread_hiring test_thread_close_atomic test_world_threads test_arrival_wiring test_arrival_narration test_local_place_travel test_lr00_p1_intent test_shops test_sessions` + `UNDO`. After M4 (pre-plant rule): `sys.modules[__name__]` back in `turn_front.py`'s `_local_place_turn` → the arrival pin red; restore, sha256.
- [ ] **Step 3:** M11 `game.py split T6.1a: thread turns, intent execution and place turns live in game_parts/turn_front.py`. M10b.

### Task 7: `front-2` (30 names, 944 lines, 14 S) (spec T6.1)

**Content:** `_tell_the_coin`, `_the_rest_of_the_line`, `_person_answers_stock`, the last-call and refusal turns (`_last_call`, `combat_refusal_turn`, `_approach_turn`, `player_cannot_act_turn`), `_reads_as_address`, `_addressed_in`, `_front_recovery`, `_front_step`, the spoken-coin offers (`_defer_spoken_coin_offer`, `_record_spoken_coin_response`, `_economic_listing`, `_front_economic_offer`, `_purchase_refused`, `_hand_over_coin`), `_coin_without_a_reading` (D-429's code; moved unchanged), the blow and heavy-question helpers (`_blow_stands`, `_blow_in_the_words`, `_ask_about_the_blow`, `_heavy_allowed`, `_ask_before_the_heavy`, `_answered_heavy_question`, `_ask_which_move`), `_narrated_person`, `front_read_ahead`, `_front_offer_gate`, `_line_gives`, `_front_consume`.

**Batch notes:** `combat_refusal_turn` is named in `docs/engine-split/source-readers.md`: the reader must still find it (read the row; change the reader path only if it reads `game.py` text, with an approval row). Long function `_front_step` key moves. D-429 stays open (Stage C).

- [ ] **Step 1: Tests** (seeds `20261420`-`20261429`):
  - `test_front_2_lives_in_the_part` (red).
  - `test_turn_money_helpers_use_the_given_session` (Review Focus 5) for `_tell_the_coin`, `_the_rest_of_the_line`, with an input only `s` has (a purse or a person only in `s`).
  - `test_a_patched_front_read_ahead_reaches_its_caller` (graphify "who calls front_read_ahead").
  - `test_a_coin_without_a_reading_answers_as_before`: two Turkish inputs from D-429's row, pinned in both flags exactly as today (the flag-on gap included: this is a move, not the fix).
- [ ] **Step 2:** M1-M10. Named: `test_coin_writers test_economic_room test_economic_dialogue test_money_routes test_front_money test_front_failed_fallback test_money_cards test_coin_never_works test_d096_dead_coin_card test_dilim3d_money test_d5_money_text test_d142_false_purse_line test_front_carries_more test_front_proposal test_front_tip_pipeline test_front_voice test_messenger_chain_front test_talk_front test_room_purpose_routing test_room_routing_diagnostic test_economic_spoken_consent test_combat_v2_authoritative` + `UNDO` + `DEATH`. `test_coin_writers` stays byte-unchanged and green; a coin writer found inside a moved name is a new writer: hold, `Ruling`, debt row.
- [ ] **Step 3:** M11 `game.py split T6.1b: the coin front, refusal turns and front gates live in game_parts/turn_front.py`. M10b.

### Task 8: `front-3` (8 names, 265 lines, 4 S) (spec T6.1)

**Content:** `_front_wield`, `_coin_not_parcel`, `_names_no_parcel`, `_front_hand_over`, `_front_work`, `_take_names_a_job`, `_front_take`, `_sleep_after_walk`. After this batch `turn_front.py` is whole (about 2 255 lines; it must be ≤ 2 500 with no `files` entry).

- [ ] **Step 1: Tests** (seeds `20261430`-`20261439`): `test_front_3_lives_in_the_part` (red); `test_turn_money_helpers_use_the_given_session` gains `_sleep_after_walk` (an input only `s` has).
- [ ] **Step 2:** M1-M10. Named: `test_wield_front test_front_proposal test_front_carries_more test_coin_writers test_economic_room test_money_routes` + `UNDO` + `DEATH`.
- [ ] **Step 3:** M11 `game.py split T6.1c: the hand-over, work, take and sleep fronts live in game_parts/turn_front.py`. M10b. Ledger: `wc -l` of `turn_front.py`.

### Task 9: `turn.py` — batch `turn-1` (13 names, 848 lines, 5 S) (spec T6.1)

**Content:** `ResolvedTurn`, `DEBUG_MODE`, `TurnResolved`, `turn_source_key`, `run_player_turn`, `_run_player_turn_owned`, `_run_player_turn`, `_run_player_turn_keyed`, `_dispatch_player_turn`, `_dispatch_turn_body`, `_spoken_rest_of_turn`, `_current_procedural_entity_ids`, `_keep_town_portrait`. Sensitive: `_run_player_turn_owned`, `_run_player_turn_keyed`, `_dispatch_player_turn`, `_current_procedural_entity_ids`, `_keep_town_portrait`.

**Files:** Create `ai-dnd/game_parts/turn.py`; modify `ai-dnd/game.py`, `surface.json`, `size_budget.json`; test `test_engine_parts_pilot.py` (the import-order test and the wrapper-filter tuple test gain `turn`, §23 row 7).

**Batch notes:**
- `TurnResolved` and `ResolvedTurn` are classes: they move and are re-exported. `_run_player_turn_internal` (still in `game.py` until `turn-3`) raises `TurnResolved`; `_dispatch_player_turn`, `_dispatch_turn_body` and `_spoken_rest_of_turn` catch it. Both sides must see the same class object.
- `ResolvedTurn` keeps `@dataclass` (Ruling L); header per M5.
- `DEBUG_MODE` (constant) moves. Ruling (pre-flight Minor 5): after `turn-3`, `_run_player_turn_internal` reads `turn.py`'s own binding bare, while `game_parts/narration_safety.py` reads `game.DEBUG_MODE` (the re-exported copy); a runtime `game.DEBUG_MODE = True` would then reach only `narration_safety` — nothing writes it today (measured: written nowhere, appendix E) and it is a debug switch, not game state — if wrong: one debug print path stays silent; the fix is a one-line `game.DEBUG_MODE` read in a later behaviour slice.
- `run_player_turn` is patched at 167 sites, `_dispatch_player_turn` at 17: the keyed turn must call `game._dispatch_player_turn`. Long function `_dispatch_player_turn` key moves. `turn.py` is about 870 lines after this batch: no `files` entry.

- [ ] **Step 1: Tests** (seeds `20261440`-`20261449`):
  - `test_turn_1_lives_in_the_part` (red).
  - `test_the_turn_resolved_signal_is_one_class`: `game.TurnResolved is game_parts.turn.TurnResolved`, and a turn that raises it from `_run_player_turn_internal` is caught by the moved dispatch (graphify "where is TurnResolved raised and caught").
  - `test_resolved_turn_is_the_same_dataclass` (Ruling L): `dataclasses.is_dataclass(game.ResolvedTurn)`; `[(f.name, f.default, f.default_factory) for f in dataclasses.fields(game.ResolvedTurn)]` equals the literal captured on `BASE_SHA` (`MISSING` written as `dataclasses.MISSING`).
  - `test_a_failed_turn_rolls_back_from_the_part` (Review Focus 3): `s = game.create_session(seed=…)`; `patch.object(game, "_dispatch_player_turn", side_effect=…)` that writes a marker into `s.world_state` and raises; `game.run_player_turn(<input>, session=s)` in the shape of the existing rollback test (graphify "run_player_turn rolled_back runtime snapshot test"); `s.world_state` and `s.character` equal their copies from before; the reply says rolled back as that test pins; `game._DEFAULT_SESSION` untouched.
  - `test_a_patched_dispatch_reaches_the_moved_keyed_turn`.
- [ ] **Step 2:** M1-M10. Named: `test_turn_never_traps test_turn_usage test_d234_combat_undo test_sessions test_startup test_combat_v2_authoritative test_lr00_p1_intent` + `UNDO` + `DEATH`.
- [ ] **Step 3:** M11 `game.py split T6.1d: the owned and keyed turn and the turn dispatch live in game_parts/turn.py`. M10b.

### Task 10: `turn-2` (2 names, 370 lines, 1 S) (spec T6.1)

**Content:** `_narrate_resolved_turn` (S), `_owner_module_reply`.

- [ ] **Step 1: Tests** (seeds `20261450`-`20261459`):
  - `test_turn_2_lives_in_the_part` (red).
  - `test_the_narrative_adapter_reaches_the_moved_narrate_turn` (Review Focus 4): Plan 4's `test_the_narrative_adapter_reaches_the_moved_ask` shape; `install_narrative_context_adapter(game)`, then a resolved turn through `game._narrate_resolved_turn(..., session=s)` (the `test_f04_frozen_narrator_faults` call shape) with the offline model: the adapter's wrapped `finalize` ran once.
  - `test_turn_session_helpers_use_the_given_session` gains `_narrate_resolved_turn`.
- [ ] **Step 2:** M1-M10. Named: `test_narrative_director test_f04_frozen_narrator_faults test_heard_rumours_turn test_quiet_turn test_smoke_turn_diagnostics` + `UNDO`. Long function `_narrate_resolved_turn` key moves.
- [ ] **Step 3:** M11 `game.py split T6.1e: narrating the resolved turn lives in game_parts/turn.py`. M10b.

### Task 11: `turn-3` — `_run_player_turn_internal` whole (2 756 lines) (spec T6.2)

**Review tier:** strong. This is the turn itself: Undo, death, money and every model call meet here.

**Files:** as Task 9, plus `identity_allowlist.json` (two rows: `sys.modules`, `locals`) and `api/tests/test_engine_size_budget.py`.

**Batch notes:**
- Identity uses (Ruling J): `sys.modules["game"]` (after Task 2) and `locals().get("preparsed_scene_intent")` move unchanged under their allowlist rows. D-345 is answered here.
- It reads `game._speech_debug_trail` (D-344: the trail stays in `game.py`, so `patch.object(game, "open", create=True)` still reaches it).
- `DEBUG_MODE` is read bare (a `turn.py` constant since `turn-1`; Ruling in Task 9).
- `size_budget.json`: `files["game_parts/turn.py"]` is created here at the real size (Ruling H, §23 row 5, `kadir-notes.md` line).
- `test_long_functions_cannot_grow_or_appear` names `"game.py::_run_player_turn_internal"` literally. It becomes `"game_parts/turn.py::_run_player_turn_internal"` in this commit (§23 row 6 "eşit sıkılık"; the test is otherwise unchanged).

- [ ] **Step 1: Tests** (seeds `20261460`-`20261469`): `test_turn_3_lives_in_the_part` (red); `test_turn_session_helpers_use_the_given_session` gains `_run_player_turn_internal` (an input only `s` has); `test_the_speech_debug_trail_patch_still_reaches_the_turn` (graphify "test patches game open create=True"): green before and after.
- [ ] **Step 2:** M1-M10 (allowlist rows first, M4). Named: the union of Tasks 6-10 + `test_heard_rumours test_heard_rumours_follow test_dialogue_live_context` + `UNDO` + `DEATH`. After M4 (pre-plant rule): `sys.modules[__name__]` back in `turn.py`'s `_run_player_turn_internal` → `test_heard_rumours_gets_the_game_module_from_the_turn` red; restore, sha256. The three Task 2 pins are green in both flags.
- [ ] **Step 3:** M11 `game.py split T6.2: _run_player_turn_internal lives in game_parts/turn.py, whole (spec §7 identity rows)`. M10b. `turn.py`'s `size_budget.json` entry = its real size: frozen from here.
- [ ] **Step 4: Ledger:** line counts of `game.py` and every part (`turn_front.py` ≤ 2 500; `turn.py` at its entry); the held table (if any); the three allowlist rows; Plan 5's re-export line count.

### Task 12: The net's exam on the moved tree

**Review tier:** none (Opus runner; nothing committed). Worktree `p5x` from the Stage B tip. Routine: one fault alone, run the named check, see the stated red, `git checkout HEAD -- ai-dnd`, next fault.

- [ ] **Fault 1 — a part binds a patched name.** `turn_front.py` gains `from game_parts import combat_flow` and `_last_call` calls `combat_flow.ensure_death_state`. Expected red: `test_engine_routing` (sibling import, R1/R9).
- [ ] **Fault 2 — the part's own module.** `sys.modules[__name__]` in `turn_front.py`'s `_local_place_turn`. Expected red: `test_a_local_place_turn_hands_the_game_module_to_arrival`, and R6 (no row for `__name__`).
- [ ] **Fault 3 — rollback on the wrong session.** `turn.py`'s `_run_player_turn_owned` reads `game._DEFAULT_SESSION` where it read `game._session()`. Expected red: `test_a_failed_turn_rolls_back_from_the_part`.
- [ ] **Fault 4 — frozen adapter alias.** `turn.py`'s `_narrate_resolved_turn` calls a module-level `_FINALIZE = game.finalize_narration` captured at import. Expected red: `test_the_narrative_adapter_reaches_the_moved_narrate_turn` (and R7/R9 if they see the capture; record which).
- [ ] **Fault 5 — money on the default session.** `turn_front.py`'s `_tell_the_coin` reads `game._DEFAULT_SESSION`. Expected red: `test_turn_money_helpers_use_the_given_session`.
- [ ] **Fault 6 — an unlisted identity use.** Add `locals()` to `turn_front.py`'s `_front_step`. Expected red: R6 in `test_engine_routing`, and `move_block` refuses it in a fixture (Task 1 guard).
- [ ] **Fault 7 — the Undo restore leaves.** Add `_restore_in_place` to `turn-2.txt`. Expected red: `test_the_undo_restore_stays_with_the_session`.
- [ ] **Fault 8 — `turn.py` grows.** Add one line to `turn.py`. Expected red: `test_the_engine_fits_its_budget` (the frozen entry).
- [ ] **Final step:** `p5x` restored and clean, `p5m` untouched; `ENGINE_SET` + `NEIGHBOURS` green in both flags. A fault that stayed green stops the plan before the gate: fix the check red-first, then repeat the exam.

### Task 13: Gate TM5 (spec TM5), PR B

**Review tier:** strong (whole-branch review on Opus): the Stage B diff; the money, death and Undo tests named in Tasks 6-11; M7 for the six batches, each against its move commit's parent; `writer_scan.py` on the gate tree with all six batch files (`missing=0`, `HELD` sets equal the expected files exactly, by the `$3` column).

- [ ] **Step 1:** `git fetch origin`; merge `origin/main` if it moved (`MAIN_SHA`). If `game.py` or a part changed underneath: rerun M7 for every batch against a fresh base and regenerate the locks.
- [ ] **Step 2: Whole-branch review before the suites.** One fix wave, red-first (Opus); scoped re-review (Opus). From Step 3 on, only the ledger, debt rows and PR text change; any change to code, tests or locks reruns Steps 3-6.
- [ ] **Step 3: N4/N7 bases** (Plan 4 Task 17 Step 3 Ruling carried).
  - `git worktree add --detach ../AI-DND-k2-bolme-p5b <Stage A tip>`; in it, `git merge --no-ff --no-edit <MAIN_SHA>` (local, never pushed).
  - Check: `git diff <p5b HEAD> <Stage B tip> --stat -- . ':!ai-dnd/game.py' ':!ai-dnd/game_parts'` lists only Stage B's own tests, locks and docs. `git diff --quiet <P5BASE> <Stage B tip> -- <every money, death and Undo test named in Tasks 6-11, UNDO and DEATH included>`: RC 0.
  - Four suites, one at a time, each after the gate wait, the foreign-load check and an empty `pgrep -af slot_gate`, `WT` = `p5b`, started detached (Ruling E form and start check): `p5g0-off-n4-n7-b`, `p5g0-off-n4-n7-c`, `p5g0-fon-n4-n7-b`, `p5g0-fon-n4-n7-c`. At most two suites per agent (Ruling E).
- [ ] **Step 4: Gate suites** on `p5m`: `p5tm5-off-n4-n7`, then `p5tm5-fon-n4-n7`. Pass: `PAR_EXIT=0` and `failing_ids 0`. An unseeded red follows Plan 3's 40-fixed-town-seed procedure; any other red stops the plan.
- [ ] **Step 5: N4 and N7 per flag.**
  - `ledger_diff.py --diff --base <b> --base2 <c> --new <tm5>`: `DROPS 0`, `LOST 0`, `SUBLOST 0`, `SUBGONE 0`, `SUBCRASH 0`.
  - `coverage_by_function.py --diff`: `DOWN 0` outside the noise set; every `UP` explained.
  - Ruling: N7 equality is checked at TM5 too, though spec TM5 lists only N4 — the turn core is the most-covered code and the suites already write the N7 ledgers — if wrong: an explained noise entry. §23 row 10.
  - Any drop, lost test or `DOWN` stops the plan.
- [ ] **Step 6: Speed (Rulings B, C).** Suites by wall clock against the Ruling C limits; longest-shard ratio as information. Cumulative A/B, OLD `p5o`, NEW `p5m`, prefix `p5t13cum`: pass ≤ 1.10, above it STOP. One flag-on reading `p5tm5bench-fon`, recorded only. Every number with its load line.
- [ ] **Step 7: Checks without a suite.** `outside_probe.py` → `PROBE ok parts=` including `game_parts.turn_front` and `game_parts.turn`; `test_regression.py` 30/30; `move_check.py --comments-only` against the `P5BASE` archive → `COMMENTS base=<C> now=<C>`; `routing_audit.py` → `clean`; `classify_all.py` → `not_in_lock=0`; ruff once; both import orders with the `start_local.ps1` interpreter rc 0; sizes: `game.py` = `size_budget.json`, every part ≤ 2 500 (`turn_front.py` included) or at its frozen entry (`narration_safety.py`, `turn.py`). **Zero-tolerance journeys (Ruling D):** `NEIGHBOURS` alone in both flags (`p5tm5-journeys-off/-fon`): `RESULT exit=0`, journey count pasted.
- [ ] **Step 8: Debt rows** (table below; parks from Tasks 0-12 included). Every park gets a row; none without an owner.
- [ ] **Step 9:** Recheck the free debt ids. Push and open PR B; merge PR A and PR B in order, ancestor check before each merge, CI rules after each.
- [ ] **Step 10:** Open `bash`/`sleep` processes and the `p5b`/`p5p`/`p5x` slots' runs checked. Ledger lines "TM5 geçti", "oynayış ertelendi (Kadir 2026-11-20)". Cut `p5c` (Stage C). Worktrees are not deleted.

---

# Stage C — D-429 money fix (worktree `AI-DND-k2-bolme-p5c`, PR C)

### Task 14: D-429 — a coin decision without a reading answers as with the flag off

**Review tier:** strong (money; Opus implementer, Opus review). Branch `task/game-py-bolme-p5-d429` from the Stage B tip after TM5; PR C stacked on PR B, merged after it.

**Files:**
- Create: `ai-dnd/api/tests/test_d429_coin_without_a_reading.py` (seeds `20261480`-`20261489`).
- Modify: `ai-dnd/game_parts/turn_front.py` (`_coin_without_a_reading`; `_front_step` only if the fix cannot live in the first), `docs/agents/debt-register.md` (D-429 closed).

**Rules for this task:**
- The fix goes into `turn_front.py`, a normal part (Ruling H): no new module, no `allowed_imports.json` row, no `surface.json` row. `turn.py` is not touched.
- Lock changes, each with its §23 row if it happens: none expected. `turn_front.py` must stay ≤ 2 500 (`part_max`; about 2 255 before the fix). `_front_step` is on the long-function list at 235: if the fix makes it grow, that is a raise (karar 10): §23 row plus a `kadir-notes.md` line, "gevşetme olabilir". Prefer keeping the change inside `_coin_without_a_reading` (37 lines, under `long_function_min` 151).
- Money never moves in any case (D-429 row); the tests assert the purse is byte-equal before and after.

- [ ] **Step 1: Red tests, both flags** (the row's four cases):

```python
def test_a_beer_paid_below_price_opens_the_counter_with_the_reading_down(self):   # case 1, red with the flag on
    # "barmene 2 bakır verip bi bira istiyorum", model reading fails -> the counter opens as with the flag off; purse equal
def test_a_coin_and_bed_promise_to_a_named_person_keeps_its_note(self):           # case 2, red expected, not known
    # "Aldric'e 1 gümüş verip oda tutuyorum" (a named NPC who is not the innkeeper): the room card opens, or the
    # `unclear` note is kept when it cannot open; purse equal
def test_a_bed_promise_in_combat_stays_unclear(self):                              # case 3 (R11 `unclear` kept)
def test_the_room_reading_really_failed_in_the_http_test(self):                    # case 4
    # the HTTP room test's path asserts _front_route == "fallback:failed"
```

  - Case 2's red is not known: D-429's row says "incelemeye göre olası, koşulmadı". If it is green on its first run it becomes a guard (planted red, Ruling); a red is never forced.
  - Run with `ENGINE_SET` + `NEIGHBOURS` + `api.tests.test_coin_writers api.tests.test_economic_room api.tests.test_front_failed_fallback api.tests.test_front_money` (`p5t14-red-off/-fon`): the stated reds, the rest green.
- [ ] **Step 2: Fix.** Then `p5t14-off/-fon`: `RESULT exit=0`. Full M10-shaped pattern run over `SLOTPY inventory.py --touching _coin_without_a_reading _front_step` + the money modules of Task 7, both flags. Cumulative A/B (`p5t14cum`), binding.
- [ ] **Step 3:** D-429 closed with the test names. **Commit** `D-429: a coin decision without a model reading answers as with the flag off (money, red-green)`. Push, PR C, merge after PR B with the ancestor check and the CI rules. Ledger "D-429 kapandı"; Turkish five-line morning summary; "Plan 5 bitti; Plan 6 (T7) yazılabilir".

---

## Approval list §23 rows (the executor adds them to `docs/agents/onay-listesi-20261115.md` with the task that makes the change)

| # | Test or rule | Change | Mark | Written in |
|---|---|---|---|---|
| 1 | Speed rule (Tasks 0, 4, every M10b, 13, 14) | cumulative A/B against `TM0BASE` at every binding point, M10b included | sıkılaştırma, gevşetme değil | Task 0 |
| 2 | `move_block` N3 rule 6 | an identity use moves when an `identity_allowlist.json` row names its file, function and name | gevşetme olabilir (sınır yeniden tanımlandı) | Task 1 |
| 3 | `identity_allowlist.json` | three rows: `turn_front.py` `_local_place_turn` `sys.modules` (Task 6); `turn.py` `_run_player_turn_internal` `sys.modules`, `locals` (Task 11) (spec §7) | gevşetme olabilir | Tasks 6, 11 |
| 4 | `_batches_are_movable` | `sensitive_allowed=True` for T6 (spec T6, strong review) | gevşetme olabilir | Task 3 |
| 5 | `size_budget.json` `game_parts/turn.py` | entry created once in `turn-3` at the real size, above `part_max` 2 500, then frozen (spec §11 "geldikleri boyutta dondurulur"; karar 10 note in `kadir-notes.md`) | gevşetme olabilir (sayı 2 500'ün üstünde) | Task 11 |
| 6 | `test_long_functions_cannot_grow_or_appear` | literal key `game.py::_run_player_turn_internal` → `game_parts/turn.py::_run_player_turn_internal` | eşit sıkılık | Task 11 |
| 7 | `test_both_import_orders_work_in_a_fresh_interpreter`, wrapper-filter tuple test | expected output and tuple gain `turn_front` (Task 6) and `turn` (Task 9) | iddia eklendi | Tasks 6, 9 |
| 8 | Shard timeout 4 500 s, wall clock | carried from Plans 3-4 (D-448) | taşındı | Task 0 |
| 9 | M12 writer scan | Plan 4 row 8 carried: the `HELD` set equals Task 3's recorded set exactly | gevşetme olabilir (taşındı) | Task 0 |
| 10 | N7 at TM5 | coverage equality checked although spec TM5 lists only N4 | sıkılaştırma | Task 13 |

## Debt rows this plan owns and what happens to each

| Row | Handling |
|---|---|
| D-345 `locals()` in the turn function | Task 11 moves it unchanged under an allowlist row; row updated with the pin name, trigger → "T7 / tur işlevine dokunan ilk davranış işi" (spec §7: it stays in the register) |
| D-344 `_speech_debug_trail` stays | Task 11 pin; row updated "Plan 5: tur kodu taşındı, iz `game.py`'de, yama ulaşıyor"; trigger unchanged |
| D-429 coin decision without a reading | Stage C, Task 14; closed there |
| D-349 N3 carried items | Task 0 Step 7 / Task 3 Step 4 recheck over the turn names (ledger lines); row updated in Task 13 Step 8 |
| D-378 held names (`turn_source_key`, `_intent_infrastructure_result`, `_dynamic_engine_transitions`) | the first two move in `turn-1`/`front-1`; `_dynamic_engine_transitions` stays (Ruling I); row updated at Task 13 |
| D-448 load-sensitive speed | Task 13 numbers; closed or carried with them |
| D-341, D-342 probes | Tasks 5 and 13 checks |
| D-363 top-level `if`/`try` | Task 0 Step 3 recheck; carried |
| Plan 4 rows with a Plan 5 trigger (D-450..D-469) | listed in Task 0 Step 7 and handled in the task they name |

New rows this plan writes (ids from `D-470`, in Task 13 Step 8):
- `D-470` `turn.py` frozen at its arrival size (about 4 020 lines; spec §5 estimated 3 900, §11 freezes it); it can only shrink by splitting `_run_player_turn_internal`, which spec §2 puts in the slice after the split. Owner: the first behaviour slice after Plan 6.
- `D-471` `_restore_in_place` and `_dynamic_engine_transitions` stay in `game.py` with `GameSession` (Ruling I); 78 lines, not what keeps `game.py` over 1 500 (see D-473). Owner: Plan 6.
- `D-472` `sys.modules["game"]` in `turn_front.py` and `turn.py` instead of spec §7's literal `game` (Ruling J). Owner: Plan 6 (T7.4 review).
- `D-473` `game.py` ≤ 1 500 (spec §2, §5, §11) is not reachable by moving: after Plan 5 it is 2 148 lines plus re-export lines, of which 1 292 are blank lines left behind by moves; reaching ≤ 1 500 needs a blank-line cleanup that spec §2 lists as a non-goal ("biçim düzeltme"), or a spec decision. Owner: Plan 6.

Carried unchanged: D-343 (T7), D-351, D-379 and D-380(3) (Plan 6), D-356-D-358, D-362, D-365.

---

## Plan 6 outline

**Plan 6 — T7 closure.** Final sizes; dead-code candidates with both-flag N7 evidence; D-343, D-379, D-351, D-380(3), D-470-D-473; dev-only tools; Kadir's closing play (Ruling D ends here).

**`game.py` ≤ 1 500 (pre-flight I5), said plainly.** Measured on `0b1dca5a` with every Plan 4 and Plan 5 name removed: 2 148 lines = 1 292 blank + 97 comment-only + 759 code (never-moved names, Ruling I's 78 lines, imports, re-exports, module setup), plus Plan 5's re-export lines. Moving cannot reach 1 500: spec §5 forbids moving the never-moved code, and Ruling I's 78 lines are too few. Only removing the blank lines that moves left behind can, and spec §2 names "biçim düzeltme" a non-goal. So Plan 6 must, before any line is removed:
1. write a `Ruling` that deleting blank lines orphaned by moves is part of finishing the move, not a format fix, with an approval §24 row marked "gevşetme olabilir (spec §2 hedef olmayanı yorumlanıyor)" and a `kadir-notes.md` line (karar 10 style: Kadir sees it);
2. remove only whole blank lines (no comment, no code), checked by `move_check.py` as deletions only and by `COMMENTS base=<C> now=<C>`;
3. if that Ruling is not taken, Plan 6 lowers nothing: `game.py` stays at about 2 200 lines, `size_budget.json` holds the real size, and D-473 stays open for Kadir. Plan 6 does not promise ≤ 1 500 otherwise.

Ruling: Plan 5 does not change `move_block` to drop separator blank lines (the reviewer's optional fix, about 130 lines) — it would change the mover in the middle of the strong moves and still leave about 1 160 blank lines, so it does not decide ≤ 1 500; the decision belongs with the rest of the cleanup in Plan 6 — if wrong: Plan 6 removes about 130 more blank lines.

---

## Self-review

1. **Spec coverage.**
   - T6.1 (`_dispatch_player_turn`, keyed turn, `_execute_intent_internal`, front and thread functions) → Tasks 6-10.
   - T6.2 (`_run_player_turn_internal` whole, identity edits named in the brief) → Tasks 2 and 11 (Ruling J).
   - TM5 (suites ×2 with bases, N4, time and turn bench, PR) → Task 13 (plus N7, Ruling).
   - §5 `turn.py` content → Ruling H (`CORE` = spec §5's list), Tasks 9-11.
   - §7 identity names → Tasks 1, 2, 6, 11; `locals()` in the allowlist and the register (D-345). §7 speed stop → Tasks 0, 4, every M10b, 13, 14.
   - §11 each part ≤ 2 500, `turn.py` frozen at arrival → Ruling H, Tasks 8 (turn_front size), 11 (entry), 13 Step 7, Fault 8.
   - §2/§5 `game.py` ≤ 1 500 → not reachable in Plan 5; D-473 and the Plan 6 outline say what Plan 6 must do.
   - D-429 after TM5, red-green money → Task 14.
2. **Lessons from Plan 4 carried:** 4 500 s shards (Ruling C); WMI foreign-load script (Global Constraints); detached starts in the exact working form with a start check, 9-minute polls, 150-minute cap, Status CONTINUE, continuation after a lost agent (Ruling E); M12 as a reading list read by `$3`; base pins in both flags; existing header order kept (M5); cumulative rule against `TM0BASE` (Ruling B).
3. **Step scan.** Every move task names its batch, sizes, tests, seeds, named M10 modules and commit message. Test bodies that depend on existing tests name the graphify query that finds them.
4. **Name consistency.** Batches `front-1..3`, `turn-1..3` match `-measure/batches/` and appendix D; labels `p5t<N>-<B>-<off|fon>`; Review Focus test names match Tasks 2, 3, 7-10 and 12; `_PART_MODULES` gains `game_parts.turn_front` once (Task 6) and `game_parts.turn` once (Task 9).
5. **Proportion.** 15 tasks: Stage A 6, Stage B 8, Stage C 1. Strong: Tasks 1, 2, 5, 6-11, 13, 14. Opus net review: Task 3. Runner only: Tasks 0, 4, 12. Full suites: 6, all in Task 13. A/B series: Tasks 0, 4, 6-11, 13, 14 (10 series of 12 bench runs).
6. **Loosening check.** No Ruling loosens a controller or CLAUDE.md rule. Boundary rows marked "gevşetme olabilir": §23 rows 2, 3, 4, 5, 9. Rows 1 and 10 are stricter.

## Execution

Subagent-driven. Speed rule 1 as in Global Constraints (Stage A only; Task 3 writes §23 after Task 1's review and fix wave). Stage B runs strictly in order; Stage C starts only after TM5. The controller holds the ledger, the gate waits, the labels and the A/B series. Implementers get the Move procedure (Plan 3's text, Plan 4's deltas and the deltas above) word for word, `STORE/common.md` and their task text.

---

## Pre-flight review fixes

Review: `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p5/p5-preflight-review.md` (Critical 2, Important 6, Minor 8). Re-measurement with the fixed scripts on the same read-only archive of p4m `0b1dca5a` (WSL `python3` 3.12): `STORE/out-c1/`, copied into `-measure/out/`. No test, `slot.sh` or `slot_gate.sh` ran.

| Finding | What changed |
|---|---|
| C1 | Ruling H rewritten: two parts. `turn.py` = spec §5's core (16 names, 3 974 lines), created once in `turn-3` at its real size and frozen (spec §11 quoted); `turn_front.py` = 51 names, 2 179 lines, normal `part_max`. `batches5.py` cuts two targets (`CORE`); six batches (`front-1..3`, `turn-1..3`), CAP 1 000 except `turn-3` (Ruling K). Six move tasks (6-11); exam, TM5, D-429 renumbered 12-14. `_PART_MODULES` two entries; import-order rows; Fault 8; D-470 text; D-429 lands in `turn_front.py`. One §23 raise row (row 5) instead of three. |
| C2 | `p5_checks.py` sees class decorators (`decorated 1`: `ResolvedTurn` `@dataclass`); `batches5.py` counts decorator names as read (turn-1 header now has `dataclass`). Ruling L; M2 and M5 text; Task 9 pin `test_resolved_turn_is_the_same_dataclass`; Task 4 records the decorator line and `CHANGED 0`. |
| I1 | Ruling E and `common.md` carry the literal working `Start-Process` form with `'-lc','\"...\"'`, the reason, and a 2-minute start check. |
| I2 | Task 0 Step 8 creates §23 with rows 1, 8, 9; Task 1 adds row 2 and lists the file; Task 3 writes §23 only after Task 1's review and fix wave. Speed rule 1 text equal in Global Constraints and Execution. Approval table names the writing task per row. |
| I3 | Task 0 Step 2 applies only this branch's INDEX line (`git diff 45d2c690 task/game-py-bolme-p5 -- docs/design/INDEX.md \| git apply`) and checks one added line. |
| I4 | `DEATH` list defined and named in Tasks 7, 8, 9, 11; Task 13 Step 3 checks it. |
| I5 | Measured composition in "Measured draft base", appendix I and the Plan 6 outline (2 148 = 1 292 blank + 97 comment + 759 code); D-473; Plan 6's required Ruling stated plainly, no promise of ≤ 1 500. Optional `move_block` blank-line deletion not taken (Ruling in the Plan 6 outline). |
| I6 | Task 14 edits `turn_front.py` (not frozen): no new module, no lock widening; each possible lock change named with its §23 row; a first-run green case becomes a guard plus a Ruling (Task 14 and Global "Red first"). |
| Minor 1 | 43 names (plan and appendix B). |
| Minor 2 | Content lines rebuilt from the batch files (sensitive names listed). |
| Minor 3 | Targeted runs write `api.tests.<m>` (Task 2 Step 4, Task 4 Step 2, Task 14 Step 1); rule added to "Run commands". |
| Minor 4 | Size estimates include header and separators: `turn_front.py` about 2 255, `turn.py` about 4 020; the `kadir-notes.md` line carries the real numbers. |
| Minor 5 | `DEBUG_MODE` Ruling in Task 9. |
| Minor 6 | Task 2 Step 3: planted `sys.modules["json"]` proves both pins red before the edit. |
| Minor 7 | Task 0 Step 7 and Task 3 Step 4 write ledger lines; the register row is updated in Task 13 Step 8. |
| Minor 8 | Ruling E names Plan 4 Task 10. |

Rulings J, K and I stand as the review found them. No finding was ruled against.
