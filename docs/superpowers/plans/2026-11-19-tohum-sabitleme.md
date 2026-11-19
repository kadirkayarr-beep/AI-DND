# Fixed-town job (D-373, D-374, D-375, D-377) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Every test named below starts its campaign in a fixed town, and the town-dependent failures they hid are understood. Each real game gap is fixed with a red test first.

**Architecture:** Two lanes run in parallel in two worktrees, one writer each. Lane A is money and naming (D-374, D-375). Lane B is the front fallback and the journeys (D-377, D-373, then a scan). Lane B is merged into lane A locally. Debt and approval rows are written once, then both full suites run, then the whole branch is reviewed. The result is one PR.

**Spec:** the debt rows D-373, D-374, D-375 and D-377 in `docs/agents/debt-register.md`, plus CLAUDE.md "[Kalite] Sabit kasaba". Owner decision 2026-11-19: "önerdiğin sırayla devam et … workflow kullan … dikkatli ol hata yapma".

## Global Constraints

- **Base:** `dfa28754` (the PR 5 tip, #132). Lane A works in `C:\Users\Kadir\Desktop\AI-DND-k2-tohum-a` on branch `task/tohum-a`, slot 2. Lane B works in `C:\Users\Kadir\Desktop\AI-DND-k2-tohum-b` on branch `task/tohum-b`, slot 4.
- **Seeding** uses only the existing helpers: `api.tests.town_seed.fixed_town(test, first_seed)` for unittest tests, and `campaign_seed` for journey scenarios. No new seeding mechanism.
- **No seed shopping.** A seed is never picked just because it passes. Every town where a test fails is either:
  - (a) a game gap, fixed with a red test that uses that town; or
  - (b) a test assumption the town breaks, shown in the report with the evidence (what the town has, what the test assumed).

  For (b), the seed choice gets a `Ruling` line, and one extra test pins the failing town's correct behaviour where that is possible.
- **Money code** (wage, coin, payment): an independent review on the strongest allowed model (Opus), red test first. Never fable (owner rule).
- **Neighbours:** every targeted run includes NEIGHBOURS = `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys`.
- **Lanes never edit** `docs/agents/debt-register.md` or `docs/agents/onay-listesi-20261115.md`. They write the proposed rows into their report. The merge step writes them.
- **Debt ids:** the next free id is D-381. The merge step assigns ids.
- **Approval list:** every changed test gets a row. Seeding a test that ran on random towns is marked "gevşetme olabilir": it now covers one town instead of many, which is why the 40-town probes are kept as evidence.
- **Full suites:** only in the Gate task, one at a time, after the strict pgrep wait. No browser tests. Never read key files. Never push, merge to main/dev, or delete branches.
- **Evidence for a town:** a temporary probe test over seeds 1..40 (pattern used in Plan 2: one test method per seed). It is never committed. After use: delete it and `git restore --staged` it (slot.sh stages untracked files).

## Task A1: D-374, wage not paid in towns 14 and 22 (money)

**Files:** `ai-dnd/api/tests/test_step4_branches.py`, plus whatever money code the root cause names.

- [ ] Reproduce with `fixed_town` seeds 14 and 22: `0 != 12`. Trace why no wage is paid.
- [ ] (a) If it is a game gap: write a red test in towns 14 and 22, fix it, show the test green, and run the other 38 seeds as a probe.
- [ ] (b) If it is a test assumption: give the evidence and the Ruling.
- [ ] Seed `test_the_wage_is_the_only_money_that_moved` and every other campaign-starting test in this module that has no seed. Commit.

## Task A2: D-375, a hidden new name passes in town 30

**Files:** `ai-dnd/api/tests/test_front_carries_more.py` and the code that `_inspection_findings` uses.

- [ ] Same steps as A1 for seed 30: the name "Umerişa" or the town's equivalent is hidden inside a known name.
- [ ] Seed every unseeded campaign-starting test in the module. Commit.

## Task B1: D-377, the fallback walks the player out of town on "walk out and rob X" (towns 12, 27, 32)

**Files:** `ai-dnd/api/tests/test_front_failed_fallback.py` and the D-240 fallback code (`game.py` and/or `world_threads.py`; find it with graphify).

- [ ] Write a red test: towns 12, 27 and 32, the line "Şehrin dışına gidiyorum ve <the town's own NPC>'i soyuyorum." with the front reading failing. Expected: the location does not change.
- [ ] Fix the fallback so a walk-out that also does a second deed is left to the old chain in every town.
- [ ] Seed the module's unseeded tests. Run the 40-seed × 4-line probe green. Commit.

## Task B2: D-373, 64 journey scenarios without `campaign_seed`

**Files:** `ai-dnd/api/tests/journeys/scenarios/*.json` (only the 64 unseeded ones), plus the report table if the schema needs it.

- [ ] List the 64. Give each one a fixed `campaign_seed` by one stated rule.
- [ ] Run the journey modules. A scenario that fails with its seed goes through the (a)/(b) rule. Zero-tolerance journeys stay green.
- [ ] Commit.

## Task B3: scan (read-only, report only)

- [ ] Count the test modules and tests that create a campaign with no `fixed_town` or `campaign_seed`. A campaign is created through `create_campaign`, `/campaigns` POST, or a helper that calls them.
- [ ] Write the list to the report. The merge step turns it into one debt row with an owner. No code change.

## Task M: merge and rows

- [ ] In lane A's worktree: `git merge --no-ff task/tohum-b`. Resolve any conflict by reading both sides. Rerun the targeted modules of all tasks together with NEIGHBOURS.
- [ ] Write the debt rows (D-381 on, exactly 8 `|` each):
  - close D-373, D-374, D-375 and D-377, or update them with their state;
  - add new rows for the parks and the scan.
- [ ] Write the approval list section 19 with every changed test. Commit.

## Task G: gate

- [ ] Two full suites on slot 2, one at a time: `slot_gate.sh 2 AI-DND-k2-tohum-a tohum-off 3 3600 '.'`, then `tohum-fon` (the label token `fon` turns the flag on).
  - Flag off passes with `failing_ids 0` and `PAR_EXIT=0`.
  - Flag on passes when `failing_ids ⊆ F_fon` (`C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p2/F_fon.txt`). F_fon ids that now pass are listed. A red outside F_fon stops the job.
- [ ] `python test_regression.py` as a script: 30/30.

## Task R: whole-branch review

- [ ] One Opus review of `dfa28754..HEAD`, money focus. Then one fix wave (red-first) and one scoped re-review. Remaining Minors go to debt rows.
