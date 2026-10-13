# F03-P01 Evidence Reconciliation — 2026-10-13

**Status: additive evidence index only.** This note does not create evidence, grant acceptance authority, or mark F03/LR-00 PASS.

## Three distinct API field-manifest captures

| Capture time (UTC) | Evidence file | SHA-256 | Result and scope |
|---|---|---|---|
| 2026-10-10 15:54:41Z | `.local/evidence/F03/20261010T155441Z/field-paths.json` | `9e219414c5362c9aa6a373ebebfff5faa9dac5e8859817aad80e0cddf97a5bb4` | **BLOCKED**, manifest v1. One create-response capture in a temporary SQLite store; no turns. Narration history was empty, campaign time and combat ID were null, and location was unresolved. |
| 2026-10-10 19:11:51Z | `.local/evidence/F03/20261010T191151Z/P01/field-paths.json` | `ace449f387204edfb26b74ed4f39910a42af83b68deb73ec570f011c4363473d` | **BLOCKED**, manifest v1. One temporary store and campaign, one accepted turn, no combat fixture. The run did not capture persisted narration history or the required complete field set. |
| 2026-10-10 19:21:42Z | `.local/evidence/F03/20261010T192142Z/P01/field-paths.json` | `093b34837ecb532b06d5601eb0e1efcf552c5a6a3c95797accaea2a39ef45c46` | **PASS for the F03-P01 API field-manifest run only**, manifest v2. One temporary SQLite store and campaign, two accepted turns, zero Qwen chat calls; includes persisted narration/state and a same-campaign combat-fixture snapshot. |

The later v2 capture supersedes the earlier BLOCKED captures **only for the F03-P01 API-field-manifest run**. It does not establish browser-visible parity, server-process restart persistence, full combat replay, campaign isolation, or F03 phase acceptance.

## Existing records and acceptance boundary

- `ai-dnd/docs/F03_P01_FIELD_PATH_MANIFEST_2026-10-10.md` remains unchanged. It links to the 15:54:41Z artifact and accurately records that specific run as BLOCKED; it is not a status update for the later captures.
- A historical reconciliation document was found in commit `9a3a5608310cc6915585bd4fc25dbaa26b505e99` (document SHA-256 `584935bfe2d6b5ee67d0ede3bf8455545e2c50490df9a1cdc3d25972ca4f637c`). It is absent from the current checkout and is not an owner-approval record. It is historical context only.
- The governing frozen roadmap is `ai-dnd/docs/AI-DND_Future_Project_Bible_v2_3_2_PROPOSED.md`, SHA-256 `7685bc4318bea56a5b23713af712d22b3a4749d2e5c2d97b551b1e545ef3fcb3`, bound by its separate owner-approval record. That approval freezes roadmap/governance; it is not release or test-result approval.
- The three JSON artifacts are under ignored `.local/evidence/`; this Markdown file is a secondary index to those existing artifacts, not a copy or replacement for them.

**F03 remains OPEN/BLOCKED; LR-00 remains BLOCKED. F10 full is not authorized by this note.** The F03-P03 report at `.local/evidence/F03/20261010T205453Z/P03/REPORT.md` records browser/process-restart/campaign-isolation acceptance as BLOCKED / NOT EXECUTED. No P01 result here closes that work or the remaining F03 acceptance criteria.
