# F02 Phase Acceptance — scoped evidence

**Status:** PASS within the evidence scope below.  
**Binding Bible:** `AI-DND_Future_Project_Bible_v2_3_2_PROPOSED.md`, SHA-256 `7685bc4318bea56a5b23713af712d22b3a4749d2e5c2d97b551b1e545ef3fcb3`.  
**Tested source baseline:** `e74515bc3ddf5d71f3e7a6d16437e05c19ba2680`.  
**Workspace HEAD observed:** `b87ebfd9b523c9c0a97688498b57a25c54ceab82` on `maintenance/pre04-runtime-health`; this documentation-only commit is above the tested source baseline. No checkout or history operation was performed.

## Acceptance criteria

| AC | Status | Evidence |
|---|---|---|
| F02-AC-001 | PASS | Disposable locked install and bounded library/frontend typecheck, 67-test run and build completed with exit/timing records on the same machine. |
| F02-AC-002 | PASS | Modes are separately recorded below. Only actually executed modes claim fresh results. |
| F02-AC-003 | PASS-SCOPED | Five F01 pins were identical before/after offline dependency install and after the frontend build. |
| F02-AC-004 | PASS WITH UNCONFIRMED HISTORICAL DEFECTS | Each registry item carries classification, owner, reproduction, risk, gate and source. The criterion does not require historical issues to be reproduced or fixed. Stage-1 BLOCKED is retained in the original evidence. |
| F02-AC-005 | PASS | All 15 owner rows remain unchanged and labeled KORUNUR. |

## Test-mode matrix

| Mode | Result |
|---|---|
| Selected frontend regressions | PASS — 67 tests, 67 passed, 0 failed, exit 0 |
| Full Python discovery | NOT TESTED |
| Browser | PASS-SCOPED HISTORICAL only; no browser run in this stage |
| Real Qwen | NOT TESTED |
| Manual gameplay | NOT TESTED |

## Isolated run evidence

The clean-room source archive was built from e74515b; archive SHA-256: `31d58f449b7516bb870f4237ff49ee730e3a7c6519fbca35db4d6649fae88bbf`. Offline install used `pnpm install --frozen-lockfile --offline --ignore-scripts --reporter=append-only`, exit 0 in 37 seconds.

| Command | Exit | Elapsed |
|---|---:|---:|
| `pnpm run typecheck:libs` | 0 | 26 s |
| `pnpm --filter @workspace/ai-dnd-experience typecheck` | 0 | 10 s |
| `pnpm --filter @workspace/ai-dnd-experience test` | 0 | 12 s |
| `PORT=22785 BASE_PATH=/ai-dnd-experience/ pnpm --filter @workspace/ai-dnd-experience build` | 0 | 12 s |

Stage 2's failed harness attempts are retained separately. The corrected stage 3 copy restored only the three imported JPEGs from immutable e74515b Git blobs and built library declarations with the repository's `typecheck:libs` script; no source or generated output was fabricated.

## F01 pin preservation

Each hash was unchanged before install, after install and after build:

| Pin | SHA-256 |
|---|---|
| `Owner_Decision_Castle_Ward_1501.md` | `be4b2f8a399103537f93fc33cfebe47524bd811a6fb232b577b480a087895d8a` |
| `pack_index.json` | `3ba99717976aa25f154fdd97cc4ce6e5e7d5bf59bd175bc037cd7c537ebcacd5` |
| `neverwinter_the_north_v1.extraction.json` | `51b1ce206d8be080de855aff79348a05578a99ca5c5b69c7fee912063d5c64c5` |
| `neverwinter_the_north_v1.review.json` | `0438e805ba26c345af6b7b0078770e45a33f71fb0b5e9cab404cfe7571de703e` |
| `installed_region_catalog.json` | `2c20d3841a6fe3eb7566fb97b3cc07cc9aa5e65585e481c531a820c7d94d1936` |

## Boundaries

No production publish, source-code change, Bible or lore-pin edit, workflow restart, owner SQLite access, API/game request, session change, live Qwen call, or Git history/branch operation was performed. This scoped PASS does not convert any NOT TESTED mode into a pass.

Detailed command logs, timings, source/image provenance, failed stage-2 attempts and pin comparisons are in `.local/evidence/F02/20261010T140640Z/`.
