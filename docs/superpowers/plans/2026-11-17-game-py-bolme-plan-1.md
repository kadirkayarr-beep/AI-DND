# game.py Split, Plan 1 (T0 safety net, T1 single copy, T2 wrapper + hash + pilot) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the machine proof net (N1-N8), make the engine a single module copy, and move two pilot blocks out of `ai-dnd/game.py` so the method is proven before any bulk move.

**Architecture:** Moved code lives in `ai-dnd/game_parts/` and reaches every engine name as `game.X` (the "centre rule"), so every existing `import game`, `game.X` and test patch keeps working unchanged. `game.py` re-exports moved names with explicit `from game_parts.x import a, b` lines and its bound-session wrapper is widened by an explicit `_PART_MODULES` list. Static tools (stdlib `ast`, `symtable`, `tokenize`) lock the surface; two dynamic tools (patch-hit ledger, per-function coverage) prove tests still exercise the same code.

**Tech Stack:** Python stdlib (`ast`, `symtable`, `tokenize`, `unittest`); dev-only pinned `coverage`, `ruff` (F821, F401, F811, never `--fix`/`format`); guarded WSL runner `slot.sh`.

**Spec:** `docs/superpowers/specs/2026-11-17-game-py-bolme-design.md` (approved by Kadir 2026-11-17, all 11 decisions as recommended). The spec is the authority; where this plan and the spec differ without a `Ruling` line, the spec wins.

**Scope (Ruling by the controller, not reopened):** this plan covers spec stages T0, T1, T2 only. T3-T7 are separate plans written after this plan's last gate (see "Sonraki planlar").

**Gates in this plan:** G0 = spec TM0 (Task 10); G1 = a gate after T1 that the spec does not have (Task 13); G2 = spec TM1, the go/no-go gate (Task 21). The controller's brief calls the last gate "TM2"; the spec's own TM2 (after T3) belongs to Plan 2.

**Owner approval (Kadir, 2026-11-17: "Onaylıyorum"):** this plan; execution method subagent-driven; baselines stored in `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/`; dev-only install of `coverage` and `ruff` from PyPI plus the slot-venv `.pth` probe (feasibility measured first in Task 9). Execution starts only after Kadir's BM play gate (≥10 min).

## Global Constraints

- **Precondition 1:** Kadir has played BM for at least 10 minutes and said so. Until then no task starts; the ledger says "oynayış bekliyor".
- **Precondition 2:** `origin/main` contains the BM slice (e8a66d88 or later).
- **Ruling:** T0 locks are generated directly on `main` — BM is already merged, so the spec §12 "unmerged branch first, regenerate after BM" detour is void — if wrong: locks are regenerated, one task.
- **Worktrees:** one per stage, off `origin/main`, one writer each. From `C:\Users\Kadir\Desktop\AI - DND`: `git fetch origin` then `git worktree add ../AI-DND-k2-bolme-t0 -b task/game-py-bolme-t0 origin/main` (likewise `-t1`, `-t2`). A stage starts only after the previous stage's PR is merged.
- **Push, PR, merge:** only with Kadir's fresh approval for that action. No force push. Never delete a branch. After every push/merge: `gh run list --repo kadirkayarr-beep/AI-DND --limit 5`; "AI-DND bounded verification" must be green before "done".
- **Freeze (spec decision 3):** while the T1 or T2 branch is open, no other branch touches `ai-dnd/game.py` or `ai-dnd/game_parts/`.
- **Tests run only through the slot runner.** `SLOT` = the slot number the controller assigns, `WT` = worktree folder name only.
  - Targeted: `bash C:/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh <SLOT> <WT> test <label> 1800 <modules...> <NEIGHBOURS>`; pass = a line `RESULT exit=0 Ran <n> tests`.
  - `NEIGHBOURS` = `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys` (in every task's targeted run; never dropped).
  - Full suite, flag off: `bash C:/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh <SLOT> <WT> par <label> 3 3000 '.'`; pass = `PAR_EXIT=0`.
  - Full suite, flag on: prefix `WSLENV=AI_DND_FRONT_PROPOSAL AI_DND_FRONT_PROPOSAL=1` and use a different label.
  - Never two full suites at once (16 GB RAM). Full suites only at the three gates. No browser tests. `slot.sh` stages `ai-dnd content lib artifacts .github start_local.ps1` with `git add`; anything a test reads must live under `ai-dnd/`.
- **Scripts that are not tests** (`SLOTPY`): after a `slot.sh ... test` call has synced the tree, run `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- bash -c 'cd /root/aidnd-env-<SLOT>/src/ai-dnd && /root/aidnd-env-<SLOT>/proj/.venv/bin/python scripts/engine_split/<script>.py <args>'`. Output paths are given as `/mnt/c/Users/Kadir/Desktop/<WT>/...`. Ruling: scripts run with the slot's Python outside the guarded launcher — they are not tests and call no model — if wrong: rerun inside a test module.
- **Red first.** Every new test is seen failing for the stated reason before the change. Every new test that starts a campaign or session wraps it in `fixed_town(self, <seed>)` from `api/tests/town_seed.py`.
- **Old-behaviour tests** are rewritten only with equal strictness and get a row in `docs/agents/onay-listesi-20261115.md` (columns `Test | Değişiklik | İşaret`; mark "gevşetme olabilir" when a boundary moves). Unmarked loosening, skipping or deleting stops the work.
- **Findings** go to `docs/agents/debt-register.md` as rows with exactly 8 `|` (next free id after the highest `D-nnn`; D-330 was the highest on 2026-11-17).
- **Ledger:** `.superpowers/sdd/game-py-bolme-plan-1/progress.md` (local, not committed). Decisions as `Ruling: <karar> — <neden> — <yanlışsa maliyeti>`. Each gate records N1/N4/N5/N7 output, suite seconds and the turn benchmark.
- **Review tier is by content** (spec §5): money/save/Undo/snapshot touching work gets an independent review on the strongest model (fable is allowed for this plan only; otherwise Opus). Each task states its tier. Reviews run on a `git archive <sha>` copy.
- **Tools:** stdlib `ast`/`symtable`/`tokenize` in CI. `coverage`, `ruff` dev-only, pinned in `ai-dnd/scripts/engine_split/requirements-dev.txt`, never in `uv.lock`, never in CI. Forbidden: `ast.unparse`, formatters, `ruff --fix`, `ruff format`, rope, libcst codegen, import-linter, desloppify. Moved source is edited in place only.
- **Centre rule (spec §4):** a part never calls another engine name bare; it writes `game.X`. No part imports a sibling part or writes `from game import`. Only `game.py` imports `game_parts.*` (tests do not either).
- **Never moved (spec §5):** `GameSession`, the session core, the wrapper, `create_session`, `_GameModule`, the import-time `initialize_game` call, `_speech_debug_trail`, `DEFAULT_SAVE_PATH`, `start_terminal_game`.
- **Never read or print key files** (`.env`, `apikeys*`, `*.pem`). Old saves do not matter (owner rule): no compatibility work.
- **Every implementer brief** carries `docs/agents/implementer-preamble.md`, the graphify rule (`graphify query` first when `graphify-out/graph.json` exists in the worktree), "a move task changes nothing else", "the prefix is added in place; source is never regenerated", and names functions/files, not line numbers. `game.py` is 25 122 lines: never read it whole.
- **Stop and ask** only for: irreversible/destructive action, security-sensitive action, side effect outside the worktree (push, merge, publish), a plan so broken every path is a guess. Everything else: decide, write a `Ruling`, continue.
- **Approvals to collect once, before Task 1** (one batched question to Kadir): (a) `pip install` of the pinned `coverage` and `ruff` into the slot venv (downloads from PyPI; spec decision 5); (b) one `.pth` file in the slot venv for the dynamic probes (Task 9), removed when the whole split ends; (c) baselines stored in `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/` because `.local/` is per worktree.

## Review Focus

Failure modes the spec implies but none of its listed checks exercise; each is pinned by a test in the task named.

1. **Terminal started from another working directory** (`python C:\...\ai-dnd\game.py` with cwd elsewhere): the game starts and the engine is imported once. Task 11.
2. **Terminal `/save` and `/load` through the moved loop:** an explicit path saves and loads; the default path is still `ai-dnd/saves/adventure.json`, never `ai-dnd/game_parts/saves/`. Task 11.
3. **Terminal stdin closed (EOF):** the process ends promptly with the same exit code as before the change, no hang. Task 11.
4. **CRLF working copy:** the move tool and `move_check` give the same verdict for a CRLF file as for its LF twin and never rewrite line endings. Tasks 5 and 6.
5. **Golden surface must not depend on the machine:** a default such as `save_path=PosixPath('/root/...')` must not put a path into the golden file. Task 2.

---

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `ai-dnd/scripts/engine_split/__init__.py` | empty package marker | 1 |
| `ai-dnd/scripts/engine_split/inventory.py` | top-level index, call graph, constant clusters, spec-claim re-check | 1 |
| `ai-dnd/scripts/engine_split/surface.py` | N1 snapshot + diff rule | 2 |
| `ai-dnd/scripts/engine_split/patch_census.py` | N2 scan | 3 |
| `ai-dnd/scripts/engine_split/sensitivity.py` | N8 scan | 4 |
| `ai-dnd/scripts/engine_split/move_check.py` | N5 equivalence | 5 |
| `ai-dnd/scripts/engine_split/move_block.py` | in-place cut, append, `game.` prefix | 6 |
| `ai-dnd/api/tests/engine_sources.py` | N6 `engine_source_files()` | 7 |
| `ai-dnd/scripts/engine_split/probe_boot.py`, `ledger_diff.py`, `coverage_by_function.py` | N4, N7 | 9 |
| `ai-dnd/api/tests/bench_engine_turn.py` | fixed turn benchmark (not collected by `par`) | 9 |
| `ai-dnd/scripts/engine_split/routing_audit.py` | N3 | 17 |
| `ai-dnd/api/tests/engine_split_locks/*.json` | `surface`, `patch_census`, `sensitive`, `size_budget`, `allowed_imports`, `identity_allowlist` | 2, 3, 4, 8, 17 |
| `docs/engine-split/` | committed reports: `inventory.json`, `claims.md`, `patch-census.md`, `source-readers.md` | 1, 3, 7 |
| `ai-dnd/game_parts/__init__.py` | `import game` only | 11 |
| `ai-dnd/game_parts/terminal.py` | terminal loop `run(input_fn, print_fn)` | 11 |
| `ai-dnd/game_parts/character_rules.py` | pilot (a): `roll_d20` | 18 |
| `ai-dnd/game_parts/text_rules_a.py` | pilot (b): one regex constant + one pure helper | 19 |

Tests import the tooling the way `api/tests/test_development_tooling.py` imports `scripts/development_checks.py` (read its import header first and copy the pattern). Every tooling function takes paths as arguments so tests run on small fixture sources in a temp dir.

---

# Stage T0 — safety net (worktree `AI-DND-k2-bolme-t0`, PR 1). The engine does not change.

### Task 0: Open the stage

**Review tier:** none (no code).

- [ ] **Step 1:** Confirm both preconditions and collect the three batched approvals (Global Constraints). Write the answers in the ledger.
- [ ] **Step 2:** Create the worktree and the ledger file. If the spec and this plan are not on `origin/main`, bring exactly those two files: `git checkout task/game-py-bolme-tasarim-20261117 -- docs/superpowers/specs/2026-11-17-game-py-bolme-design.md docs/superpowers/plans/2026-11-17-game-py-bolme-plan-1.md`, add one line for the spec to `docs/design/INDEX.md`, commit `game.py split: design and plan 1 documents`.
- [ ] **Step 3:** Run `NEIGHBOURS` once and record the seconds (measured, not guessed). Expected: `RESULT exit=0`.

### Task 1: Inventory and spec-claim re-check (spec T0.1, first half)

**Review tier:** normal. Money/save/Undo: no.

**Files:**
- Create: `ai-dnd/scripts/engine_split/__init__.py`, `ai-dnd/scripts/engine_split/inventory.py`, `ai-dnd/scripts/engine_split/requirements-dev.txt`
- Create: `docs/engine-split/inventory.json`, `docs/engine-split/claims.md`
- Test: `ai-dnd/api/tests/test_engine_split_inventory.py`

**Interfaces — Produces:**
- `top_level_index(path: Path) -> list[dict]`; each dict: `name`, `kind` (`"function" | "class" | "assign" | "import"`), `start` (first line of the contiguous comment block directly above, no blank line between, else the def/decorator line), `def_line`, `end`, `lines`.
- `call_graph(path: Path) -> dict[str, list[str]]`: top-level function → sorted engine top-level names it reads as free (global-scope per `symtable`) names.
- `constant_clusters(path: Path) -> list[list[str]]`: connected components of module-level assignments whose right-hand side reads another module-level assignment.
- `closed_helpers(path: Path) -> list[str]`: functions whose call-graph entry holds no function or class name.
- `verify_claims(root: Path) -> list[dict]` (`claim`, `spec_value`, `measured`, `status` in `same | shifted | false`).
- CLI: `inventory.py --root . --out-json <path> --out-claims <path>`.

- [ ] **Step 1: Measure [Y].** Check that `SLOTPY` works (`python -c "import game; print(len(vars(game)))"`), and that a new directory under `ai-dnd/scripts/` trips no file-inventory lock: search `ai-dnd/scripts/development_checks.json` and `api/tests/test_development_tooling.py` for a pinned file list. Record both in the ledger.
- [ ] **Step 2: Write the failing tests** on fixture sources written to a temp dir:

```python
def test_index_block_starts_at_the_comment_directly_above(self):
    src = "# banner\n\n# why f exists\n@dec\ndef f():\n    return 1\n"
    f = next(d for d in top_level_index(write(src)) if d["name"] == "f")
    self.assertEqual((f["start"], f["def_line"], f["end"]), (3, 4, 6))

def test_call_graph_ignores_locals_and_attributes(self):
    src = "def a():\n    return 1\ndef b():\n    a = 2\n    return a\ndef c(x):\n    return a() + x.a\n"
    self.assertEqual(call_graph(write(src)), {"a": [], "b": [], "c": ["a"]})

def test_constant_clusters_join_dependent_constants(self):
    src = "import re\nA = 'x'\nB = re.compile(A)\nC = 3\n"
    self.assertEqual(constant_clusters(write(src)), [["A", "B"], ["C"]])

def test_closed_helpers_reference_no_engine_function(self):
    src = "K = 1\ndef a():\n    return K\ndef b():\n    return a()\n"
    self.assertEqual(closed_helpers(write(src)), ["a"])
```

- [ ] **Step 3:** Run `api.tests.test_engine_split_inventory` + `NEIGHBOURS`. Expected: FAIL, `ModuleNotFoundError` for `engine_split`.
- [ ] **Step 4:** Implement the four functions with `ast` + `symtable` (free name = a name `symtable` reports as global in that function's scope tree).
- [ ] **Step 5:** Implement `verify_claims` with one check per spec [D] claim. Claims and spec values: top-level functions 521; `_run_player_turn_internal` 2 743 lines; comments 1 056 (`tokenize.COMMENT`), 119 naming Kadir / an owner decision / `D-nnn`; in-function imports 338 in 127 functions; top-level assignments 170, 68 holding `re.compile(`; `uuid4(` called in exactly `_apply_player_damage`, `_resolve_player_death_turn`, `_start_combat_with_initiative`, `_down_outside_combat_turn`, `_migrate_legacy_combat_state`, `advance_campaign_time`; `sys.modules[__name__]` only in `_local_place_turn` and `_run_player_turn_internal`; `getLogger(__name__)` only in `_repair_dilim1_fields`, `_repair_dilim2_fields`; `locals().get("preparsed_scene_intent")` only in `_run_player_turn_internal`; non-constant defaults in `_combat_record_for_actor`, `_has_unregistered_person_name`, `_combat_end_if_decided`, `initialize_game`, `_death_save_line`, `start_terminal_game`; closed helpers 151; `legacy_debug/` scripts that `exec` `game.py` 25; `import game` sites 430; distinct `game.X` names 245; outside `game.X(..., session=...)` calls 190 on 39 names; no `game.py` row in `test_coin_writers.WRITERS`. Counts are `shifted` when they differ (BM moved the base); a named-set claim that no longer holds is `false`.
- [ ] **Step 6:** Run the tests. Expected: PASS. Then `SLOTPY inventory.py` writing the two report files. Any `false` claim: write a `Ruling` on its effect and continue; if the claim is one this plan's T1 or T2 depends on (uuid4 set, non-constant defaults, identity names), stop and report.
- [ ] **Step 7:** Add `api.tests.test_development_tooling` to this task's targeted run. Expected: `RESULT exit=0`.
- [ ] **Step 8: Commit** `game.py split T0.1: inventory, call graph, constant clusters, spec claim re-check`.

### Task 2: N1 golden surface and diff rule (spec T0.1, second half)

**Review tier:** normal. Money/save/Undo: no.

**Files:**
- Create: `ai-dnd/scripts/engine_split/surface.py`, `ai-dnd/api/tests/engine_split_locks/surface.json`
- Test: `ai-dnd/api/tests/test_engine_surface.py`

**Interfaces — Produces:**
- `snapshot(module) -> dict[str, dict]`: every key of `vars(module)` except `__builtins__`, `__doc__`, `__file__`, `__cached__`, `__spec__`, `__loader__`, `__name__`, `__package__`. Entry: `kind` (`function | class | module | data`); functions/classes add `module` (`__module__`); functions add `signature` and `session_bound` (`getattr(f, "_session_bound", False)`); data adds `type` (type name only, never the value).
- `normal_signature(fn) -> str`: `inspect.signature` text where every default that is not `None`, `bool`, `int`, `float` or `str` is written `<TypeName>`.
- `diff_rule(old: dict, new: dict, moved: set[str], added: set[str] = frozenset()) -> list[str]`: empty list = allowed. Allowed differences: `module` of a name in `moved`; presence of a name in `added`. Everything else is a violation line.
- `new_engine_functions(golden: dict, live: dict) -> list[str]`: functions whose `module == "game"` and are absent from `golden` (spec §11 name allow-list).
- CLI: `surface.py --write <path>`; `surface.py --diff --old <path> --new <path> --moved a,b --added c`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_live_surface_equals_the_golden_file(self):
    self.assertEqual(snapshot(game), json.loads(GOLDEN.read_text(encoding="utf-8")))

def test_a_missing_name_is_reported(self):
    live = dict(golden); del live["roll_d20"]
    self.assertIn("roll_d20", "\n".join(diff_rule(golden, live, moved=set())))

def test_only_the_module_of_a_moved_name_may_change(self):
    live = copy.deepcopy(golden); live["roll_d20"]["module"] = "game_parts.character_rules"
    self.assertEqual(diff_rule(golden, live, moved={"roll_d20"}), [])
    self.assertNotEqual(diff_rule(golden, live, moved=set()), [])
    live["roll_d20"]["signature"] = "(x)"
    self.assertNotEqual(diff_rule(golden, live, moved={"roll_d20"}), [])

def test_losing_the_session_wrapper_is_a_violation(self):
    live = copy.deepcopy(golden); live["roll_d20"]["session_bound"] = False
    self.assertNotEqual(diff_rule(golden, live, moved={"roll_d20"}), [])

def test_a_new_top_level_function_in_game_is_refused(self):
    live = copy.deepcopy(golden)
    live["brand_new"] = {"kind": "function", "module": "game", "signature": "()", "session_bound": True}
    self.assertEqual(new_engine_functions(golden, live), ["brand_new"])

def test_defaults_never_put_a_path_or_address_in_the_signature(self):   # Review Focus 5
    def f(a=1, b="x", p=Path("/root/x"), fn=print, n=None): ...
    self.assertEqual(normal_signature(f), "(a=1, b='x', p=<PosixPath>, fn=<builtin_function_or_method>, n=None)")
```

(On Windows the `p` default is `<WindowsPath>`; the test builds the expected text from `type(Path()).__name__`.)

- [ ] **Step 2:** Run. Expected: FAIL (`surface` missing).
- [ ] **Step 3:** Implement; generate `surface.json` with `SLOTPY surface.py --write` (sorted keys, indent 1).
- [ ] **Step 4:** Run `api.tests.test_engine_surface` + `NEIGHBOURS`, flag off and flag on (targeted, not full). Expected: both `RESULT exit=0`. If the surface differs between flags, stop and report (the golden file cannot hold two truths).
- [ ] **Step 5:** Write to the ledger: total names, function count, `session_bound` count (spec expects about 517).
- [ ] **Step 6: Commit** `game.py split T0.1: N1 golden surface and diff rule`.

### Task 3: N2 patch census (spec T0.2)

**Review tier:** normal. Money/save/Undo: no.

**Files:**
- Create: `ai-dnd/scripts/engine_split/patch_census.py`, `ai-dnd/api/tests/engine_split_locks/patch_census.json`, `docs/engine-split/patch-census.md`
- Test: `ai-dnd/api/tests/test_engine_patch_census.py`

**Interfaces — Consumes:** `surface.json` (the set of `game` names, read as data; no import of `game`).
**Produces:**
- `scan(root: Path, game_names: set[str]) -> list[dict]`; each site: `file`, `line`, `target`, `how` (`patch_string | patch_object | patch_multiple | setattr | assign`), `in_test_function`.
- Scope: every `.py` under `root` except `game.py`, `game_parts/` and `scripts/engine_split/`. Test files of this plan are scanned like any other.
- Counted: `patch("game.X"...)`; `patch.object(A, "X"...)`, `setattr(A, "X", ...)`, `patch.multiple(A, X=...)` and `A.X = ...` (module level included) where `A` is `game` or an alias from `import game as A`; when `A` cannot be resolved (parameter, fixture), the site is counted whenever `"X"` is in `game_names` or is `open`.
- `targets(sites) -> dict[str, str]`: target → `function | data | import | absent` (`absent` = not a `game` attribute, e.g. `open`).
- `not_called_tests(root) -> list[str]`: `file::test` ids that patch a `game` target and assert `assert_not_called()` on it (N4's blind spot; spec §6).
- Lock file: `{"targets": {...}, "not_called_tests": [...]}`. Counts and sites go to the report only.

- [ ] **Step 1: Measure [Y].** After Step 4, read what the scan reports for `api/ollama_adapter.py` (`install_for_engine`) and `scripts/gameplay_audit.py`; write file, line and targets in the ledger.
- [ ] **Step 2: Write the failing tests:**

```python
def test_the_lock_equals_a_fresh_scan(self):
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    sites = scan(ROOT, GAME_NAMES)
    self.assertEqual(lock["targets"], targets(sites))
    self.assertEqual(lock["not_called_tests"], not_called_tests(ROOT))

def test_an_unknown_target_is_seen(self):
    sites = scan(fixture("import game\nfrom unittest.mock import patch\n"
                         "def test_x():\n    with patch.object(game, 'brand_new_helper'):\n        pass\n"), {"roll_d20"})
    self.assertEqual([s["target"] for s in sites], ["brand_new_helper"])

def test_module_level_rebinding_outside_test_files_is_counted(self):
    sites = scan(fixture("import game\ngame.system_prompt = 'x'\n", name="live_integration_test.py"), {"system_prompt"})
    self.assertEqual((sites[0]["target"], sites[0]["how"], sites[0]["in_test_function"]), ("system_prompt", "assign", False))

def test_an_unresolved_alias_is_counted_conservatively(self):
    src = "from unittest.mock import patch\ndef helper(engine):\n    return patch.object(engine, 'roll_d20')\n"
    self.assertEqual([s["target"] for s in scan(fixture(src), {"roll_d20"})], ["roll_d20"])

def test_the_real_tree_lists_the_known_rebinders(self):
    found = {(Path(s["file"]).name, s["target"]) for s in scan(ROOT, GAME_NAMES)}
    for pair in [("live_integration_test.py", "system_prompt"), ("acceptance_test.py", "roll_d20"),
                 ("offline_test_support.py", "ollama"), ("test_sessions.py", "uuid4"),
                 ("test_dialogue_live_context.py", "open"), ("narrative_director.py", "finalize_narration")]:
        self.assertIn(pair, found)
```

- [ ] **Step 3:** Run. Expected: FAIL (`patch_census` missing).
- [ ] **Step 4:** Implement with `ast`; write the lock and the report (per-target counts, per-file counts, the `not_called_tests` list by name).
- [ ] **Step 5:** Run `api.tests.test_engine_patch_census` + `NEIGHBOURS`. Expected: `RESULT exit=0`. Write the `roll_d20` count in the ledger (spec had 283 vs 378; this is the one number).
- [ ] **Step 6: Commit** `game.py split T0.2: N2 patch census over every .py under ai-dnd`.

### Task 4: N8 sensitivity scan and the sensitive list (spec T0.7)

**Review tier:** strong (this list decides every later task's review tier). Money/save/Undo: yes.

**Files:**
- Create: `ai-dnd/scripts/engine_split/sensitivity.py`, `ai-dnd/api/tests/engine_split_locks/sensitive.json`
- Test: `ai-dnd/api/tests/test_engine_sensitivity.py`

**Interfaces — Consumes:** `top_level_index` (Task 1).
**Produces:**
- `classify(path: Path) -> dict[str, list[str]]`: top-level function → sorted reasons from `snapshot`, `save`, `file_write`, `money`; functions with no reason are absent.
- `is_sensitive(name: str, lock: dict) -> bool`.
- Lock: `{"functions": {name: [reasons]}, "removed": [{"name", "reason", "reviewer"}]}`. A name leaves `functions` only through a `removed` row written by the strong reviewer, never by an implementer, and each removal gets an approval-list row.

- [ ] **Step 1: Measure [Y].** From `GameSession` in `game.py` list the snapshot/restore method names (it has `_capture_runtime_snapshot`; find its restore twin and any other pair) and the save/load/serialise function names (`save_game`, `load_game`, `serialize_game_state` and what they call to write). Write the name sets in the ledger; they are the scan's inputs.
- [ ] **Step 2: Write the failing tests:**

```python
def test_the_six_known_names_are_listed(self):
    lock = json.loads(LOCK.read_text(encoding="utf-8"))["functions"]
    for name in ("perform_skill_check", "execute_intent", "_front_step",
                 "_thread_gate", "_run_player_turn_keyed", "finalize_narration"):
        self.assertIn(name, lock)

def test_every_flagged_function_is_in_the_lock_or_removed_with_a_reason(self):
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    removed = {row["name"] for row in lock["removed"]}
    for name, reasons in classify(GAME).items():
        self.assertTrue(name in lock["functions"] or name in removed, name)
    for row in lock["removed"]:
        self.assertTrue(row["reason"] and row["reviewer"], row)

def test_reasons_by_content_not_by_name(self):
    src = ("def tidy(world):\n    world['currency'] -= 1\n"
           "def note(s):\n    return s._capture_runtime_snapshot()\n"
           "def put(p, t):\n    p.write_text(t)\n"
           "def keep():\n    return save_game('x')\n"
           "def plain():\n    return 1\n")
    self.assertEqual(classify(write(src)), {"tidy": ["money"], "note": ["snapshot"],
                                             "put": ["file_write"], "keep": ["save"]})
```

- [ ] **Step 3:** Run. Expected: FAIL.
- [ ] **Step 4:** Implement. `money` = regex `currency|coin|gold|money_owner|pay\(` on the function's source text (spec §5); `snapshot`, `save` = an `ast.Call` whose function name or attribute is in the Step 1 sets; `file_write` = `open(` with a write mode, `write_text`, `write_bytes`, `os.replace`, `json.dump`, `tempfile.*`.
- [ ] **Step 5:** Generate the lock (`removed` empty). Run `api.tests.test_engine_sensitivity` + `NEIGHBOURS`. Expected: `RESULT exit=0`.
- [ ] **Step 6:** Ledger: list length (spec's rough figure: about 45) and, for Plans 2-5, the list grouped by the spec §5 target module.
- [ ] **Step 7: Commit** `game.py split T0.7: N8 sensitivity scan and sensitive list`.

### Task 5: N5 `move_check` (spec T0.4)

**Review tier:** normal. Money/save/Undo: no.

**Files:**
- Create: `ai-dnd/scripts/engine_split/move_check.py`
- Test: `ai-dnd/api/tests/test_engine_move_check.py`

**Interfaces — Consumes:** `top_level_index`, `is_sensitive`.
**Produces:**
- `check_move(base_root: Path, new_root: Path, moved: dict[str, str], sensitive: dict, tier: str, manual: list[str] = []) -> dict` with `changed` (list of human-readable findings; empty = equivalent), `comments_base`, `comments_now`, `manual` (echoed, each tagged "mekanik değil"). `base_root` and `new_root` are folders holding `game.py` and, when present, `game_parts/`; `moved` maps a name to its part file name.
- `comment_counts(base_root: Path, new_root: Path) -> tuple[int, int]`: `tokenize.COMMENT` totals over `game.py` + all parts on each side.
- For every moved name, all three must hold: (a) `ast.dump` of the moved block equals the base block's after every `game.<X>` attribute read is folded back to the bare name `X`; (b) the `tokenize` stream as `(type, string)` pairs, comments and docstrings included, equals the base block's after dropping each added `game` `.` pair; `NEWLINE`/`NL` are compared by type only; (c) the block starts at `start` from `top_level_index` (the comment lines directly above travel with it), and `comments_now` equals `comments_base`.
- Also: every changed line of `game.py` is a deletion or a `from game_parts.<x> import ...` line, except lines named in `manual` (`"file:line:reason"`); a moved name that `is_sensitive` with `tier != "strong"` is a finding.
- CLI: `move_check.py --base-root <dir> --root . --moved name=part.py,... --tier normal|strong [--manual "file:line:reason" ...]`; prints `CHANGED <n>`; exit 1 when `n > 0`. `move_check.py --comments-only --base-root <dir> --root .` prints `COMMENTS base=<n> now=<n>`; exit 1 when they differ.
- The base folder is made with `git archive origin/main ai-dnd/game.py ai-dnd/game_parts | tar -x -C <dir>` (drop `ai-dnd/game_parts` while the package does not exist on `main`).
- **Rule (spec §6):** `CHANGED` above zero is never patched forward; the move is redone from scratch.

- [ ] **Step 1: Write the failing tests** (each builds a base `game.py`, a new `game.py` and one part in a temp dir):

```python
BASE = "K = 1\n\n# why roll exists (D-123)\ndef roll():\n    return helper() + K  # keep\n\ndef helper():\n    return 2\n"
GOOD_GAME = "K = 1\n\nfrom game_parts.dice import roll\n\ndef helper():\n    return 2\n"
GOOD_PART = "import game\n\n# why roll exists (D-123)\ndef roll():\n    return game.helper() + game.K  # keep\n"

def test_a_clean_move_is_equivalent(self):            # changed == []
def test_a_changed_operator_is_reported(self):        # part has `-` for `+`  -> changed
def test_a_deleted_comment_is_reported(self):         # part drops "# keep" -> changed, comments_now == comments_base - 1
def test_a_dropped_leading_comment_is_reported(self): # part drops "# why roll exists (D-123)" -> changed
def test_ast_unparse_output_is_reported(self):        # part body = ast.unparse(...) of the function -> changed (token stream)
def test_an_extra_edit_in_game_py_is_reported(self):  # new game.py also changes helper's body -> changed
def test_a_sensitive_name_needs_the_strong_tier(self):# sensitive={"functions": {"roll": ["money"]}}: tier "normal" -> changed; "strong" -> []
def test_crlf_and_lf_give_the_same_verdict(self):     # Review Focus 4: same three files with \r\n -> changed == []
def test_a_manual_line_in_game_py_is_exempt_and_echoed(self):
    # new game.py also changes `K = 1` to `K = 2`: changed non-empty; with manual=["game.py:1:test"] -> changed == [], manual == ["game.py:1:test"]
def test_comment_counts_cover_game_py_and_every_part(self):
    # base: game.py with 2 comments; new: game.py with 1 + part with 1 -> (2, 2)
```

Each named test asserts exactly the outcome in its comment.

- [ ] **Step 2:** Run. Expected: FAIL (`move_check` missing).
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `api.tests.test_engine_move_check` + `NEIGHBOURS`. Expected: `RESULT exit=0`.
- [ ] **Step 5: Commit** `game.py split T0.4: N5 move_check (AST, token stream, comment count, sensitive list)`.

### Task 6: In-place move tool

**Review tier:** normal (its output is judged by `move_check` and by the task's reviewer on every use). Money/save/Undo: no.

**Files:**
- Create: `ai-dnd/scripts/engine_split/move_block.py`
- Test: `ai-dnd/api/tests/test_engine_move_tool.py`

**Interfaces — Consumes:** `top_level_index`, the census lock's `targets`.
**Produces:**
- `prefix_names(block: str, engine_names: set[str], keep_bare: set[str]) -> tuple[str, list[tuple[int, int, str]]]`: inserts the six characters `game.` before each free reference (global scope per `symtable`) to a name in `engine_names - keep_bare`, using `tokenize` positions; returns the text and the insertions `(line, col, name)`. No other byte changes.
- `move(game_py: Path, part_py: Path, names: list[str], surface_targets: set[str]) -> dict`: cuts each block (`start`..`end` from `top_level_index`) byte for byte, appends it to the part, applies `prefix_names`, and puts one `from game_parts.<part> import <names>` line where the first cut block began (so `globals()` order, and with it `_ENGINE_FUNCTIONS` order, is unchanged). Returns the spans and insertions.
- Which names get the prefix: every engine top-level function or class (same-part ones and self-recursion included), every name in `surface_targets`, and every constant that does not live in the destination part. Constants that live in the destination part and are not in `surface_targets` stay bare (N3 rule 5).
- Refusals (raise `MoveRefused` with the reason): the block reads bare `open`; an engine name appears in a default argument or decorator (N3 rule 4); the block contains `__file__`, `__name__`, `globals(`, `locals(`, `vars(`, `sys.modules` (N3 rule 6).
- The part's header (`import game` and the stdlib / non-engine imports the block needs) is written by hand and reported to `move_check` as manual.

- [ ] **Step 1: Write the failing tests:**

```python
def test_only_free_engine_names_get_the_prefix(self):
    block = "def roll(messages):\n    random = _session().rng\n    return random.randint(1, K) + len(messages) + obj.helper\n"
    out, ins = prefix_names(block, {"_session", "K", "helper", "messages", "random"}, keep_bare=set())
    self.assertEqual(out, "def roll(messages):\n    random = game._session().rng\n"
                          "    return random.randint(1, game.K) + len(messages) + obj.helper\n")
    self.assertEqual([name for _, _, name in ins], ["_session", "K"])

def test_same_part_constants_stay_bare_but_surface_names_never_do(self):
    out, _ = prefix_names("def f():\n    return RX.match(CLASSES)\n", {"RX", "CLASSES"}, keep_bare={"RX"})
    self.assertEqual(out, "def f():\n    return RX.match(game.CLASSES)\n")

def test_comments_strings_and_line_endings_are_untouched(self):       # Review Focus 4
    block = "# K is the cap\r\ndef f():\r\n    return 'K' + str(K)  # K\r\n"
    out, _ = prefix_names(block, {"K"}, keep_bare=set())
    self.assertEqual(out, "# K is the cap\r\ndef f():\r\n    return 'K' + str(game.K)  # K\r\n")

def test_move_leaves_one_import_line_at_the_old_position(self):
    # game.py: "A = 1\n\n# c\ndef f():\n    return A\n\ndef g():\n    return f()\n"; move(["f"])
    # -> game.py == "A = 1\n\nfrom game_parts.p import f\n\ndef g():\n    return f()\n"
    # -> part ends with "# c\ndef f():\n    return game.A\n"

def test_refusals(self):
    # bare open(...) in the block; `def f(x=K)`; `__file__` in the block -> MoveRefused each
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Text is read and written in binary and decoded as UTF-8 so line endings survive.
- [ ] **Step 4:** Add one round-trip test: `move` on the Task 5 `BASE` fixture, then `check_move(...)["changed"] == []`.
- [ ] **Step 5:** Run `api.tests.test_engine_move_tool api.tests.test_engine_move_check` + `NEIGHBOURS`. Expected: `RESULT exit=0`.
- [ ] **Step 6: Commit** `game.py split T0: in-place move tool (tokenize positions, no source regeneration)`.

### Task 7: N6 `engine_source_files()` and the source-reading tests (spec T0.3)

**Review tier:** strong (boundaries are redefined). Money/save/Undo: per test; `test_coin_writers.py` is not touched.

**Files:**
- Create: `ai-dnd/api/tests/engine_sources.py`, `docs/engine-split/source-readers.md`
- Test: `ai-dnd/api/tests/test_engine_sources.py`
- Modify: each class-A test found in Step 1 (expected to include `api/tests/test_talk_mode_writers.py`, `api/tests/test_narration_source_record.py`, `test_combat_v2_authoritative.py`, `api/tests/test_exits.py`)
- Modify: `docs/agents/onay-listesi-20261115.md`

**Interfaces — Produces:**
- `engine_source_files(root: Path = ENGINE_ROOT) -> list[Path]`: `[root / "game.py"] + sorted((root / "game_parts").glob("*.py"))`; a missing `game_parts` gives only `game.py`.
- `engine_source_text(root: Path = ENGINE_ROOT) -> str`: the files' texts joined with `"\n"`.

- [ ] **Step 1: Measure [Y].** List every test file under `ai-dnd` that mentions `game.__file__`, `"game.py"`, `inspect.getsource(game` or globs `*.py` in the engine folder (the quick search on 2026-11-17 found 25 files). Classify each in `source-readers.md`: **A** reads engine text or AST to assert something about engine code; **B** uses the path only to find a folder; **C** executes the file (`runpy`, `exec`, subprocess: left for Task 12). Only A changes. For each A test, write its present form (text search, AST walk, writer count).
- [ ] **Step 2: Write the failing helper tests:**

```python
def test_without_a_package_only_game_py_is_listed(self):      # temp root with game.py only -> [root/"game.py"]
def test_parts_follow_game_py_in_name_order(self):            # game_parts/b.py, a.py -> [game.py, a.py, b.py]
def test_the_real_list_starts_with_the_engine_file(self):     # engine_source_files()[0].name == "game.py"
```

- [ ] **Step 3:** Run (FAIL), implement, run (PASS).
- [ ] **Step 4:** For each A test, one at a time: (i) run it green; (ii) rewrite it to read `engine_source_files()` / `engine_source_text()` with every assertion kept at equal strictness; (iii) **seeded-violation proof:** point the helper at a temp root holding a copy of `game.py` plus a fake `game_parts/x.py` containing the exact text or call the test forbids, and show the test fails; record the failing line in the ledger; (iv) add an approval-list row, marked "gevşetme olabilir" when the scanned set changed.
- [ ] **Step 5:** `test_exits.OnlyExitsReadsTests.test_only_exits_reads_the_exit_fields` scans `root.glob("*.py")`: extend the scanned set with `engine_source_files()`'s parts, keep the skip rules, give it its own seeded proof and approval-list row.
- [ ] **Step 6:** Run every modified module + `api.tests.test_engine_sources api.tests.test_coin_writers` + `NEIGHBOURS`. Expected: `RESULT exit=0`; `test_coin_writers.py` has no diff.
- [ ] **Step 7: Commit** `game.py split T0.3: N6 engine_source_files and source-reading tests bound to it`.

### Task 8: Size latch (spec T0.6, §11)

**Review tier:** normal. Money/save/Undo: no.

**Files:**
- Create: `ai-dnd/api/tests/test_engine_size_budget.py`, `ai-dnd/api/tests/engine_split_locks/size_budget.json`

**Interfaces — Consumes:** `engine_source_files`, `top_level_index`.
**Produces:**
- Lock: `{"files": {"game.py": <lines today>}, "part_max": 2500, "slack": 50, "long_function_min": 150, "long_functions": {name: lines}}`.
- `budget_findings(actual: dict[str, int], lock: dict) -> list[str]`: a file over its budget; a budget more than `slack` above the real size; a part without a `files` entry that exceeds `part_max`.
- `long_function_findings(actual: dict[str, int], lock: dict) -> list[str]`: a function of `long_function_min` lines or more that is absent from `long_functions`, or longer than its entry.
- Raising any number needs an approval-list row and Kadir (spec decision 10); lowering does not.

- [ ] **Step 1: Write the failing tests:**

```python
def test_the_engine_fits_its_budget(self):
    self.assertEqual(budget_findings(real_sizes(), LOCK), [])
    self.assertEqual(long_function_findings(real_function_lengths(), LOCK), [])

def test_one_line_over_is_red(self):
    self.assertNotEqual(budget_findings({"game.py": LOCK["files"]["game.py"] + 1}, LOCK), [])

def test_a_budget_cannot_hoard_room(self):
    self.assertNotEqual(budget_findings({"game.py": LOCK["files"]["game.py"] - 51}, LOCK), [])
    self.assertEqual(budget_findings({"game.py": LOCK["files"]["game.py"] - 50}, LOCK), [])

def test_a_part_may_not_pass_2500_lines(self):
    self.assertNotEqual(budget_findings({"game.py": LOCK["files"]["game.py"], "game_parts/x.py": 2501}, LOCK), [])

def test_long_functions_cannot_grow_or_appear(self):
    self.assertNotEqual(long_function_findings({"brand_new": 150}, LOCK), [])
    grown = {"_run_player_turn_internal": LOCK["long_functions"]["_run_player_turn_internal"] + 1}
    self.assertNotEqual(long_function_findings(grown, LOCK), [])
```

- [ ] **Step 2:** Run (FAIL: lock file missing), write the lock from the real sizes, run `api.tests.test_engine_size_budget` + `NEIGHBOURS`. Expected: `RESULT exit=0`.
- [ ] **Step 3: Commit** `game.py split T0.6: size latch (game.py cannot grow)`.

### Task 9: N4 patch-hit ledger, N7 coverage, fixed turn benchmark (spec T0.5)

**Review tier:** normal. Money/save/Undo: no.

**Files:**
- Create: `ai-dnd/scripts/engine_split/probe_boot.py`, `ledger_diff.py`, `coverage_by_function.py`
- Create: `ai-dnd/api/tests/bench_engine_turn.py`
- Test: `ai-dnd/api/tests/test_engine_probe_tools.py`

**Interfaces — Produces:**
- `probe_boot.start()`: does nothing unless `/root/aidnd-env-<SLOT>/engine-split-probe.json` exists (`{"ledger": bool, "coverage": bool, "out": "<dir>"}`). With `ledger`, it wraps `unittest.mock._patch.__enter__/__exit__` and `unittest.TestCase.run`; for every patch whose target object is the `game` module it writes one JSON line `{"test", "target", "kind", "called"}` at exit, also when the test raised. `test` is the running test id, or `<outside-test>:<file name>`. `kind` is `mock` (then `called` is the mock's `.called`) or `other` (`called` is `null`). With `coverage`, it starts `coverage` limited to `game.py` and `game_parts/*`, parallel data files in `out`.
- `merge_ledger(lines_dir: Path) -> dict[str, bool | None]` keyed `"<test>|<target>"` (`True` if any record was called).
- `noise(a: dict, b: dict) -> list[str]`: keys whose values differ between two runs of the same code.
- `drops(base: dict, new: dict, noise_keys: set[str]) -> list[str]`: keys `True` in `base` and not `True` in `new`, minus noise. Gate rule: empty.
- `function_hits(coverage_json: Path, index: dict[str, list[dict]]) -> dict[str, int]`: top-level function name → number of executed lines, summed over `game.py` and parts by function name.
- `unequal(base: dict[str, int], new: dict[str, int], noise_names: set[str]) -> list[str]`.
- `api.tests.bench_engine_turn`: one `unittest` case that, inside `fixed_town(self, 20261117)`, creates `game.create_session(seed=20261117)`, replaces the model with the offline fake, plays the same command list five times on five fresh sessions and prints `TURN_BENCH median_ms_per_turn=<x> turns=<n>`.

- [ ] **Step 1: Measure [Y].** Read `tools/acceptance/linux_guard/sitecustomize.py` and (via `wsl.exe ... head -80`) `/root/aidnd-env-<SLOT>/linux_guarded_launcher.py`. Answer in the ledger: how test processes are started (flags such as `-I`/`-S`, environment scrubbing), whether a `.pth` file in `proj/.venv` site-packages is processed, whether writes under the slot root are allowed, whether `coverage` is importable.
- [ ] **Step 2: Decide by the measurement.** Feasible: install the pinned `coverage` (approved in Task 0) and one `.pth` line that calls `probe_boot.start()`; with no flag file it must do nothing. Not feasible: write "N4/N7 kurulamadı" with the reason in the ledger, tell Kadir, and continue with N3 + full suite as the spec allows (§9); the T2 gate then cannot give the N4 proof and that is said in the PR text.
- [ ] **Step 3: Write the failing tests** for the pure functions:

```python
def test_merge_keeps_true_over_false(self):   # two lines same key, called False then True -> True
def test_noise_is_what_two_equal_runs_disagree_on(self):
    self.assertEqual(noise({"t|roll_d20": True, "u|x": True}, {"t|roll_d20": True, "u|x": False}), ["u|x"])
def test_a_patch_that_stopped_firing_is_a_drop(self):
    self.assertEqual(drops({"t|roll_d20": True}, {"t|roll_d20": False}, set()), ["t|roll_d20"])
    self.assertEqual(drops({"t|roll_d20": True}, {}, set()), ["t|roll_d20"])
    self.assertEqual(drops({"t|roll_d20": True}, {"t|roll_d20": False}, {"t|roll_d20"}), [])
def test_function_hits_follow_the_function_across_files(self):
    # coverage json: game.py executed lines [2, 3]; index {"game.py": [{"name": "f", "def_line": 1, "end": 3}]} -> {"f": 2}
def test_unequal_ignores_only_the_noise_names(self):
    self.assertEqual(unequal({"f": 3, "g": 2}, {"f": 2, "g": 1}, {"g"}), ["f"])
def test_a_record_is_written_when_the_test_body_raises(self):
    # run a tiny TestCase in-process with the ledger wrapper active and a temp out dir: patch.object(fake_game, "x") then raise
    # -> one line, called False
```

- [ ] **Step 4:** Run (FAIL), implement, run (PASS).
- [ ] **Step 5: Benchmark scenario [Y].** Read `offline_test_support.py` and the first scenario used by `api.tests.test_journeys`; reuse that scenario's command list (at least 10 commands) and its fake-model setup. Pin the list in `bench_engine_turn.py` as a tuple. Ruling to record: which scenario was chosen.
- [ ] **Step 6:** Smoke: with the flag file set to ledger only, run `api.tests.test_engine_surface test_regression` through `slot.sh`; expect `RESULT exit=0` and a non-empty ledger containing `roll_d20` keys. Run `api.tests.bench_engine_turn` twice; expect two `TURN_BENCH` lines in the run's `target.log`; record both. Remove the flag file.
- [ ] **Step 7:** Run `api.tests.test_engine_probe_tools` + `NEIGHBOURS` with no flag file. Expected: `RESULT exit=0` and no ledger output (the probe is off by default).
- [ ] **Step 8: Commit** `game.py split T0.5: N4 patch-hit ledger, N7 per-function coverage, fixed turn benchmark`.

### Task 10: Gate TM0 and PR 1

**Review tier:** whole-branch review on the strongest model before the PR. Ruling: every PR of this plan gets one — each PR lands on `main` by itself — if wrong: cost is one extra review per PR.

- [ ] **Step 1:** `git fetch origin`. If `origin/main` moved, merge it, then regenerate `surface.json`, `patch_census.json`, `sensitive.json`, `size_budget.json` and rerun Tasks 1-8's test modules + `NEIGHBOURS`.
- [ ] **Step 2: Baselines, one run at a time.** Per flag setting, three full suites: A = ledger on, coverage off (the timed run and the gate run); B and C = ledger and coverage on. Six runs in total. Ruling: three per flag instead of the spec's two — the time base must not carry coverage overhead and N7 needs two coverage runs — if wrong: about one hour of machine time. Every run: `PAR_EXIT=0`.
- [ ] **Step 3:** Compute and store under `AI-DND-TOOLS/measure/engine-split/` (copy in `.local/engine-split/`): per flag `ledger-base.json`, `ledger-noise.json` (`noise` over A, B, C pairwise), `coverage-base.json`, `coverage-noise.json` (`unequal` of B vs C), suite seconds of run A; plus the turn benchmark run twice. Write all numbers and both noise-set sizes in the ledger.
- [ ] **Step 4:** Whole-branch review; fix findings red-first.
- [ ] **Step 5:** Ask Kadir for push + PR approval. After the push: `gh run list --repo kadirkayarr-beep/AI-DND --limit 5` until "AI-DND bounded verification" is green. Ask Kadir for the merge. After the merge check CI on `main` again.
- [ ] **Step 6:** Five-line Turkish morning summary; ledger line "TM0 geçti".

---

# Stage T1 — single copy (worktree `AI-DND-k2-bolme-t1`, PR 2). This is a code change, not a pure move.

### Task 11: Terminal entry hands over `input_fn`/`print_fn` at call time; loop moves to `terminal.py` (spec T1.1)

**Review tier:** strong. Money/save/Undo: yes (the loop calls `save_game` and `load_game`).

**Files:**
- Create: `ai-dnd/game_parts/__init__.py` (one line: `import game`), `ai-dnd/game_parts/terminal.py`
- Modify: `ai-dnd/game.py` (new guard as the first statement; the old `if __name__ == "__main__":` block at the end of the file is removed), `ai-dnd/api/tests/engine_split_locks/size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_single_copy.py`

**Interfaces — Produces:**
- `game_parts.terminal.run(input_fn, print_fn) -> int`: returns 0 when the player declines to start or leaves the loop.
- `game.py`, first statement of the file:

```python
if __name__ == "__main__":
    import game
    from game_parts import terminal
    raise SystemExit(terminal.run(input_fn=input, print_fn=print))
```

- `start_terminal_game(input_fn=input, print_fn=print, save_path=DEFAULT_SAVE_PATH)` and `DEFAULT_SAVE_PATH` stay in `game.py` with unchanged signature and value. `run` calls `game.start_terminal_game(input_fn=input_fn, print_fn=print_fn)`.
- The loop body is the old block's text with only these edits: engine names get `game.` (`roll_d20`, `SKILLS`, `_session`, `perform_skill_check`, `run_player_turn`, `messages`, `save_game`, `load_game`, `DEFAULT_SAVE_PATH`), `input(` becomes `input_fn(`, `print(` becomes `print_fn(`, `raise SystemExit(0)` becomes `return 0`, and `return 0` is added after the loop. Every comment line of the old block is kept verbatim.

- [ ] **Step 1: Write the failing tests** (`ROOT = Path(__file__).resolve().parents[2]`):

```python
def test_a_terminal_run_uses_the_engine_that_is_already_imported(self):
    # inside fixed_town(self, 20261118); snapshot the default session first and restore it in finally
    # (GameSession._capture_runtime_snapshot and its restore twin)
    answers = iter((["1"] if game.DEFAULT_SAVE_PATH.is_file() else []) + ["2", "SkillHero", "/skill stealth 15", "çık"])
    out = io.StringIO()
    with patch("builtins.input", lambda prompt="": next(answers)), patch("sys.stdout", out):
        with self.assertRaises(SystemExit) as stop:
            runpy.run_path(str(ROOT / "game.py"), run_name="__main__")
    self.assertEqual(stop.exception.code, 0)
    self.assertIn("🎲 SKILL CHECK", out.getvalue())
    self.assertIn("Skill: Stealth", out.getvalue())
    self.assertEqual(game._session().character["name"], "SkillHero")   # red today: the second copy got the hero

def test_the_main_guard_is_first_and_always_exits(self):
    def is_main_guard(node):      # `if __name__ == "__main__":` (Eq only; the `!=` block further down is not one)
        t = getattr(node, "test", None)
        return (isinstance(node, ast.If) and isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
                and t.left.id == "__name__" and isinstance(t.ops[0], ast.Eq)
                and getattr(t.comparators[0], "value", None) == "__main__")
    body = ast.parse((ROOT / "game.py").read_text(encoding="utf-8")).body
    self.assertTrue(is_main_guard(body[0]))
    self.assertIsInstance(body[0].body[-1], ast.Raise)
    self.assertEqual(sum(is_main_guard(n) for n in body), 1)

def test_the_default_save_path_stays_under_ai_dnd_saves(self):          # green today; pinned
    self.assertEqual(game.DEFAULT_SAVE_PATH, ROOT / "saves" / "adventure.json")

def test_terminal_save_and_load_use_the_given_path(self):               # Review Focus 2
    # same harness as the first test; answers: [...start..., f"/save {tmp}", f"/load {tmp}", "çık"]
    # assert tmp.is_file(); "Oyun kaydedildi:" and "Oyun yüklendi:" in output; nothing was created under ROOT/"game_parts"/"saves"

def test_the_terminal_starts_from_another_working_directory(self):      # Review Focus 1
    # subprocess: [sys.executable, str(ROOT/"game.py")], cwd=<temp dir>, input="2\nzar at\nexit\n", timeout=60, utf-8 env
    # assert returncode == 0 and "D20 sonucu:" in stdout; print(f"TERMINAL_CHILD_SECONDS={elapsed:.2f}")

def test_closed_stdin_ends_the_terminal_promptly(self):                 # Review Focus 3
    # subprocess with input="" and timeout=60: it returns; returncode equals the value measured in Step 2
```

- [ ] **Step 2: Measure [Y] before changing code.** Run `api.tests.test_engine_single_copy` + `NEIGHBOURS`. Expected: the first two tests FAIL; the save-path test passes. Record `TERMINAL_CHILD_SECONDS` (the cost of today's double execution) and the closed-stdin exit code; pin that code in the last test.
- [ ] **Step 3: Seeded proof for the save-path pin.** In the working tree only, point `DEFAULT_SAVE_PATH` at `... / "game_parts" / "saves" / "adventure.json"`, run the test, see it FAIL, restore the line. Record in the ledger.
- [ ] **Step 4:** Make the change described under Interfaces. Lower `size_budget.json` `game.py` to the new line count + 10. Ruling: +10 stays inside the approved 50-line slack and covers Task 14's two lines — if wrong: nothing, the latch still bites at +50.
- [ ] **Step 5:** `SLOTPY move_check.py --comments-only --base-root <dir> --root .`. Expected: `COMMENTS base=<n> now=<n>`, equal. List every hand-edited line of the loop in the ledger as "mekanik değil". The reviewer diffs the old block against `terminal.py` with the three substitutions undone (`game.` removed, `input_fn(` back to `input(`, `print_fn(` back to `print(`) and must find no other difference.
- [ ] **Step 6:** Run `api.tests.test_engine_single_copy api.tests.test_engine_surface api.tests.test_engine_size_budget api.tests.test_engine_patch_census test_sessions test_regression` + every module Task 7 modified + `NEIGHBOURS`. Expected: the new tests PASS; `test_sessions` `test_terminal_initialization_dice_and_exit` passes unchanged; `test_engine_surface` passes with **no** golden change; the only expected failure is `test_regression.test_terminal_skill_command` (the run now ends in `SystemExit`, so its `mod` is never bound; Task 12 owns it and the ledger names it). The `exec` test in `test_sessions` still passes here; Task 12 retires it because an `exec` copy becomes half copy, half real module as soon as parts exist. Any other failure: trace it, do not accept it. Record the new `TERMINAL_CHILD_SECONDS`.
- [ ] **Step 7: Commit** `game.py split T1.1: terminal entry passes input/print at call time; loop lives in game_parts/terminal.py`.

### Task 12: Rewrite the `runpy` test; retire the `exec` contract (spec T1.2)

**Review tier:** strong. Money/save/Undo: yes (state/save input).

**Files:**
- Modify: `ai-dnd/test_regression.py` (`test_terminal_skill_command`), `ai-dnd/test_sessions.py` (`test_exec_namespace_scalars_are_not_a_state_input`)
- Modify: `docs/agents/onay-listesi-20261115.md`, `docs/agents/debt-register.md`
- Modify (only after Kadir's yes): the two comment lines above the `_GameModule` class swap in `ai-dnd/game.py`

- [ ] **Step 1: Measure [Y].** (a) Is `"current_hp"` a key of `game.__dict__`? (b) Which tests, if any, run a `legacy_debug/` script (search test files for `legacy_debug`)? Record both.
- [ ] **Step 2:** Rewrite `test_terminal_skill_command` against the one module, equal strictness: same inputs and the same three output assertions; `runpy.run_path(..., run_name="__main__")` now ends in `SystemExit(0)` (assert it); the character is read from `engine._session().character` instead of `mod["_session"]()`; add `assert sys.modules["game"] is engine`; restore the default session afterwards. Leave `isolated_model` untouched.
- [ ] **Step 3:** Replace the `exec` test with `test_module_scalars_are_not_a_state_input_for_another_session`, inside `fixed_town(self, 20261119)`:

```python
session = game.create_session(seed=17)
before = session.serialize_game_state()
default_before = game.serialize_game_state()
try:
    game.current_hp = 0
    game.character_name = "Unowned character"
    self.assertEqual(session.serialize_game_state(), before)
    session.character["current_hp"] = 2
    self.assertEqual(session.serialize_game_state()["player"]["current_hp"], 2)
    self.assertEqual(game.serialize_game_state(session=session), session.serialize_game_state())
    self.assertNotIn("current_hp", vars(game))          # keep only if Step 1 (a) measured False
finally:
    # put the default session's hp and name back; then
    self.assertEqual(game.serialize_game_state(), default_before)
```

- [ ] **Step 4:** Approval-list rows: the `runpy` test ("tek modüle karşı yeniden yazıldı; eşit sıkılık"), and the `exec` test with the exact mark **"sözleşme kaldırıldı, gevşetme"** (spec §7, decision 1). Proposed new comment text for `game.py`, as a third row awaiting Kadir: `# Imported modules retain live character aliases. The engine file is never` / `# run as a second copy (exec, runpy); the terminal entry delegates here.` Do not edit the comment until Kadir says yes; the comment count stays the same either way.
- [ ] **Step 5:** Debt rows (8 `|` each): the `legacy_debug/` scripts that `exec` `game.py` are "bölmeden sonra güvenilmez", not fixed (use the count Task 1 measured); `isolated_model` still patches `sys.modules["ollama"]` for a second copy that no longer exists.
- [ ] **Step 6:** Regenerate `patch_census.json` if the scan changed and explain each added or removed target in the ledger. Run `test_regression test_sessions api.tests.test_engine_single_copy api.tests.test_engine_patch_census api.tests.test_engine_surface` + `NEIGHBOURS`. Expected: `RESULT exit=0`.
- [ ] **Step 7: Commit** `game.py split T1.2: terminal test runs against the single engine; exec second-copy contract retired`.

### Task 13: Gate after T1 and PR 2

**Review tier:** whole-branch review on the strongest model.

Ruling: the spec has no milestone between TM0 and TM1, but the controller requires one worktree and PR per stage and T1 changes how the engine starts — full suite ×2 here — if wrong: one hour of machine time.

- [ ] **Step 1:** `git fetch origin`; merge `origin/main` if it moved (the freeze should make this a no-op for `game.py`).
- [ ] **Step 2:** Full suite flag off, then flag on, ledger on, coverage off. Both `PAR_EXIT=0`.
- [ ] **Step 3:** `drops(base, new, noise)` per flag. Expected: empty, except keys of the two tests Task 12 rewrote (name them in the ledger). Suite seconds and turn benchmark recorded against the TM0 base.
- [ ] **Step 4:** Whole-branch review; fix red-first. Ask Kadir: push + PR, the comment wording from Task 12, then merge. CI green after each.
- [ ] **Step 5:** Five-line morning summary; ledger line "T1 kapısı geçti".

---

# Stage T2 — wrapper, hash, pilot (worktree `AI-DND-k2-bolme-t2`, PR 3)

### Task 14: `_PART_MODULES` in the wrapper filter (spec T2.1)

**Review tier:** strong. Money/save/Undo: yes (session binding).

**Files:**
- Modify: `ai-dnd/game.py` (the `_ENGINE_FUNCTIONS` expression and one new line above it), `ai-dnd/api/tests/engine_split_locks/surface.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

**Interfaces — Produces:** `game._PART_MODULES: tuple[str, ...]` (empty here) and the filter `value.__module__ == __name__ or value.__module__ in _PART_MODULES`.

- [ ] **Step 1: Write the failing test:**

```python
def test_the_wrapper_filter_reads_an_explicit_part_list(self):
    self.assertEqual(game._PART_MODULES, ())          # Task 18 changes this expected value
    tree = ast.parse(engine_source_files()[0].read_text(encoding="utf-8"))
    assign = next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "_ENGINE_FUNCTIONS")
    self.assertIn("_PART_MODULES", {n.id for n in ast.walk(assign) if isinstance(n, ast.Name)})
```

- [ ] **Step 2:** Run. Expected: FAIL, `AttributeError: _PART_MODULES`.
- [ ] **Step 3:** Add `_PART_MODULES = ()` directly above `_ENGINE_FUNCTIONS` and widen the filter. No star import anywhere.
- [ ] **Step 4:** Save the old golden (`git show origin/main:ai-dnd/api/tests/engine_split_locks/surface.json`), regenerate, then `SLOTPY surface.py --diff --old <old> --new <new> --moved "" --added _PART_MODULES`. Expected: no violation; the `session_bound` set is identical.
- [ ] **Step 5:** Run `api.tests.test_engine_parts_pilot api.tests.test_engine_surface api.tests.test_engine_size_budget test_sessions` + `NEIGHBOURS`. Expected: `RESULT exit=0`.
- [ ] **Step 6: Commit** `game.py split T2.1: bound-session wrapper filter reads an explicit _PART_MODULES list (empty)`.

### Task 15: `engine_hash` over the engine file set (spec T2.2)

**Review tier:** strong. Money/save/Undo: yes (save metadata).

**Files:**
- Modify: `ai-dnd/api/persistence/campaign_store.py` (`_engine_hash`, new module-level helpers)
- Test: `ai-dnd/api/tests/test_engine_hash_parts.py`

**Interfaces — Produces:**
- `campaign_store._engine_files(game_file: Path) -> list[Path]`: `[game_file] + sorted((game_file.parent / "game_parts").glob("*.py"))`.
- `campaign_store._engine_digest(game_file: Path) -> str`: sha256 over, for each file in order, `<name relative to game_file.parent, posix>` + `b"\0"` + file bytes + `b"\0"`.
- `_engine_hash()` returns `_engine_digest(Path(game.__file__).resolve())` and keeps its `OSError -> CampaignStorageError` handling.

- [ ] **Step 1: Measure [Y].** Confirm `engine_hash` is written and never compared: list every read of the column in product code (spec: none). If a comparison exists, stop and report.
- [ ] **Step 2: Write the failing tests** on a temp folder with `game.py` and `game_parts/a.py`, `game_parts/b.py`:

```python
def test_changing_a_part_changes_the_hash(self):
def test_adding_a_part_changes_the_hash(self):
def test_renaming_a_part_changes_the_hash(self):
def test_changing_game_py_changes_the_hash(self):
def test_the_hash_is_stable_for_the_same_files(self):
def test_product_and_test_helper_list_the_same_files(self):
    self.assertEqual(campaign_store._engine_files(ROOT / "game.py"), engine_source_files())
def test_a_missing_engine_file_is_a_storage_error(self):
    with patch.object(campaign_store, "_engine_digest", side_effect=OSError):
        with self.assertRaises(campaign_store.CampaignStorageError):
            campaign_store.CampaignStore._engine_hash()
```

(Use the store class's real name from `campaign_store.py`.)

- [ ] **Step 3:** Run. Expected: FAIL (`_engine_digest` missing).
- [ ] **Step 4:** Implement.
- [ ] **Step 5:** Run `api.tests.test_engine_hash_parts api.tests.test_campaign_persistence api.tests.test_campaign_ownership api.tests.test_campaign_ownership_schema_migration api.tests.test_startup_safety` + `NEIGHBOURS`. Expected: `RESULT exit=0`.
- [ ] **Step 6: Commit** `game.py split T2.2: engine_hash covers game.py and game_parts`.

### Task 16: Path guards know `game_parts` (spec T2.3)

**Review tier:** normal. Money/save/Undo: no.

**Files:**
- Modify: `ai-dnd/scripts/development_archive.py` (the "Archive cannot contain verifier source" path tuple), `ai-dnd/scripts/development_checks.py` (`owners` list and the protected-change detection), `ai-dnd/scripts/security_gate.py` if Step 1 finds an engine path in it
- Test: `ai-dnd/api/tests/test_development_tooling.py`

- [ ] **Step 1: Measure [Y].** Find where `ai-dnd/game.py` becomes a protected path (search for `protected_changes`) and whether `security_gate.py` names the engine file at all. Record the functions.
- [ ] **Step 2: Write the failing tests** next to the existing `game.py` cases in `test_development_tooling.py`, same shape: a change to `ai-dnd/game_parts/terminal.py` appears in `scope["detail"]["protected_changes"]`; an archive root that contains `ai-dnd/game_parts` raises `ValueError("Archive cannot contain verifier source")`; the "Architecture structure" row needs `ai-dnd/game_parts` to exist.
- [ ] **Step 3:** Run (FAIL), add `game_parts` beside every `game.py` entry found in Step 1, run `api.tests.test_development_tooling` + `NEIGHBOURS`. Expected: `RESULT exit=0`.
- [ ] **Step 4: Commit** `game.py split T2.3: path guards cover ai-dnd/game_parts`.

### Task 17: N3 routing audit (spec T2.4, first part)

**Review tier:** strong. Money/save/Undo: no.

**Files:**
- Create: `ai-dnd/scripts/engine_split/routing_audit.py`, `ai-dnd/api/tests/engine_split_locks/allowed_imports.json`, `ai-dnd/api/tests/engine_split_locks/identity_allowlist.json` (`[]`)
- Test: `ai-dnd/api/tests/test_engine_routing.py`

**Interfaces — Consumes:** census `targets`, `engine_source_files`.
**Produces:** `audit(root: Path, surface_targets: set[str], allowed_imports: set[str], identity_allowlist: list[dict], character_names: set[str]) -> list[str]` (empty = clean; each finding starts with `R<n> <file>:<line>`). Rules (spec §6 N3):
- **R1** a part imports only stdlib (`sys.stdlib_module_names`), `game`, and modules in `allowed_imports` (every module `game.py` imports today, top level and in-function, frozen in the lock at this task).
- **R2** no `game_parts.*` or relative import inside a part; no `from game import`. Outside `game.py` and `game_parts/`, no file under `ai-dnd` imports `game_parts` (tests included). In `game.py`, every `game_parts` import is `from game_parts.<x> import <names>`; no star.
- **R3** a name in `surface_targets` (plus `open`) is never bound at part module level and never read as a bare global in a part.
- **R4** `game.<x>` appears only inside function bodies: not at module level, not in a default argument, not in a decorator.
- **R5** a part's module-level assignment reads only names bound in the same part, its imports and builtins.
- **R6** `__file__`, `__name__`, `globals`, `locals`, `vars`, `sys.modules` are forbidden in a part unless a row `{"file", "function", "name", "reason"}` in `identity_allowlist.json` matches; every row is on the approval list.
- **R7** no undefined global name in a part; no `game.<character attribute>` (`character_names` = the keys of `_CHARACTER_GLOBALS`, read from `game.py` by `ast`).

- [ ] **Step 1: Write the failing tests** — one fixture part per rule, each asserting its rule id is in the findings, plus the clean cases:

```python
BAD = {
 "R1": "import game\nimport requests\n",
 "R2": "import game\nfrom game_parts import dice\n",
 "R2b": "from game import roll_d20\n",
 "R3": "import game\nfrom uuid import uuid4\ndef f():\n    return uuid4()\n",
 "R3b": "import game\ndef f():\n    return roll_d20()\n",          # roll_d20 is a surface target
 "R3c": "import game\ndef f(p):\n    return open(p)\n",
 "R4": "import game\nCAP = game.K\n",
 "R4b": "import game\ndef f(x=game.K):\n    return x\n",
 "R5": "import game\nB = OTHER_PART_CONSTANT + 1\n",
 "R6": "import game\ndef f():\n    return __file__\n",
 "R7": "import game\ndef f():\n    return helper()\n",
 "R7b": "import game\ndef f():\n    return game.current_hp\n",
}
def test_each_rule_fires_on_its_fixture(self): ...
def test_a_clean_part_passes(self):
    # "import game\nimport re\nRX = re.compile('a')\ndef f(s):\n    random = game._session().rng\n    return RX.match(s), game.roll_d20(), random\n" -> []
def test_an_allowlisted_identity_name_passes_and_only_that_one(self): ...
def test_a_test_file_importing_game_parts_is_reported(self): ...
def test_a_star_reexport_in_game_py_is_reported(self): ...
def test_the_real_tree_is_clean(self):
    self.assertEqual(audit(ROOT, TARGETS, ALLOWED, ALLOWLIST, CHARACTER_NAMES), [])
```

- [ ] **Step 2:** Run. Expected: FAIL (`routing_audit` missing).
- [ ] **Step 3:** Implement with `ast` + `symtable`; generate `allowed_imports.json` from `game.py`.
- [ ] **Step 4:** Run `api.tests.test_engine_routing` + `NEIGHBOURS`. Expected: `RESULT exit=0` (the real tree holds `terminal.py` only). If `terminal.py` trips a rule, that is a Task 11 defect: fix it red-first here and say so in the ledger.
- [ ] **Step 5:** Install the pinned `ruff` (approved in Task 0) and run `ruff check --select F821,F401,F811 game.py game_parts` through `SLOTPY`-style invocation, no `--fix`. Record the output in the ledger as a second opinion; it gates nothing.
- [ ] **Step 6: Commit** `game.py split T2.4: N3 routing audit (seven rules) on game_parts`.

### Task 18: Pilot (a) — `roll_d20` moves to `game_parts/character_rules.py`

**Review tier:** strong. Money/save/Undo: no (stop if Step 1 says otherwise).

**Files:**
- Create: `ai-dnd/game_parts/character_rules.py`
- Modify: `ai-dnd/game.py` (the `roll_d20` block becomes `from game_parts.character_rules import roll_d20`; `_PART_MODULES = ("game_parts.character_rules",)`), `surface.json`, `size_budget.json` (lower if the latch asks)
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

- [ ] **Step 1: Measure [Y].** `is_sensitive("roll_d20", lock)` must be `False`. If `True`, stop: the pilot needs another name and Kadir is told. Make the base folder for `move_check` from `origin/main` (Task 5's `git archive` line) under `AI-DND-TOOLS/measure/engine-split/base-t2/`.
- [ ] **Step 2: Write the failing tests:**

```python
def test_a_moved_function_still_binds_the_session_it_is_given(self):
    with fixed_town(self, 20261120):
        s = game.create_session(seed=5)
        default_state = game._session().rng.getstate()
        before = s.rng.getstate()
        value = game.roll_d20(session=s)
        self.assertIn(value, range(1, 21))
        self.assertNotEqual(s.rng.getstate(), before)
        self.assertEqual(game._session().rng.getstate(), default_state)
    self.assertTrue(game.roll_d20._session_bound)
    self.assertEqual(game.roll_d20.__module__, "game_parts.character_rules")   # red before the move

def test_a_part_reads_engine_names_through_game(self):
    fake = MagicMock(); fake.rng.randint.return_value = 7
    with patch.object(game, "_session", return_value=fake):
        self.assertEqual(game.roll_d20.__wrapped__(), 7)   # the part's own function, without the session wrapper
    fake.rng.randint.assert_called_once_with(1, 20)

def test_a_patch_on_game_roll_d20_reaches_engine_callers(self):
    # inside fixed_town; patch.object(game, "roll_d20", return_value=20) and run one engine call that rolls a d20
    # (perform_skill_check with the default session's character); assert the mock was called and the result's dice == 20

def test_both_import_orders_work_in_a_fresh_interpreter(self):
    for code in ("import game, game_parts; print(game.roll_d20.__module__)",
                 "import game_parts, game; print(game.roll_d20.__module__)"):
        done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "game_parts.character_rules"), done.stderr)
```

Update Task 14's test to expect `("game_parts.character_rules",)`.

- [ ] **Step 3:** Run. Expected: FAIL on the `__module__` lines and on the import-order test.
- [ ] **Step 4:** Move with the tool: `SLOTPY`-run `move_block.py` against the worktree path (`--game /mnt/c/.../ai-dnd/game.py --part /mnt/c/.../ai-dnd/game_parts/character_rules.py --names roll_d20`). Write the part header by hand (`import game`). Set `_PART_MODULES`. Nothing else changes.
- [ ] **Step 5: N5.** `move_check.py --base-root <base-t2> --root . --moved roll_d20=character_rules.py --tier strong --manual "game_parts/character_rules.py:1:part header" --manual "game.py:<line>:_PART_MODULES value"`. Expected: `CHANGED 0`. Paste the output in the ledger. The reviewer runs it again separately. `CHANGED` above zero: redo the move from scratch.
- [ ] **Step 6: N1.** Regenerate the golden; `surface.py --diff --moved roll_d20`. Expected: no violation.
- [ ] **Step 7: Seeded proof for the wrapper.** In the working tree only, set `_PART_MODULES = ()`; run the first test; expected FAIL (`session=` is rejected); restore. Record.
- [ ] **Step 8:** Regenerate `patch_census.json` if the new tests added a target (for example `_session`) and explain it in the ledger. Targeted run: `api.tests.test_engine_parts_pilot api.tests.test_engine_routing api.tests.test_engine_surface api.tests.test_engine_patch_census api.tests.test_engine_size_budget api.tests.test_engine_hash_parts` + the ten test modules with the most `roll_d20` sites in `docs/engine-split/patch-census.md` + `NEIGHBOURS`. Expected: `RESULT exit=0`.
- [ ] **Step 9: Commit** `game.py split T2.4: pilot (a) roll_d20 lives in game_parts/character_rules.py`.

### Task 19: Pilot (b) — one regex constant and the pure helper that reads it move to `game_parts/text_rules_a.py`

**Review tier:** strong. Money/save/Undo: no.

**Files:**
- Create: `ai-dnd/game_parts/text_rules_a.py`
- Modify: `ai-dnd/game.py`, `surface.json`, `size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

- [ ] **Step 1: Measure and choose [Y].** From `docs/engine-split/inventory.json` pick the pair `(CONST, helper)` where: `CONST = re.compile(...)` is a module-level assignment alone in its constant cluster; `helper` is in `closed_helpers`, reads `CONST`, is not sensitive, and neither name is a census target; at least one other reader of `CONST` stays in `game.py`. Among candidates take the helper with the fewest lines, ties by name. Write `Ruling: pilot (b) = <CONST>, <helper> — <the measured facts> — <cost if wrong: redo one small move>`.
- [ ] **Step 2: Write the failing tests** (names filled from Step 1):

```python
def test_the_constant_is_one_object_under_both_names(self):
    # no test imports game_parts (N3 R2): reach the part's namespace through the unwrapped helper
    self.assertIs(game.<CONST>, game.<helper>.__wrapped__.__globals__["<CONST>"])
def test_the_helper_gives_the_same_answers_as_before(self):
    # three inputs chosen from the helper's existing tests; expected values captured on origin/main before the move
def test_the_helper_is_session_bound_and_lives_in_the_part(self):
    self.assertTrue(game.<helper>._session_bound)
    self.assertEqual(game.<helper>.__module__, "game_parts.text_rules_a")
def test_the_reader_left_in_game_py_still_works(self):
    # call the staying reader named in Step 1 with an input that exercises CONST; same result as on origin/main
```

- [ ] **Step 3:** Run (FAIL on the `__module__` line), move both names with `move_block.py` (the constant stays bare inside the part: N3 rule 5), add `"game_parts.text_rules_a"` to `_PART_MODULES`, write the part header by hand (`import game`, `import re`).
- [ ] **Step 4:** `move_check.py --base-root <base-t2> --root . --moved roll_d20=character_rules.py,<CONST>=text_rules_a.py,<helper>=text_rules_a.py --tier strong` (plus the `--manual` lines for both part headers and `_PART_MODULES`) → `CHANGED 0`; `surface.py --diff --moved <helper>` → no violation (the constant is data and has no `module` line). Both outputs in the ledger.
- [ ] **Step 5:** Targeted run: `api.tests.test_engine_parts_pilot api.tests.test_engine_routing api.tests.test_engine_surface api.tests.test_engine_size_budget` + the test modules that call the helper or the staying reader + `NEIGHBOURS`. Expected: `RESULT exit=0`.
- [ ] **Step 6: Commit** `game.py split T2.4: pilot (b) regex constant and its pure helper live in game_parts/text_rules_a.py`.

### Task 20: The net's own exam (spec §6, mandatory before any bulk move)

**Review tier:** strong. Money/save/Undo: no.

**Files:** none committed. Work on a throwaway local branch `tmp/game-py-bolme-ag-sinavi` cut from the T2 branch; it is never pushed and, by the owner's rule, not deleted (note it in the ledger).

For each fault: apply it alone, run the named module through `slot.sh` (or the named script), see the stated red, `git checkout -- .`, next fault. Record the failing line of each in the ledger.

- [ ] **Fault 1 — bare call to a patched name.** In `game_parts/text_rules_a.py`, change the helper to call bare `roll_d20()`. Expected red: `api.tests.test_engine_routing` (R3).
- [ ] **Fault 2 — missing re-export.** Delete `from game_parts.character_rules import roll_d20` from `game.py`. Expected red: `api.tests.test_engine_surface` (missing name).
- [ ] **Fault 3 — forbidden text in a part.** Put, into `game_parts/character_rules.py`, the text that one Task 7 class-A test forbids (take the first row of `docs/engine-split/source-readers.md`). Expected red: that test.
- [ ] **Fault 4 — deleted comment.** Remove one comment line from the moved helper block. Expected red: `move_check` prints `CHANGED` above zero.
- [ ] **Fault 5 — `__file__` in a part.** Add `_HERE = __file__` to `game_parts/character_rules.py`. Expected red: `api.tests.test_engine_routing` (R6).
- [ ] **Final step:** switch back to the T2 branch, confirm `git status` is clean, rerun `api.tests.test_engine_routing api.tests.test_engine_surface` + `NEIGHBOURS` green. A fault that stayed green stops the plan: the net has a hole; fix the check red-first in its owning task's files, then repeat the whole exam.

### Task 21: Go/no-go gate (spec "TM1") and PR 3

**Review tier:** whole-branch review on the strongest model.

- [ ] **Step 1:** `git fetch origin`; merge `origin/main` if it moved; if `game.py` changed underneath, rerun both `move_check` commands against the fresh base and regenerate the locks.
- [ ] **Step 2:** Full suite flag off, then flag on, ledger on, coverage off. Both `PAR_EXIT=0`.
- [ ] **Step 3: N4.** `drops(base, new, noise)` per flag must be **empty** (the Task 12 keys excepted, by name). Any other drop: the plan stops here and Kadir is told (spec: devam/dur kapısı). Pay separate attention to the `not_called_tests` list from Task 3: N4 cannot see them, N3 is their only guard; say so in the PR text.
- [ ] **Step 4: Speed.** Suite seconds (run A base) and the turn benchmark (median of 5) against TM0. Ruling: the spec starts the 10 % rule at its TM2, but the pilot already routes the most-called name through `game.` — apply it now: more than 10 % slower on either measure = stop and report — if wrong: one early conversation with Kadir.
- [ ] **Step 5:** Debt rows: `game.` prefix style and its optional removal; `_speech_debug_trail` stays in `game.py` because of the `open` patch; root tests outside CI (already D-329: reference it, do not duplicate); the 2 743-line turn function and its `locals()` lookup (next slice).
- [ ] **Step 6:** Whole-branch review; fix red-first. Ask Kadir: push + PR, then merge. CI green after each (`gh run list --repo kadirkayarr-beep/AI-DND --limit 5`).
- [ ] **Step 7:** Check for open `bash`/`sleep` processes; five-line morning summary; ledger line "Plan 1 bitti; T3 planı yazılabilir". No play gate inside Plan 1 (spec decision 7: play at spec TM3 and at closure); the web game's behaviour is unchanged and the ledger says "oynayış: Plan 1'de gerekmez (karar 7)".

---

## Sonraki planlar

Each is written after Task 21 passes, as its own plan, own worktree and own PR. No tasks here; only the measured inputs each needs from Plan 1.

- **Plan 2 — T3 leaves (`tables.py`, `schemas.py`, `text_rules_a/b.py`) to spec TM2.** Needs: `inventory.json` constant clusters and `closed_helpers` (real count vs the spec's 151), `sensitive.json` (helpers to hold back), census targets for data names (`CLASSES`, `RACES`, `system_prompt`), TM0 suite-time and turn-benchmark bases.
- **Plan 3 — T4 low-impact areas (`character_rules`, `places`, `intent`, `dialogue`, `lore`, `narration`, `narration_safety`, `living_world_turn`, `new_game`) to spec TM3 + Kadir's 10-minute play.** Needs: call graph (final module boundaries), in-function import list per function, production rebinders from the census (`narrative_director`, `trace_ai_pipeline`, `ollama_adapter`), the non-constant-default list, speed numbers from Plan 2's gate.
- **Plan 4 — T5 money, save, combat and sensitive leftovers to spec TM4.** Needs: `sensitive.json` grouped by target module (decides how T5.4-5 splits), the `uuid4` caller set, the logger-name facts for `_repair_dilim1/2_fields`, `coverage-base.json` and its noise set (N7 equality is due at TM4).
- **Plan 5 — T6 turn core (`turn.py`) to spec TM5.** Needs: the two `sys.modules[__name__]` sites and the `locals()` site as measured, the identity allow-list state, N4 noise set, the zero-tolerance journey list.
- **Plan 6 — T7 closure.** Needs: final sizes for the budget file, the dead-code candidates with both-flag coverage (four-condition evidence, spec §10), pinned `vulture`, the list of dev-only installs to remove (slot `.pth`, `coverage`, `ruff`), CLAUDE.md / preamble / GLOSSARY / ADR / INDEX lines (decision 8).
