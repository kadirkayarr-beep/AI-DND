# Design fix plan (desloppify stage 2) — 2026-11-25

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Each task has its own worktree, branch, test slot and ledger. Steps use checkbox syntax.

## Kadir için kısa özet (Türkçe)

Puanı en çok düşüren gerçek tasarım borçlarını, oyunu bozmadan ve her adımı testle kanıtlayarak düzeltiyoruz.

- **Dalga 1 (paralel):** T1 ve T2.
  - T1: Dev tur fonksiyonu `play_turn` bölünecek. Bu iş para, kayıt ve Geri Al yolunda; Opus yazar, Opus inceler.
  - T2: Saf kural dosyaları (`core_resolution`, `model_phase`) api katmanından motor katmanına inecek. Sonnet yazar, Sonnet inceler. `dnd_2024_rules` plan incelemesinden sonra çıkarıldı (içerik manifestleri ona bağlı ve kendisi de api'yi çağırıyor).
- **Dalga 2 (paralel, dalga 1 birleştikten sonra):** T3 ve T4.
  - T3: Hatayı sessizce yutan geniş `except Exception` blokları daraltılacak ya da kayda bağlanacak. Kayıt koduna dokunduğu için Opus yazar, Opus inceler.
  - T4: En çok kullanılan üç dosyadaki sözlüklere açık tip (TypedDict) verilecek. Sonnet yazar, Sonnet inceler.
- **Dalga 3:** 20 parçalı yeni değerlendirme ve puan raporu.
- **Yapılmayacak (Ruling):** `game.py` özel isim dışa aktarımı. Oyuna faydası yok, kırılma riski var.

Her görevde önce testler yazılır, testin hatayı gerçekten yakaladığı bozma denemesiyle kanıtlanır, sonra kod değişir. Davranış, para, kayıt, Geri Al, hata mesajları ve oyuncu metni aynen kalır.

## Goal

Lift the desloppify subjective score by fixing the real design debt the 2026-11-25 audit found (AI-DND-desloppify/.superpowers/sdd/desloppify/audit/RAPOR.md), only where the fix is healthy for the game: no behaviour change, no weaker tests.

## Global Constraints (bind every task)

- Behaviour stays identical. This covers HTTP status codes, error bodies, player text, the order of save/commit/rollback, receipts, Undo points and locks. A real bug found on the way is not fixed silently. It goes in the debt register with a red test, as its own commit and Ruling.
- Red first. A new characterization test must be shown red by mutation (remove or alter the pinned line, run it, see it fail, restore with `git restore`). The ledger records the mutation run label.
- Size locks only shrink: `ai-dnd/scripts/quality_gate/size_lock.json` and `api/tests/engine_split_locks/size_budget.json`. `size_lock_shrink` must exit 0. A boundary change goes in docs/agents/onay-listesi.md marked "gevşetme olabilir".
- Quality gate exit 0 before each commit: ruff ratchet, ruff check-shrink, vulture names-shrink, size_lock_shrink, vulture.
- Tests run only through `bash /c/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh <SLOT> <WORKTREE> test <label> 540 <modules>` from /c/Users/Kadir/Desktop. Each task uses only its own slot. Never slots 3, 4 or 5. Never a full suite. No browser tests.
- Foreground waits are at most 9 minutes. No Monitor.
- Every test that creates a campaign uses a fixed town seed (`api/tests/town_seed.py` fixed_town or TOWN_SEED).
- Every targeted run includes these modules:
  - the neighbour set: api.tests.test_journey_runner, test_journey_report, test_journey_schema, test_journeys;
  - api.tests.test_town_seed;
  - the engine locks: test_engine_surface, test_engine_patch_census, test_engine_routing, test_engine_sources, test_engine_size_budget, test_engine_layout, test_quality_size_budget, test_main_route_table;
  - api.tests.test_refusal_census.
- Run in both flags: AI_DND_FRONT_PROPOSAL unset, and =1 with api.tests.gate_boot listed first. Expect failing_ids 0.
- test_contract_parity gets a shard of its own, because it runs about 500 s.
- Money tests list: docs/superpowers/plans/2026-11-23-tur-bolme-measure/money_tests.txt.
- A local gate pass is not a CI pass. CI also runs knip, the gitleaks fingerprint check, project_health_check/final_gate and the full sharded suite (.github/workflows/ai-dnd-ci.yml, ai-dnd-quality.yml). Before choosing test modules, grep the whole repo (tools/, content/, docs/acceptance/, api/tests) for the file paths and module names you change. Tests that read a file's text or path do not show up as importers.
- Process rules:
  - One commit per group, English messages, no attribution.
  - No push. No subagents.
  - Never run rm -r, Remove-Item, git clean, git reset --hard or git worktree remove.
  - No key files.
  - Run graphify query before grepping when graphify-out exists.
- Ledger: `.superpowers/sdd/<task>/progress.md` in the task's worktree. It holds the Rulings, RESULT lines, mutation proofs, parks and the docs/agents/implementer-preamble.md checklist. It is the report.

## Review Focus (inputs no existing test is sure to cover)

1. A turn that fails after a partial write: autosave failure, or a commit that cannot be confirmed. Every restored field must come back, and the error body must match. Covered by T1 steps 2 and 3.
2. A turn that ends in death or combat interrupt while a front proposal is pending, with the flag on. Covered by T1 step 2 and the both-flags runs.
3. A test that patches `api.core_resolution.X` or `api.model_phase.X` after the move. The patch must still reach the code. Covered by T2 step 2, the module-identity test.
4. An unexpected exception type on the money/save path. It must still roll back and fail closed. T3 class A therefore keeps broad catches and only adds logging; one test per site pins this (T3 step 2).
5. A TypedDict that marks a key required when some code path omits it. There is no runtime effect, but the type would lie. Covered by T4 step 2, the producer census.

---

## Wave 1 (T1 and T2 in parallel; no shared files)

### T1: Split play_turn out of create_app (money/save/Undo path)

**Setup**

- Worktree C:/Users/Kadir/Desktop/AI-DND-k2-playturn, branch task/play-turn-split-20261125, base baf7febb.
- Slot 9. Ledger .superpowers/sdd/d531/progress-4.md.
- Prior rules: brief-2.md, brief-3.md and progress-3.md in that folder (the register pattern, late lookup of api.main helpers through the passed module, the route_dump.py and main_openapi_golden.json proof).
- Implementer and reviewer: Opus.

**Files**

- Modify: ai-dnd/api/main.py.
- Create: ai-dnd/api/routes_turn.py.
- Create tests: ai-dnd/api/tests/test_play_turn_branches.py and ai-dnd/api/tests/test_turn_autosave_rollback.py.
- Update: size_lock.json, docs/agents/debt-register.md (D-531 row only).

**Interfaces**

- Produces `register_turn_routes(application, *, api_main, <closure deps>)`, called at the old spot.
- Produces one `TurnRun` dataclass holding the shared per-turn locals, and step functions that each take it.
- No caller outside api/ changes.

**Steps**

- [ ] 1. **Branch census.** List every exit of play_turn (api/main.py, `def play_turn`, about 30 exits). Record the line text, the status code and the body shape. Seed list from the plan review (line numbers at baf7febb; re-anchor by text):
  - 404 unknown session inside the lock (~1161);
  - replay of a repeated request (~1177);
  - the proposal refusal (~1193);
  - HTTPExceptions that are built and returned rather than raised (~1218, ~1235);
  - the `except BaseException` handler (~1317) and the `finally` blocks (~1522, ~1555) and handler (~1527);
  - the model-call limit (~1604) and invalid model response (~1610);
  - lore evidence (~1670), `narrative_memory_error` (~1698), the three error codes (~1754-1764);
  - response build (~1794), receipt conflict 409 (~1853), commit decisions (~1866, ~1888);
  - the economic path, combat or death, the two autosave-failure sites, commit-unconfirmed, normal commit, narration fallback.
  - Map each exit to an existing test by grepping api/tests and the root test_*.py.
  - The ledger table has three columns: exit, pinned-by, gap.
- [ ] 2. **Characterization tests for every gap** in test_play_turn_branches.py. Each test asserts:
  - the status code;
  - the exact error body or response keys;
  - the session fields that must or must not change;
  - receipts;
  - the Undo checkpoint presence.

  Mutation-prove each test red, then restore.
  Commit: "Pin play_turn exits that no test covered".
- [ ] 3. **The two autosave-failure sites** (stage 3 park).
  - test_turn_autosave_rollback.py pins every field restored at each site and the error body. Mutation-prove it red.
  - If the steps match `_put_back_turn` exactly, call the helper there.
  - If not, write a Ruling and leave the site.

  Commit.
- [ ] 4. **Split.**
  - Move play_turn into api/routes_turn.py.
  - Shape: one orchestrator function, at most 150 lines, owns `with record.turn_lock:` and every try / except / finally of today's body. The steps run inside it.
  - A raise must keep its handler: never move a raise across a step boundary in a way that changes which handler catches it.
  - Break the rest of the body into named steps, each at most 150 lines (the limit is 151). Steps share state only through `TurnRun` or explicit parameters.
  - The nested helpers `refuse_before_commit` and `refuse_model_failure` become methods on `TurnRun`. Their bodies and messages are unchanged.
  - api.main helpers are looked up late through `api_main`, never bound at import, so test patches on api.main still apply.
  - The cut tools (ai-dnd/scripts/engine_split/cut_block.py, cut_check.py, and the plans' block_io.py) may find clean cut points.

  Commit.
- [ ] 5. **Proof.**
  - route_dump.py before and after: byte-identical. test_main_route_table green.
  - size_lock_shrink exits 0. create_app is expected to fall from 1711 to about 900 lines or fewer.
  - No new long_functions key, with no exception: size_lock_shrink counts any new entry as growth (scripts/quality_gate/size_lock_shrink.py) and CI runs it.
  - If a step truly cannot get to 150 lines or fewer, stop, write a Ruling in the ledger and report. Do not change the gate.
- [ ] 6. **Tests.** Run the stage-3 set (every module hitting /turn, /undo, economic_action; money_tests.txt; test_turn_rollback_sites; test_campaign_api; test_persistence_idempotency; test_narration_receipt_contract), the new tests and the global set, in both flags.
  - RESULT lines go in the ledger.
  - Update the D-531 debt row.

  Commit.

**Accept when**

- failing_ids is 0 in both flags.
- The route dump is identical.
- No function is over 150 lines.
- Every new test has a mutation proof.

### T2: Move pure rule modules below the api layer

**Setup**

- Worktree C:/Users/Kadir/Desktop/AI-DND-k2-rules, branch task/rules-down-20261125, base baf7febb.
- Slot 2. Ledger .superpowers/sdd/rules-down/progress.md.
- Implementer and reviewer: Sonnet.

**Why it is healthy.** The engine (game.py, game_parts/*, root modules) imports api.core_resolution and api.model_phase at about 51 sites in total, most of them inside functions. Both modules import only the standard library (checked by the plan review). They are engine rules that live in the wrong package, which creates part of the engine-api cycle the review names. Moving them makes these edges one-way at no behaviour risk.

**Out of scope (Ruling, from the plan review).** dnd_2024_rules stays in api/, for two reasons:
- Its path is content data: tools/content/check_manifest.py RESOLVER_FILES, content/manifest/phb2024.json (891 references), legacy-compatibility.json and test_roadmap_b04 read the file's text at that path.
- It lazily imports bold_acts, api.character_creation and character_progression, so moving it would not remove the edge.

**Files**

- Move with `git mv`:
  - ai-dnd/api/core_resolution.py -> ai-dnd/core_resolution.py
  - ai-dnd/api/model_phase.py -> ai-dnd/model_phase.py
- Create shims at the old paths (see step 3).
- Modify imports outside T1's files:
  - every engine import site (game.py, game_parts/*, root *.py, incidents/*, adventure/*, class_progression/*), including imports inside functions;
  - api/ modules other than api/main.py and api/routes_*.py;
  - tests.
- Update engine locks:
  - regenerate api/tests/engine_split_locks/surface.json with `python scripts/engine_split/surface.py --write` (each object's `__module__` changes; never edit it by hand);
  - add core_resolution and model_phase to allowed_imports.json;
  - update any other lock the failing lock tests name.
- Do NOT touch:
  - size_lock.json (it has no keys for these files);
  - docs/agents/debt-register.md (the controller adds the row after both wave-1 PRs merge, to avoid a shared file);
  - api/main.py, api/routes_*.py, or T1's new tests.

**Steps**

- [ ] 1. **Pre-check and census.**
  - Confirm both modules import only stdlib: grep every import line, including indented ones.
  - Confirm no root module with the same name exists.
  - List every import of the two modules: `^from`, indented `from`, and `from api import a, b, core_resolution` lists.
  - List every patch target: patch, monkeypatch, setattr, string targets.
  - List every non-import reference to the paths `api/core_resolution.py` and `api/model_phase.py` in tools/, content/, docs/acceptance/, scripts/ and api/tests.
  - Write the census in the ledger.
- [ ] 2. **Red test** api/tests/test_rules_module_identity.py. For each module it asserts:
  - `import api.<m>` and `import <m>` give the same object (`is`);
  - a monkeypatch through `api.<m>.<name>` is seen by code that imported `<m>` directly, and the reverse;
  - for core_resolution, a ContextVar set through one name is read through the other.

  It is red before the move. Commit.
- [ ] 3. **Move and shim.**
  - `git mv` each module.
  - The shim at api/<m>.py is a docstring, `import sys`, `import <m> as _m`, then `sys.modules[__name__] = _m`. This keeps one module object.
  - The shims stay only for the import sites in T1's files. T3 step 0 rewrites those and deletes the shims (`git rm`) once wave 1 is merged.
  - Identity test green. Commit.
- [ ] 4. **Rewrite imports** at every census site outside T1's files.
  - Regenerate and update the locks as listed above.
  - Run the quality gate. Commit.
- [ ] 5. **Tests**, both flags:
  - the global set and the identity test;
  - every module from the step 1 census (importers, patchers, path readers);
  - test_core_resolution* where present;
  - money_tests.txt, because core_resolution resolves checks used in trades;
  - the model-phase tests (grep model_phase in api/tests).

  RESULT lines go in the ledger, with the debt-row text for the controller: "engine->api edges: core_resolution, model_phase moved; dnd_2024_rules (content path), ollama_adapter, serializers, lore_authority, session_manager left".

**Accept when**

- failing_ids is 0 in both flags.
- The identity test is green.
- `grep -rnE "(from|import) api(\.| import .*)(core_resolution|model_phase)"` finds nothing outside api/main.py, api/routes_*.py and the shims themselves.

---

## Wave 2 (after wave 1 is merged; T3 and T4 in parallel; disjoint files)

### T3: Narrow or log broad `except Exception` in production code

**Setup**

- New worktree from the main that contains wave 1. Slot 9.
- Ledger .superpowers/sdd/except/progress.md.
- Implementer and reviewer: Opus, because campaign_store and the save paths are in scope.

**Step 0 (shim removal).** Rewrite the remaining imports of api.core_resolution and api.model_phase in api/main.py, api/routes_*.py and T1's files to the new paths. `git rm` the two shims. Identity test: switch it to assert that the old name is gone. Run T2's test set again. Then add the T2 debt row.

**Scope.** About 128 production `except Exception` sites (step 1's census is the authority; 13 of api/main.py's sites now live in api/routes_turn.py), excluding tests, scripts/ and docs/evidence. The live smoke scripts are excluded too. T4's files are excluded: world_threads.py, bold_acts.py, living_world.py.

**Steps**

- [ ] 1. **Census.** Classify every site in the ledger table (file:function, class, decision):
  - (A) money/save/Undo path;
  - (B) model or network call;
  - (C) best-effort fallback (narration, UI text, optional enrichment);
  - (D) already narrow enough or already logged.
- [ ] 2. **Class A: keep every catch broad.** This includes `except BaseException` in the turn path. Narrowing here would let an unexpected type skip the rollback and `_put_back_turn`, which breaks fail-closed. The only change is to add `_logger.exception` where the site is silent. Each changed site gets a test that raises an unexpected type (for example a custom RuntimeError subclass) and asserts the rollback still happens and the error body is unchanged.

  Mutation-prove each test.
- [ ] 3. **Class B.** Narrow to the adapter's real error types (grep ollama_adapter and model_chain for what they raise), plus TimeoutError and OSError. Keep a final broad fallback only where the caller must never crash the turn, and log it there. One test per changed module that drives a fake adapter raising each type.
- [ ] 4. **Class C.** Keep it broad. Add `logger.exception` or `logger.warning` with context, plus a one-line comment saying why broad is right. No test is needed when only logging is added. Check the existing tests still pass.
- [ ] 5. **Tests**, both flags: the global set, the modules for every touched file, money_tests.txt, test_persistence_idempotency, test_campaign_api, and the log-sensitive modules test_engine_parts_pilot, test_local_gemma_fast, test_model_chain. Those three assert `assertNoLogs("ai_dnd.api.ollama", "WARNING")`, so ollama fallbacks log at DEBUG.

**Accept when**

- failing_ids is 0.
- No site in class A or B is left swallowing silently.
- Every class C site logs and has a reason comment.
- The census table is complete.

### T4: TypedDict for the three hottest dict shapes

**Setup**

- New worktree from the main that contains wave 1. Slot 2.
- Ledger .superpowers/sdd/typeddict/progress.md.
- Implementer and reviewer: Sonnet.

**Scope.** world_threads.py (92 `dict[str, Any]`), bold_acts.py (71) and living_world.py (49): the records these files create and pass around. grounded_action.py is excluded because it overlaps T3's except sites; it goes to a later round. No runtime change: annotations and TypedDict definitions only.

**Steps**

- [ ] 1. **Producer census.** For each record shape, list every place that builds it and every key read. A key is `Required` only when every producer sets it; otherwise it is `NotRequired`. Record the table in the ledger.
- [ ] 2. **Test.** Add api/tests/test_world_record_types.py. It builds each record through the real producers (fixed town) and asserts that:
  - every produced dict's keys are a subset of the TypedDict's declared keys;
  - every Required key is present.

  It uses `__required_keys__` and `__optional_keys__`. Prove it red by declaring one wrong Required key, then fix.
- [ ] 3. **Annotate.**
  - Define the TypedDicts in a new module, world_record_types.py. Import it under `if TYPE_CHECKING:` (the three files already have `from __future__ import annotations`), so there is no runtime import and no allowed_imports.json change. Replace `dict[str, Any]` on the matching signatures. Leave a site alone where the shape is genuinely open.
  - Run `pyright <touched files>` locally (installed globally; no new dependency, not added to CI). Fix the type errors the change itself reveals. Pre-existing ones go in the ledger as parks.
- [ ] 4. **Tests**, both flags: the global set, the new test, and the modules that import the three files.

**Accept when**

- failing_ids is 0.
- The record-types test is green and its mutation proof is recorded.
- No runtime code changed: the diff is annotations and imports only, plus the new module and the test.

---

## Wave 3: measure

- [ ] T6.
  1. After waves 1 and 2 are merged, rescan with `export PYTHONUTF8=1` and the PATH from the desloppify brief: `desloppify --lang python scan --path ./ai-dnd --force-rescan --attest "..."`.
  2. Run a fresh 20-batch subjective review (`review --run-batches --dry-run`, one Sonnet agent per batch, then `--import-run ... --scan-after-import`).
  3. Write a short Turkish score report: before (63.0) and after, and per dimension.

## Not done (Ruling)

- **game.py private re-export facade (983 private_imports):** not healthy now. The engine locks (surface.json, patch_census.json) and many tests patch `game._x` on purpose. Removing the facade changes test reach, not game quality. Cost if wrong: the score stays lower by that detector only.
- **ollama_adapter, serializers, lore_authority and session_manager imported from the engine:** they need a ports layer. That is a later slice, decided after T6 shows where the score stands.

## Merge order and CI

- Each task gets its own PR to main.
- After green CI the PR is merged, then main CI is checked with `gh run list --repo kadirkayarr-beep/AI-DND`.
- The second PR of a wave merges main into its branch: a merge commit, never a rebase or force push. Its targeted set runs again, then it merges.
- A red CI: download the evidence first, then fix.

## Budget estimate

- T1 and T3: Opus, large.
- T2 and T4: Sonnet, medium.
- Four reviews: two Opus, two Sonnet.
- T6: 20 Sonnet batches.
- Weekly use was 58% on 2026-11-25. New stages stop near 90%.
