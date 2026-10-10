# F02 Baseline Inventory — v1

**Captured:** 2026-10-10 14:06:40 UTC  
**Scope:** F02-P01 + F02-P03 inventory/evidence and the requested F02-P04 bug baseline only. This is not F02 completion.

## Authority and checkout

- Binding Bible: `AI-DND_Future_Project_Bible_v2_3_2_PROPOSED.md`, SHA-256 `7685bc4318bea56a5b23713af712d22b3a4749d2e5c2d97b551b1e545ef3fcb3`; separate owner approval names the same digest.
- Initial checkout: `maintenance/pre04-runtime-health`, HEAD `e74515bc3ddf5d71f3e7a6d16437e05c19ba2680`, clean.
- Runtime, workflows, SQLite, Qwen, source code, lore pins and Bible bytes were not changed. No Python tests, browser/API actions, or live model calls were run.

## P01 — environment and locked inputs

- Linux x86_64; Python 3.13.11; uv 0.9.24; Node 24.13.0; pnpm 10.26.1.
- Python inputs: workspace `pyproject.toml` + `uv.lock`; no `requirements*.txt` under `ai-dnd`. Active metadata versions: FastAPI 0.141.1, httpx 0.28.1, ollama 0.6.2, PyYAML 6.0.3, uvicorn 0.54.0, pydantic 2.13.5. `pip` is not installed in the active environment.
- Frontend inputs: root `package.json` + `pnpm-lock.yaml`; artifact scripts/dependencies in `artifacts/ai-dnd-experience/package.json`.
- Configured FastAPI command: `cd ai-dnd && python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}`. Experience scripts: `pnpm --filter @workspace/ai-dnd-experience run typecheck|test|build|dev`. These commands were inventoried, not executed in this slice.
- Secret values were not read or recorded.

## F01 pinned lore source read-only comparison

All five Bible pins match both the working-tree SHA-256 and Git HEAD-blob SHA-256. This confirms only current source bytes; it does not prove clean-checkout portability or package/install preservation. F02-AC-003 remains NOT TESTED for packaging. The historical Castle Ward/`pack_index.json` line-ending mismatch and scoped repair remain recorded separately; no pin was changed.

## P03 — section 2 ownership baseline

All 15 section 2 rows are mapped in `owners.json` and labeled `KORUNUR`. No row is labeled `COMPLETE`; no `YENİ SÖZLEŞME` is introduced. Protected areas include server-owned mechanics, save/replay boundaries, fail-closed lore authority, and the empty production quest catalog. Future F03–F15 work is outside this slice.

## P04 — bug baseline

- `S10B-INV-001`: intermittent HTTP 500 root cause remains UNCONFIRMED.
- Idempotency timeout: historical/flaky report; not reproduced here.
- Castle Ward and pack-index line-ending/digest mismatch: historical evidence and scoped repair are recorded; package preservation was not rerun.
- 8008 stale-worker Adventure render TypeError: prior browser reproduction and post-restart Cedric resume are recorded as resolved only for that observed worker/session; general root cause remains unconfirmed.

## F02 acceptance status

| AC | Status | Boundary |
|---|---|---|
| F02-AC-001 | NOT TESTED | Environment/commands inventoried; no repeat run with exit evidence. |
| F02-AC-002 | NOT TESTED | No tests, full discovery, browser, Qwen, or manual gameplay run. Prior 67/67 frontend result is historical only. |
| F02-AC-003 | NOT TESTED | Five pin inputs match, but packaging was not exercised. |
| F02-AC-004 | BLOCKED | Known bugs are registered; timeout evidence/reproduction and exact runtime cause are not independently established here. |
| F02-AC-005 | PASS | All 15 section 2 owner rows have required labels. |

**F02 phase status: NOT PASSED.** Five ACs must pass before a phase PASS. F01 Windows closure evidence is not inferred to be incorporated into this Replit HEAD.

## Evidence

Detailed inventory and hashes: `.local/evidence/F02/20261010T140640Z/` (`sources-hashes.json`, `dependency-manifest.json`, `owners.json`, `bugs.json`, `run-matrix.yaml`). Evidence files are in the ignored `.local` tree; this report is the only tracked-path addition from this slice.

## Stage 2/3 review update

Stage 1 remains historical: its original `run-matrix.yaml` and AC-004 BLOCKED result are unchanged. The stage-2 isolated archive omitted required assets and generated library declarations; those failures are documented as harness failures, not game regressions. Stage 3 corrected only the disposable copy:

- Source baseline: `e74515bc3ddf5d71f3e7a6d16437e05c19ba2680`; source archive SHA-256 `31d58f449b7516bb870f4237ff49ee730e3a7c6519fbca35db4d6649fae88bbf`.
- Offline frozen pnpm install: exit 0 in 37 seconds. Library typecheck exit 0/26s; Experience typecheck exit 0/10s; frontend tests exit 0/12s (67/67); build exit 0/12s with `PORT=22785 BASE_PATH=/ai-dnd-experience/`.
- The three referenced generated images were restored from the e74515b Git blobs into the disposable copy only. SHA-256 and blob provenance are in `stage3/assets-provenance.txt`.
- All five F01 pin SHA-256 values are identical before install, after install and after build. Exact values are in `stage3/pins-after-build.txt`.
- Current workspace branch at stage 3: `maintenance/pre04-runtime-health`, HEAD `b87ebfd9b523c9c0a97688498b57a25c54ceab82` (documentation-only commit above the tested e74515b base). No branch or history operation was performed.

## Current acceptance assessment

| AC | Current status | Evidence boundary |
|---|---|---|
| F02-AC-001 | PASS | Isolated locked install and bounded library/frontend typecheck, 67 tests and build have command, exit and timing records. |
| F02-AC-002 | PASS | Selected frontend regression PASS; full Python discovery, live Qwen and manual gameplay remain NOT TESTED. Browser is PASS-SCOPED HISTORICAL only, not a new run. |
| F02-AC-003 | PASS-SCOPED | All five F01 pin bytes remained unchanged through offline install and frontend build. |
| F02-AC-004 | PASS WITH UNCONFIRMED HISTORICAL DEFECTS | Required bug-register fields are present; reproducing or fixing historical reports is not required by the Bible criterion. Stage-1 BLOCKED remains historical. |
| F02-AC-005 | PASS | The same 15 owner rows remain labeled KORUNUR. |

F02 is **PASS within this evidence scope**. This does not claim that the untested Python discovery, fresh browser, Qwen, or manual modes passed. The scoped closure is `F02_PHASE_ACCEPTANCE_v1_2026-10-10.md`; stage 2/3 logs, hashes and matrices are under `.local/evidence/F02/20261010T140640Z/`.

## Scope and next step

No game/frontend source, frozen Bible, lore pin, workflow, owner SQLite, API, session, or Qwen state was changed or accessed. The disposable test directory is removed only after the evidence is verified. Next project work can proceed to F03 in sequence; any untested F02 modes remain explicitly untested and must not be described as fresh passes.
