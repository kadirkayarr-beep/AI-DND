# C06 bounded non-DEX ASI family — scoped HTTP/UI/native acceptance

**2026-10-29, final handoff13:44 UTC. Accepted bounded family, not full C06/ASI.** Core/UI source frozen13:31, API13:32; final440 PASS and independent read-only review GO. Parent completed native odd-CON split, save/restart and owned shutdown13:41. One nonblocking stale preview-disclosure issue remains explicitly recorded below; no frozen product patch was made for it.

## Supported behavior and ownership

Sorcerer earned level4 and existing starting4/5 support fifteen ordinary Ability Score Improvement patterns: five single+2 and ten distinct two+1 among STR, CON, INT, WIS, CHA. Existing C03 feat owner controls eligibility/cap20/deltas; runtime preview is cap-filtered, static catalogue advertises the finite family. DEX is excluded because armor provenance remains unresolved, not because PHB forbids it. Other feats/classes/ceilings stay unchanged.

Existing atomic C06 transaction, normalized single class-level4 ASI record, original origin replay, XP/resource/save and durable receipt owners retained. Old CON+2 JSON/hash/replay preserved. No new endpoint, migration, general feat authority, copy of maximum or client stat authority. Strict finite object union retains each complete valid pattern; malformed/extra/DEX/null/bool/invalidsum requests never silently strip/default to CON.

Affected integer saving totals add exact modifier delta and preserve legitimate extras; unaffected totals remain verbatim. Six strict integer totals replace former CON-only equality assumption. Raw scores, runtime aliases/modifier map/final-score cache synchronize. Three known nonauthoritative player-only spell/passive caches clear on apply/load; NPC caches, DEX, AC and initiative unchanged. Cache clearing is deliberate; serialized player/API character omit these runtime modifier fields. Canonical raw scores/saving totals persist; actual runtime cache correctness is separately exercised by guarded tests, not falsely inferred from absent DB fields.

Base level HP remains existing XP/level owner; only actual CON modifier delta produces attained-level retroactive **maximum-only** gain. ASI never heals current HP. Existing capacity increases preserve spent points/slots/Hit Dice and avoid duplicate awards/HP/resource application on retry/load. The source-driven UI picker has explicit choice/confirmation and same pending/UUID/reconciliation owner; no client caps/HP math or automatic new-family selection.

## Source/evidence bindings

Work root `/workspace/scratch/a1b372df36be/ai-dnd-recovered-work-20261029`; candidate `ai-dnd-recovered-candidate-20261029`. Relative paths below refer to work unless explicit `/tmp` or candidate.

- Plan `C06-nondex-asi-implementation-plan-20261029.md`; native design `C06-nondex-asi-native-fixture-design-20261029.md`. External verified ASI/Sorcerer anchors and original plan member recorded there; no rawbook/screenshot redistribution.
- Before-patch manifest `C06-nondex-asi-prechange-source-manifest-20261029.json` SHA256 `0adf640c9cd1119632a15d1b6f6d155e3a4ca8c1ee4e07befe42c3b74dd35be7` retained.
- Owner handoffs: `C06-nondex-asi-core-handoff-20261029.md`, `C06-nondex-asi-api-handoff-20261029.md`, `C06-nondex-asi-ui-implementation-20261029.md`. Earlier pending labels describe their historical handoff point; this final record supplies subsequent acceptance.
- Core5/API261/UI11 manifests: `C06-nondex-asi-core-source-manifest-20261029.json`, `C06-nondex-asi-api-source-manifest-20261029.json`, `C06-nondex-asi-ui-sha256-20261029.txt`. Combined276 unique frozen paths `C06-nondex-asi-native-source-freeze-20261029.json`, SHA256 `e03fe5862a25c2ad910a2a4e7a626a3e0b18d7deb1f049b38ef0d81d8030991e`. Verified before/after packaging; final documentation-only addition changes no frozen product source.

## Final tests and review — overlapping counts, not additive coverage

- **440 PASS/0 FAIL/0 SKIP,135.111s** in `c06-nondex-asi-final-combined-20261029-1333`. Raw child-1 SHA256 `e17a29e68b5badbedac9d8cf9c02a2a684730c094bd70bb51b9b356897d7be06`; exact33 deduplicated selectors `C06-nondex-asi-final-selectors-20261029.json`, command `run_c06_nondex_asi_final_20261029.sh`, run-evidence.json stores source/child/guard identity. env-i PATH=/usr/bin:/bin HOME=/tmp/ai-dnd-recovery-home TMPDIR=/tmp, existing external Python-I-B and actual B06 guard SHA `d0803047bca67beec76a27d7825cef6f655bafee81d290d5c940d530ec0a51c5` with denied-file proof. Handoff author independently read terminal raw result/hash, not reran suite.
- New9 core tests cover literal15 patterns/repeated restore, cap/static eligibility, real odd/even CON boundaries, raw5/applied3 with spent resources, offsets/cache clear, fresh4/5 fullHP/no awards, forged records/formats4–6, zero/dead and late-fault rollback. Actual spell/skill owners exercised, not only cached formulas.
- New13 HTTP plus prior creation5 passed focused18; final includes them. Actual earned CHA+2/split, starts4/5, strict schemas, cap409 before mutation, stale/foreign/retry/conflict, real SQLite post-receipt-insert rollback and lost acknowledgement. Real Fire Bolt after CHA15→17 uses attackmodifier5/DC13, not Magic Missile inference. Real prior Quickened expenditure retained across split progression: points1→2 solely capacitydelta, slots3/2→3/3.
- Historical actual checkpoint13 CON+2 request/receipt captured before schema change: candidate `ai-dnd/api/tests/fixtures/c06_checkpoint13_con_asi_receipt.json` SHA `ff5a8e4d9f182d3731e4ae756ac560cf9d4707327110e9d0a287ae4e19b7edd6`; literal normalized request hash `ceb5a0e45e65e00c3486315d5891fe18058352465ed3cdc1cca655c08db77c48`. Existing session envelope substitution only on replay; old response/runtime exact, no ASI reapplied, captured header user_version6 restored without migration.
- Actual generated parser contracts12 PASS (six new/six retained), factory/OpenAPI fifteen required strict integer object variants and extra-key refusal; legacy CON alias retained. Installed Orval8.30 operation-local legacy creation strictbody fixes demonstrated parser stripping; no handwritten generated patch/install. Client/Zod typechecks pass.
- Frozen UI normal `/tmp/c06-nondex-asi-ui-full-frozen.log`: standard **172 PASS/1 pre-existing SKIP**, C06 **118 PASS/0 SKIP**. Focused43 `/tmp/c06-nondex-asi-ui-green.log`, library/UI typechecks exit0. All15 creation builder/generated-validator branches plus actual rendered choice/wizard wrappers and shared submitTurn retry tests. Scripted component/closure transport is not native HTTP proof.
- Independent final reviewer reported no blocker and verified frozen source/evidence. Static inspection is not an independently executed test run; native visual actions belong to parent observations.

## Retained failures, not relabelled green

Core initial RED1/2 had malformed cap fixture and missing-ready-assertion errors; genuine RED3 seven methods/20 assertion failures/zero errors retained. Related1 had60/64 pass with four superseded CON-only assertions and a concurrent cap-preflight edit; not final evidence. Assertions were updated only after observed failure to literal offset preservation, strict boolean-invalid save, finite15 preview and still-unsupported DEX; negative tampered split/source consistency kept. Related2 then64 pass.

API genuine newchoice/schema/parser RED retained. Initial green8/9 exposed cap19+2/20+1 producing500; core preflight now returns eligibility refusal before mutation, not an API/main workaround. Old CON replay stayed passing. UI missing choice/summary/null RED retained; null must fail closed, undefined old CON-only draft stays compatible. Initial normal C06 count115 preceded added regressions; final frozen118 supersedes it.

Preflight01 `cloud-nondex-asi-preflight-20261029-01.log/.json` failed an oracle expecting runtime constitution_mod in serialized save. Actual product transition had succeeded; save intentionally omits caches. Corrected preflight02 checks live runtime modifiers and saved origin_choices, no product edit or schema workaround. Both runs preserved.

Parent tool output at13:38:09 records an initial premature native capture before browser traffic failed because requests.jsonl did not yet exist; no phase JSON was written. At13:39 after actual browser resume, legitimate pending capture succeeded, then saved/resumed succeeded. This attempt is a timing/precondition failure, not a passing capture or product defect. Parent terminal/tool history is provenance for that failed invocation; no fabricated standalone raw log is claimed.

## Immutable bounded fixture and preflight

`cloud-nondex-asi-runtime-20261029-01` and ZIP SHA256 `acdb5e8e8a4c5d13dcbcdb542040e2d85b9b6adcf58a7dfa02b2a48c751d05da`:232 files/8 assets, reviewed finite1200s launcher, existing sorcery_points.py included. Synthetic owned principal/SQLite/HOME/tmp, same loopback constraints, no socket launched by worker. Vite build log, factory diff, sourcefreeze, identity and fixture handoff retained. Packaging-time native_tested:false remains historical, superseded by actual proof below.

Canonical public Human Criminal Sorcerer3 uses standard raw8/14/13/10/12/15, legitimate background DEX2/INT1, existing valid skills/languages/spells/Metamagic/subclass/equipment and production start catalog. Actual session `_receive_xp_award(xp.apply_xp, ...,1800,'quest:synthetic-gui-nondex-four')` once. No stat/resource override or detached XP adoption; no encounter/model/general-turn route. Restart reuses seed/campaign, never re-awards.

Pinned actual guard preflight02: create3HP17→realXP raw4/applied3HP22/22→source preview split→actual HTTP apply→HP22/26 CON14/CHA16→save/newfactory exact resume. Confirms live mod caches CON2/CHA3, saving deltas, source capacity points3→4 and slots4/2→4/3, origin unchanged, no repeated XP/HP/heal, same RNG/flags/clock/combat. Exact allowlist only selected split+ShockingGrasp+MageArmor, campaign/action/revision envelope; DEX/otherchoice/generalturn boundary denial separate from product family tests. Capture helper dry-validated on actual guarded output without writing native evidence.

## Parent-managed native acceptance

Campaign `b3fb1ba4-28a9-4a66-a55b-bccb130628b7`, runroot `cloud-native-nondex-asi-01`.

1. Genuine source create3HP17 and one real XP award yield raw4/applied3, XP2700, CON13/CHA15, HP22/22, points3, slots4/2. `cloud-nondex-asi-pending-20261029-01.json` captures baseline after browser resume.
2. Parent opened earned preview, chose source **constitution+1/charisma+1**, Shocking Grasp and Mage Armor, explicitly confirmed and applied through existing pending owner. Exact submitted choices/revision/action trace. Result raw4/applied4, CON14/CHA16, HP22/26 (maximum+4, current unchanged), points4/4, slots4/3. Origin/provenance and single XP award preserved; affected CON/CHA saving totals each+1, unrelated scores/AC/totals unchanged.
3. Parent saved; `cloud-nondex-asi-saved-20261029-01.json` PASS. Controlled restart generation `e9e5475f-6648-45a3-a743-91d65057b166` PID157→`92344e82-6588-4adc-b76f-5f101f907ffb` PID161. Home picker resumed same campaign and same22/26 HP; resumed capture PASS with exact payload/RNG/receipt+intent table hashes:
   - Payload `1f64ed2293fd3d319a3191e40652a56b34c9e82c846ff9f1020b5bb0820a7a0b`
   - RNG `cc0e48f6a8f3858f9aa2b4e44958813b395098a87c95a1fbb2fa4bdb6bc6ca6e`
   - Receipts `3feefc0da087d504d417149d3a2b576746a6373c4d50c129b6b223cd4e8abca0`
4. Canonical flags/clock/combat/award IDs/slot_turn and RNG unchanged across choice; one new level-up receipt, no focus mutation. Capture checks persisted raw scores/saving totals, not absent mod caches. Guarded runtime tests separately validate caches and real CHA cast owner.
5. Parent owned-stop, terminal prompt/ready removal verified, tab15 closed. Handoff author independently inspected all captures and ready absence; no fixture work remains running.

## Known nonblocking disclosure issue

Earned level-up preview can still display stale generic “Sorcery Points untracked”/unsupported-effect wording even when current character's pool is adopted and supported. Parent observed it in this native flow; character panel current resources/disclosure and actual transaction were correct. This is explicitly deferred presentation/projection text, not evidence of missing points or ASI failure. Exact follow-up record `C19-disclosure-nonblocking-issue-20261029.md` and runtime evidence `C19-disclosure-runtime-evidence-20261029-1340.json` preserve the mismatch; no product edits after freeze and no claim that all capability descriptions are consistent. Future correction should preserve old stored receipt replay and avoid broad stale-text rewrites.

## Limits / stopping condition

Native proves one lawful earned odd-CON boundary split and CHA increase, explicit consent, maximum-only HP, source capacity advancement and exact durable resume. All15 family branches, even-CON nonboundary, caps, raw5, starts4/5, legitimate saving offsets, spent-resource preservation and historical CON replay are separately core/API/UI evidence, not fifteen native runs.

DEX/armor ownership, other feats, other class/level ceilings, full ASI/C06/project completion remain open. No live Clerk/model, full browser matrix, deployment/private-publication readiness or exactly-once creation claim. No commit/push/merge/deploy/install/auth/access/security/personal-data changes. Accepted bounded slice is frozen for checkpoint packaging, with disclosed nonblocking stale preview text retained.
