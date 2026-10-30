# K07 death/stable — cloud takeover checkpoint (2026-10-28)

## Decision
ACCEPTED only for `K07.death_saves_and_stable.core` and `.temp_hp_at_zero`, including Human THP storage compatibility. The corresponding family was removed from `open_leaves` after independent static review and fresh scoped verification. Remaining K07 families and C06 are not complete.

## Provenance
- Upstream source base reported by Replit: `a963f0a3cc01b2ead30697aa79afa9a560db4dc8`.
- Verified full snapshot: `e4dd953b21afbb3815dc05849262d2011c55a6934de0d87404f5fc33f1c97b9c`.
- Verified required runtime-data addendum: `9e6fa22dd32d7c09e607e69549af308d3a96693f302c8448cb1f0b7e35bb79db`.
- Local import checkpoint: `1616c7f9507f0c62ba2a673dbf42f98769bb7023`. This is an imported snapshot, NOT upstream Git history. Feature changes remain uncommitted; do not push this synthetic history or overwrite another checkout.
- Original plan ZIP hash: `6e9e672c1b7f21e50c2cb880f03471e795a5a46f9d35fe0e272a68b72fb0197e`.
- Python 3.13.5; dependencies installed from unchanged uv.lock with locked sync.

## Verified changes
- Completed Long Rest expires Human root THP; short/interrupted rest preserves it.
- Legacy saves without THP keep their representation and clear stale runtime values.
- Explicit positive Human THP survives save/load and public projection.
- Ordinary damage without prior THP does not insert a zero field.
- Massive-damage regression now actually grants and absorbs THP.
- A synthetic SQL receipt failure proves rest removal/recovery happened before rollback; retry/replay/reopen then preserve exactly-once behavior.

## Evidence
Final guarded related regression: 190 unique methods, zero failures/errors/skips, exit0. This is not the full suite. Dice and failure paths use deterministic fixtures/mocks. Independent review is static, not an independent rerun.

Local-only evidence: `docs/acceptance/evidence/k07-death-stable-20261028/`; validated B02 EvidenceRecord binds review ID, exact raw digest and accepted-source manifest. Review summary: `reviews/K07-death-stable-20261028.md`.

Genuine legacy behavioral RED: `regressions-red/child-1.raw.log`; the older `legacy-roundtrip-red` directory is import-blocked, not a behavioral RED. Earlier 185-method runs and Replit's 5/58 runs overlap; never add them to 190.

## Guard and limitations
Pinned guard SHA256: `d0803047bca67beec76a27d7825cef6f655bafee81d290d5c940d530ec0a51c5`. All test children prove it before importing product tests. Fresh synthetic HOME/TMP/DB only. Anonymous Unix stream pairs support internal asyncio; address-bearing socket operations and IPv4/IPv6 remain denied. Readonly SQLite URIs require strict validation and exact per-thread authorization. Personal files, existing services, uncontrolled child processes remain unavailable. This is a trusted-Python audit boundary, not a kernel sandbox.

`test_sessions.CompatibilityTests.test_terminal_initialization_dice_and_exit` remains BLOCKED because it spawns an unguarded nested interpreter. No new subprocess permission was granted. Full release/API discovery, UI/browser, real Clerk, local Ollama and human gameplay acceptance are NOT RUN. THP replacement-choice semantics remain separately OPEN.

## Rollback / continuation
Retain the immutable input ZIPs and manifests. Apply a reviewed file delta only to a matching verified snapshot; do not reset or clean any user's checkout. Replit is stopped. No merge, push, deployment or live data migration was done.

Next: use the original K07 plan and verified source package to choose one remaining dependency-ready leaf. Do not reopen completed death/stable mechanics without a concrete counterexample. Further PHB source sections not contained in the bounded death mini pack must be transferred/verified before implementing those rules.
