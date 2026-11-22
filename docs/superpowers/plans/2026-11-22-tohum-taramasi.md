# Flaky-Town Sweep (roadmap row 2b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every test that creates a new campaign runs on a fixed town (fixed campaign id), and a guard test keeps it that way.

**Architecture:** A new campaign's town comes from its id (`SessionManager.create_campaign` → `uuid.uuid4()` → `living_world` `campaign_seed`). Pinning patches `api.session_manager.uuid` for the next id (`town_seed.fixed_town` → `journeys.runner._campaign_seeded`). We add `default_town` (pins unless an outer pin is already active), wrap every unpinned creation site with it, one `TOWN_SEED` per file, and add an AST guard over `api/tests`.

**Tech Stack:** Python stdlib (`ast`, `unittest`, `unittest.mock`); guarded runners `AI-DND-TOOLS/slot.sh` and `ai-dnd/scripts/engine_split/slot_gate.sh`.

**Spec:** `docs/superpowers/specs/2026-11-22-yol-haritasi-design.md` §5 row 2b, §6.4, §8 S9; `CLAUDE.md` "Sabit kasaba"; debt rows D-483, D-074.

## Global Constraints

- Test-only (S9): touch only `ai-dnd/api/tests/**`, `docs/agents/debt-register.md`, the ledger. Never `game.py`, `game_parts/`, engine or API code. Merges after green CI, no play gate, not counted in the S5 limit.
- Timing: after the docs PR (row 2), before the turn split (row 4): no second writer in test files while the split runs.
- Pin the seed only. Never change, weaken or delete an assertion. Never pick a seed to hide a defect: seeds come from the Task 0 rule, fixed before any run. A test red on its pinned seed = stop, debt row, report; no re-seed.
- Worktree `C:/Users/Kadir/Desktop/AI-DND-k2-tohum-tarama`, branch `task/tohum-taramasi-20261122`, one writer. Ledger `.superpowers/sdd/tohum-taramasi/progress.md`; every `Ruling:` goes there.
- Targeted runs only `bash C:/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh 9 AI-DND-k2-tohum-tarama test <label> 1800 <modules>`; pass = `RESULT exit=0`. Both flags every time: flag-on label `tt<task>-<batch>-fon`, list starts `api.tests.gate_boot` and contains `api.tests.test_engine_gate_boot`; flag-off label `tt<task>-<batch>-off` (no letters `fon` anywhere else in the label).
- Fixed neighbour set `NEIGHBOURS` in every targeted run: `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys`.
- Full suite only via `bash C:/Users/Kadir/Desktop/AI-DND-k2-tohum-tarama/ai-dnd/scripts/engine_split/slot_gate.sh 4 AI-DND-k2-tohum-tarama <label> 3 4500 '.'` (FSLOT 4), and only after `wsl -e pgrep -af slot_gate` prints nothing (else wait, poll every 5 min, at most 35 min, then ask). Pass = `PAR_EXIT=0` and `failing_ids 0`.
- Every implementer prompt carries `docs/agents/implementer-preamble.md`; graphify rule: `graphify query` before the first code read (from `C:/Users/Kadir/Desktop/AI - DND`).
- Briefs name functions and files, never line numbers. No browser tests. Models: Sonnet implementer and reviewer; never Fable.

## Inventory (scanned 2026-11-22 on origin/main 1c78add2, AST over `ai-dnd/api/tests/**/*.py`)

Entry points: HTTP `post("/api/game/campaigns", …)` (also via a parameter defaulting to that literal, `test_roadmap_c06_creation_http.post_character`) and `<manager>.create_campaign(…)`; `store.create_campaign` is a DB row, not a town. Engine-only `GameSession`/`create_session` paths have `campaign_seed ""` (same town every time): excluded.

| Measure | Count |
|---|---|
| Creation call sites | 191; already pinned at the site 34 |
| Sites not pinned at the site | **157 in 68 files** (138 reached by unpinned tests; 19 pinned only by their callers) |
| Suite tests creating a campaign on a random town | **1 243 in 150 modules** (`api/tests/test_*.py`, 639 modules in the suite) |
| Shared sites (reached from >1 module) | **8 sites in 6 files**: `test_campaign_api.create_city_with_locked_tavern` (41 modules), `test_campaign_api.CampaignApiTests.create_campaign` (40), `test_campaign_time` `asyncSetUp` (12), `test_roadmap_c06_level4_http.earned` (5), `test_roadmap_c10_berserker_http.earned` (4), `test_explicit_shop_creation` (2 sites, 3 and 2 modules), `c10_reckless_external_fixture_runtime._seed_reckless_attack` (2) |
| Of the 1 243 tests, through the two `test_campaign_api` helpers | 778 |
| Excluded | `live_lr00_grounded_play`, `live_lr00_probe`, `live_npc_p2_sample` (3 tests): not in `scripts/full_python_suite.py` (needs a live model). `journeys/runner._new_journey_campaign`: every caller wraps it in `_campaign_seeded(setup)` and `test_journeys` already fails on an unseeded scenario (118/118 seeded). |

Borrowing: the import closure of `test_campaign_api` reaches 374 test modules, `test_campaign_time` 399, `town_seed` 385 — for those, "run the borrowers" is the full suite.

## Review Focus

1. Nested pins: a borrower pins outside a helper (`test_experimental_npc_dialogue` wraps `campaign_with_npc` in `fixed_town(self, 4101)`); a helper pin must not override it → `default_town` defers (Task 1 `test_an_outer_pin_wins`); Task 3 Step 6 runs every borrower.
2. One pin covers one id: `_campaign_seeded` yields one id, then random. An outer pin around two creations leaves the second random and `default_town` would skip it → Task 0 lists such blocks; each gets one pin per creation.
3. Two campaigns in one test must get different ids (`test_http_two_player_isolation`) → the per-test counter (Task 1 `test_each_creation_takes_the_next_seed`).
4. A store shared across tests (`setUpClass`) would see the same id twice → Task 0 lists shared-store classes; such a class takes `seed + 100 * <test index>` (Ruling) — none expected (stores are per-test `TemporaryDirectory`).
5. Hidden creation forms the guard misses (a URL in a variable) → guard self-test `test_the_scan_knows_each_form` plants each form.

---

### Task 0: Lock the scope

**Files:** ledger only.

- [ ] **Step 1:** `git fetch`; base = `origin/main`, rebased after the docs PR merged. Record sha.
- [ ] **Step 2:** Run an ad hoc scratch scan with Task 1's scan rules, plus the transitive test-to-site inventory; record the site list, the counts (expect ±5 of the table above; a bigger gap = trace and Ruling), outer pins wrapping >1 creation, `setUpClass` stores.
- [ ] **Step 3: Seed rule (pre-registered):** a file that already has a module-level `TOWN_SEED` uses it; any other file `i` (1-based, sorted list of the 68 site files) gets `TOWN_SEED = 8000 + 10 * i`. Write the table to the ledger before any run.
- [ ] **Step 4: Batches:** a site file whose `test_` import closure has >40 modules goes to Task 3 (expected: the 6 shared-site files plus `test_experimental_npc_dialogue`); the rest in alphabetical batches of ≤15 files for Task 2, each with its run list = changed modules + their `test_` import closure + `NEIGHBOURS`.

### Task 1: `default_town` and the guard

**Files:** Modify `ai-dnd/api/tests/town_seed.py`; Create `ai-dnd/api/tests/test_town_seed.py`.

**Interfaces — Produces:** `default_town(test: Any, first_seed: int) -> AbstractContextManager[Any]`: `nullcontext()` with no counter step when `api.session_manager.uuid is not` the stdlib `uuid` module (an outer pin is active), else `fixed_town(test, first_seed)`. In `test_town_seed.py`: `unpinned_sites(root: Path) -> tuple[list[str], int]` (unpinned sites as `"<posix path>:<function>"`, total sites) and `PINNED_BY_CALLER: dict[tuple[str, str], str]` = `{("api/tests/journeys/runner.py", "_new_journey_campaign"): "<reason from the Inventory table>"}`.

Scan rules: files `api/tests/**/*.py` except `live_*.py`. Site = `X.post(a, …)` with `a` the literal `"/api/game/campaigns"` or a parameter of the enclosing function whose default is that literal; or `X.create_campaign(…)` with `X` not `self`/`cls`, not containing `store`, not a `…Tests` class. Pinned = inside a `with`/`async with` whose item contains a call `fixed_town`, `default_town` or `_campaign_seeded`, or a `patch`/`patch.object` naming `session_manager` and `uuid`; or the enclosing function calls `self.enterContext(<such>)`; or `(file, function)` is in `PINNED_BY_CALLER`.

- [ ] **Step 1: Failing tests** (`class DefaultTown`, `class EveryNewCampaignHasAFixedTown`):
  - `test_alone_it_pins_the_next_campaign_id`: inside `default_town(t, 5)`, `str(session_manager.uuid.uuid4()) == "00000000-0000-4000-8000-000000000005"`.
  - `test_an_outer_pin_wins`: `with fixed_town(t, 7): with default_town(t, 5):` → `…000000000007`.
  - `test_each_creation_takes_the_next_seed`: two `default_town(t, 5)` blocks → `…05`, then `…06`.
  - `test_nothing_stays_patched`: after the block `session_manager.uuid is uuid`.
  - `test_the_scan_knows_each_form`: planted sources; flagged: bare HTTP post, `self.manager.create_campaign(…)`, the path-default post; not flagged: same under `fixed_town`, under `default_town`, after `self.enterContext(fixed_town(…))`, `self.store.create_campaign(…)`, `self.create_campaign()`, `post(f"/api/game/campaigns/{cid}/resume")`.
  - `test_every_caller_pinned_entry_still_creates_a_campaign`: each key's file and function exist, contain ≥1 site, reason non-empty.
  - `test_the_scan_still_sees_every_creation`: total sites `>= 150` (Task 0: 191).
  - `test_no_new_campaign_in_the_tests_runs_on_a_random_town`: `assertEqual(unpinned_sites(ROOT)[0], [])`, message lists them; decorated `@unittest.expectedFailure` until Task 3 Step 4.
- [ ] **Step 2:** Run `api.tests.test_town_seed` + `NEIGHBOURS` (`tt1-red-off`): `DefaultTown` fails (`ImportError: default_town`); record the guard's unpinned count (expect 157 − 1 runner entry = 156).
- [ ] **Step 3:** Implement `default_town`. Run `tt1-off`, `tt1-fon`: `RESULT exit=0`.
- [ ] **Step 4:** Commit `test: default_town and the fixed-town guard (expected failure until the sweep ends)`.

### Task 2: Single-module sites (batches from Task 0 Step 4)

**Files:** the batch's site files only.

- [ ] **Step 1 (per batch):** In each file add `TOWN_SEED` (Task 0 table) and `from api.tests.town_seed import default_town`; wrap each unpinned creation call alone: `with default_town(self, TOWN_SEED):` (`test_case`/the test object in module-level helpers). No other line changes; a creation used as an expression becomes a local assigned inside the `with`.
- [ ] **Step 2:** `python -c` with `unpinned_sites` lists none of the batch's files.
- [ ] **Step 3:** Run the batch list (`tt2-b<k>-off`, `tt2-b<k>-fon`): `RESULT exit=0`. A red test: run it on main once; red there too = trace its commit (CLAUDE.md "Bilinen kırıklar"); green on main = the pinned seed exposes a defect → stop, debt row, report. No re-seed.
- [ ] **Step 4:** Commit `test: fixed towns for <files>`.

### Task 3: Shared helpers, guard live, full gate

**Files:** Task 0 Step 4's Task 3 list; `test_town_seed.py`; `docs/agents/debt-register.md`.

- [ ] **Step 1:** Wrap the sites as Task 2 Step 1.
- [ ] **Step 2: Red evidence (optional where no assertion reads town content; required for `test_campaign_api` both helpers, `test_campaign_time`, `test_experimental_npc_dialogue.campaign_with_npc`):** a scratch module `api/tests/test_zz_seed_loop.py` (never committed) sets `<home module>.TOWN_SEED = s` for s in 1..10 and runs the home module plus its two largest borrowers in-process, printing `SEED <s> FAIL <n> <ids>`; run `tt3-loop-off`. Cap 25 min per run (fewer seeds = Ruling). Delete the file; `git status` must not show it (slot staging adds it to the index: `git rm --cached` if needed). Red non-pinned seeds go into the debt row, not fixed here.
- [ ] **Step 3:** Targeted `tt3-off`/`tt3-fon` with the Task 3 files' own modules + `NEIGHBOURS`: `RESULT exit=0`.
- [ ] **Step 4:** Remove `@unittest.expectedFailure`; `api.tests.test_town_seed` green in `tt3-guard-off`/`-fon`.
- [ ] **Step 5: Debt row** (next free id after main; expected `D-484`, re-check; exactly 8 `|`): `| D-484 | [DÜŞÜK] Tohum taraması (yol haritası 2b): kampanya kuran ve kasabası sabit olmayan testler tek seferde sabitlendi (D-483, D-074 ile aynı kök neden). Envanter: 1 243 test, 150 modül, 157 kurulum yeri; yardımcılar `town_seed.default_town` ile, dosya başına bir `TOWN_SEED`; hiçbir doğrulama değişmedi. Bekçi: `test_town_seed.EveryNewCampaignHasAFixedTown`. Tohum döngüsünde kırmızı çıkan tohumlar: <liste ya da "yok"> | test | yol haritası 2b (2026-11-22) | Kadir | Yok (kapandı); bekçi kırmızıysa yeni kurulumu `default_town` ile sar | düzeldi, task/tohum-taramasi-20261122 dalında |`
- [ ] **Step 6: Full gate** (borrowers of `test_campaign_api`, `test_campaign_time`, `town_seed` = the suite): `pgrep` check, then `slot_gate.sh … tt-full-off …` and `tt-full-fon`: `PAR_EXIT=0`, `failing_ids 0` both. Any failure follows Task 2 Step 3.
- [ ] **Step 7:** `graphify update .`; commit `test: fixed towns for the shared helpers; guard live; D-484`; one Sonnet scoped review of the branch diff (`git diff origin/main -- ai-dnd/api/tests | grep -E '^[-+].*assert'` shows only `test_town_seed.py` and the creation-in-assertion lines Task 2 Step 1 turned into locals, each listed in the ledger and checked for equal strength); push, PR, merge after green CI (S4/S9), then `gh run list --repo kadirkayarr-beep/AI-DND`; five-line Turkish summary for Kadir.

**Estimate:** 6–8 h wall (edits ~2.5 h, 4–5 targeted batches × 2 flags ~2 h, seed loop ~0.5 h, full suite × 2 ~1.2 h, review ~0.5 h); 2 agents (1 Sonnet implementer, 1 Sonnet reviewer).
