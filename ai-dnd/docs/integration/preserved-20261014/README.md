# Preserved source proposals — NOT active runtime code

These are exact source/text copies retained during the 2026-10-14 integration.
Do not execute or apply them as a migration or authentication workaround.

- `claim_campaign.py.txt` and `test_claim_campaign.py.txt`: original untracked PC source and its unit test. Kept inert pending separate review. The CLI can reassign an already-owned campaign, constructs a syntactically valid Principal rather than verifying identity, and excludes only a hard-coded default live database path. It must not be introduced as an authorized ownership-recovery mechanism during a source synchronization task.
- `_add_openapi_401.py.txt`: original empty untracked helper, retained byte-for-byte.
- `cursor-source-proposal.patch.txt`: source-only diff of Cursor commit 3b7a440a24fff1b23652158d819b8edaea4ab405. Its debug log file is intentionally excluded. The existing remote Cursor branch and local all-refs backup retain the historical work. Do not apply wholesale: validated spell projection is already present; other hunks include obsolete format promotion, XP reset semantics, duplicated methods, and debug-write instrumentation.

No original working files were removed. No SQL or ownership reassignment was executed by preserving these files. Preserving a proposal is not approval of its runtime behavior.

Archive-only `.txt` attributes preserve exact original CRLF bytes and diff-context whitespace. Whitespace checks remain enabled for all active code and tests.
