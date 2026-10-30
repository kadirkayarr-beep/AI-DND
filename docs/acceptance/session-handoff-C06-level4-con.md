# C06 selected Sorcerer3→4 CON+2 — scoped ACCEPTED

2026-10-29. **ACCEPTED only for selected existing-character Sorcerer3→4 CON+2 core and persistence.** Independent final reviewer performed read-only inspection, confirmed principal source hashes/raw digest and found no blocking issues; no independent rerun or UI acceptance. Actual bounded transition and repeated v4/v5 save/fresh restore are implemented; this is not full C06 or full Sorcerer support.

Scope: applied3/raw3-or4 → applied4, fifth cantrip, seventh ordinary prepared spell, capacities4/3 preserving spent world resources, existing C03 CON+2 resolution, retained original provenance and strict earned ledger, coherent CON mirrors/saving total, unpaid base HP once, retroactive maximum through canonical no-healing setter. Unaffected saving totals remain verbatim. Exact format presence/value and trusted state roll back on failure. Direct XP900 and real XP-first2700 both roundtrip under existing v5 rules; no award or new XP floor.

Evidence-backed clarification: authoritative world slot counters can differ from the legacy character cache after real cast/rest. Both remain capacity-bounded; no refill from the cache. Exact cantrip/prepared identities remain required. Actual4 Magic Missile slot2 → save/fresh restore proves the spent world counter persists. Present final-score cache is strict; its legitimate absence on restored3 is permitted, and actual4/reload4 reconstruct it without using it as origin authority.

## Execution evidence

Initial genuine RED: `c06-four-con-red-20261029-0853`, 6 methods/5 assertion failures. Final guarded run: **323 PASS**, 17 new methods plus 306 related executions; counts overlap prior work and must not be summed. Explicit synthetic maximum-setter and postcommit-validation faults prove rollback, not naturally occurring production faults. Fixtures, patched rolls and real in-process HTTP tests are not browser/human acceptance. No additional unrelated suite run.

Bound artifacts: `docs/acceptance/evidence/c06-level4-con-20261029/` contains unchanged raw child logs, full runner evidence, schema-shaped guard/target rows, source hashes and scoped review-verdict metadata. SHA-256 of both raw logs was verified on copy; all seven source hashes equal the final-run handoff hashes. Genuine historical HEAD96e0 plus dirty recovered snapshot remains the source identity, not a claimed original clean base.

## Exact command and module scope

```sh
env -i PATH=/usr/bin:/bin HOME=/tmp/ai-dnd-recovery-home TMPDIR=/tmp /workspace/scratch/a1b372df36be/ai-dnd-recovered-work-20261029/.venv/bin/python -I -B /workspace/scratch/a1b372df36be/ai-dnd-recovered-work-20261029/run_guarded.py c06-four-con-final-20261029-0900 api.tests.test_roadmap_c06_level4_con api.tests.test_roadmap_c03 api.tests.test_roadmap_c05 api.tests.test_roadmap_c09 api.tests.test_roadmap_c06 api.tests.test_roadmap_c06_level3 api.tests.test_roadmap_c06_starting_xp api.tests.test_roadmap_c06_creation_http api.tests.test_roadmap_c06_creation_catalog api.tests.test_roadmap_c06_slot_maps api.tests.test_roadmap_c06_slot2_cast api.tests.test_roadmap_c06_asi_projection api.tests.test_roadmap_c06_asi_persistence api.tests.test_roadmap_c06_mage_armor_option api.tests.test_roadmap_c06_barbarian api.tests.test_roadmap_c06_barbarian_creation api.tests.test_roadmap_c06_zero_hp_progression api.tests.test_xp_v1 api.tests.test_xp_receipt_regression api.tests.test_roadmap_k07_hit_dice api.tests.test_spell_scope api.tests.test_campaign_persistence api.tests.test_death_system api.tests.test_death_bounded
```

The unabridged child command/environment and runtime identity are also in `run-evidence.json`. Guard SHA remains d0803047bca67beec76a27d7825cef6f655bafee81d290d5c940d530ec0a51c5.

## Exclusions and unchanged boundaries

Core creation4 remains blocked; public HTTP/catalog/UI starts remain1–3. Only prior universal applied-cap counterexamples move4→5; skipped-step, malformed4 and creation/HTTP4 negatives remain. No other ASI/general feat, DEX/armor recomputation, complete class/spell effects, Sorcery Point engine, higher XP entitlement, new spell resolver or full C06 claim. No product changes to XP/spell owners, no new blanket combat/incapacitated/action gate, no manual browser acceptance, deployment, commit, push or merge.

Independent scoped approval received. Source remains frozen. Unaffected noncanonical saving totals were tested for transition preservation; their separate offset-specific roundtrip was not a test, but the reviewer inspected persistence code. No additional work is claimed for that nonblocking note.

## One next usable increment

Add a bounded selected level-up command and choice panel to the existing authenticated campaign/session mutation-and-persistence path (`ai-dnd/api/main.py` and `artifacts/ai-dnd-experience/src/pages/game-browser.tsx`). No existing HTTP/UI caller of `preview_level_up`/`apply_level_choices` was found in these owners; current UI displays pending-effect notices and supports starting creation, not earned choice application. The next connected increment should expose server-recomputed preview4 plus exact selected CON+2/fifth-cantrip/seventh-prepared choices, atomic save and fresh resume, with stored-version conflict/rollback behavior reused from existing mutation owners. Keep starts1–3 and do not route it through ordinary combat actions or pretend an advancement endpoint already exists. This is the proposed next implementation, not code delivered or approved by this handoff.
