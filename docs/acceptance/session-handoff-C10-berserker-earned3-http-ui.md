# C10/C06 — selected earned Berserker3: scoped acceptance

Frozen handoff: 2026-10-29 16:15 UTC. **PASS for canonical earned Barbarian2→3, selected Berserker/one additional skill, spent Rage capacity delta, actual Frenzy, and corrected desktop pointer flow.** Not complete C06/C10/class/subclass coverage. Parent performed native GUI actions and reported independent source/evidence review GO; this handoff binds inspected raw tests and structured native evidence. Static review is not an independent rerun.

All external evidence names below are relative to sibling `ai-dnd-recovered-work-20261029/`.

## Source and product boundary

`C10-berserker-earned3-implementation-plan-20261029.md` binds verified Barbarian source table/Primal Knowledge/Frenzy (`barbarian.md` SHA `7c9beb785364945923f78a9b0fd9830786c3b33d4838ea545847b3ad1d9c41f2`). Exact earned choices are `subclass_id: berserker` and `primal_knowledge_skill` selected from unowned canonical class skills. Public starting creation remains capped at2; no creation3 union/grant.

`primal_knowledge_choice` stores class_level3, chosen skill and exact prior ordered proficiency baseline; current skills must equal prior+[chosen]. Origin/species/expertise provenance is preserved, no load append or legacy adoption. Ordinary skill checks use the added proficiency; optional Primal Knowledge Strength substitution is explicitly **deferred**, not silently automatic. Rage capacity follows applied selected provenance:2→3, remaining gains only1 rather than refill; active clock/turn markers unchanged. Absent legacy capability refuses this transition. Existing XP HP award is paid once; apply does not pay again/heal zeroHP. Active-combat participant synchronization preserves exact save/load state.

Frenzy applies on the first qualifying Reckless Strength hit while raging:2d6, or4d6 on a critical; flat Rage+2 once, PB only on attack. Broader live once-per-turn/critical/negative cases belong to backend tests, not the one native kill. Shared pure progression disclosure now separates adopted supported effects from genuinely pending features; live copy intentionally changes without rewriting historical receipt bytes. The previous C19 blanket-stale-disclosure issue is addressed by this shared owner for adopted capability facts, not a claim all pending features became implemented.

Freeze bindings: `C10-berserker-core-manifest-20261029.json`, `C10-berserker-api-source-manifest-20261029.json`, `C10-frenzy-frozen.sha256`, `C10-berserker-ui-sha256-20261029.txt`; later CSS-only correction `C10-composer-layout-ui-sha256-20261029.txt`. Immutable01 uses311-source `C10-berserker-native-source-freeze-20261029.json`; final03 uses313-source `C10-berserker-native-source-freeze-20261029-03.json`, rechecked after build and this doc-only write.

## Tests and failures retained

Final guarded aggregate `c10-berserker-final-combined2-20261029-1557`: **1129 PASS, 0 failures/errors/skips,190.874s**. Inspected raw `child-1.raw.log` SHA **`4a10403b09b2a4f90dfccb1b946a89313c79506afdf8c4c90889e08b1d57cb92`** and B06 guard proof; guard remains `d0803047bca67beec76a27d7825cef6f655bafee81d290d5c940d530ec0a51c5`. `run_c10_berserker_final2_20261029.sh` binds command/selectors. Subsequent product change is frontend CSS only; backend was not changed or falsely claimed rerun.

Retain first aggregate `c10-berserker-final-combined-20261029-1553`:1129 methods, one stale false-disclosure assertion failure,181.752s, raw `6badb659573266d03edb31eb68f7a0566189a575797abced0df17ddf5fde1167`. Exact test-only assertion correction was intentional adopted-capability disclosure, not preexisting baseline failure or weakened mechanics. Core ledger records genuine initial RED, combat participant exact-restore mismatch RED and malformed bare3 capacity RED; also wrong test-method call, too-broad cap-oracle correction and one noncanonical synthetic HOME invocation. Later final guarded run is authoritative; none are erased.

`C10-berserker-core-handoff-20261029.md` records final49PASS/0.786s (17 new plus related), core boundary/rollback/legacy/zeroHP/skill consumer and cap tests. `C10-berserker-api-ledger-20261029.md`: genuine HTTP RED and generated-contract RED; final36PASS/5.366s, four focused disclosure PASS, generated10/typecheck PASS. Covers actual SQLite precommit rollback/retry, lost acknowledgment/status, stale/owner/conflict, spent active capacity, actual Frenzy receipt/fresh replay, unchanged old request hashes and genuine CON/Quickened stored receipts. New live prose digest intentionally corrected with absence/no-adoption assertions; no fabricated historical Barbarian receipt. Frenzy consumer evidence is separately bound by its frozen manifest/progress ledger. Counts overlap; do not sum them as unique.

Initial Berserker UI focused40, standard172PASS/1 existing SKIP and C06146PASS. Final composer-layout regression focused15PASS/typecheck0; standard172PASS/1 existing SKIP and separate C06149PASS (`/tmp/c10-composer-layout-full.log`, implementation note/manifest). These are distinct overlapping chains, not an added unique count. Existing toolchain only; no install.

## Native01 and diagnostic02: preserve the real failure

Runtime01 ZIP SHA `a393c4c07d041314265695b4a846967f77c7a0ac24daef678e5d292336121eef`. Native01 mechanics succeeded: earned apply preserved active12 and remaining1→2/max3, actual Reckless/Frenzy18damage, exact save/restart. But Hamle yap mouseclick afterapply was obstructed; keyboard Enter opened composer. This is **not clean mouse acceptance** and not a mechanics failure. Native01 saved payload `04587c68198ba0e48ea467952fb77787fa55e9ed9e787c5e03ebf26cf9eefbec`, RNG `2e75ae31627bfd068419397be5074379e5ef086ea40890682df635ace3977248`, receipts `90a6f516e36564a1d55c8e66d6364020bce94b6dab4eeebda837aa3245ffbb06` remain retained.

Diagnostic02 launched the **same unchanged01 archive** at separate `cloud-native-berserker-diagnostic-02`, no rebuild. Actual pointer RED: transcript wrapper height0/top567.5/overflowvisible, child minimum320 extended to887.5 over button y677..721; center hit `p.story-text`, click textboxcount0. No attack required. Parent stopped/closed diagnostic02. `C10-berserker-native01-mechanics-and-mouse-issue-20261029.md` and parent DOM evidence preserve this. UI owner then changed only `unwritten-play.css` product layout, with targeted tests/registration. No hidden backend workaround, keyboard substitute or source erasure.

## Final immutable03 and setup attribution

`cloud-berserker-runtime-20261029-03` ZIP SHA **`3af6fc10b223dcb5eece28df5d6f1d152293cda1446cb57faf952979678b9ab6`**,233files/8assets. `cloud-berserker-runtime01-to03-delta-20261029.json` proves all backend and factory bytes identical; only static assets changed. Identity, launcher, build log, sourcefreeze and `cloud-berserker-fixture-handoff-20261029-03.md` bind finite1200s runtime/root `cloud-native-berserker-03`. Worker never launched sockets. Guarded ASGI preflight01/03 PASS actual modelNone factory, selected apply, natural attacks, save/fresh resume. No RNG/hit/HP overrides.

Setup is explicitly **not GUI**: actual canonical new HumanBarbarian2, Criminal classA/backgroundB, source corrected Greataxe/four owned Handaxes/opaque pack and6500CP, training and known-unarmored Rage2. Existing materializer supplies IDs. Source Commoner HP4/AC10 via bounded ENTER/START, lawful EndTurn only if needed for reach. Actual activation owner consumes Bonus and pool2→1, active12; actual `_receive_xp_award(xp.apply_xp,+600)` produces raw3/applied2 XP900, HP32/32. Seed records owner effects. No arbitrary wait/refill/clock/stat manipulation. Action remains available; no GUI reactivation is needed or claimed.

## Final native03, parent desktop pointer PASS

Campaign `cf904514-ff8b-48b4-8283-ed73ab2479da`; `cloud-berserker-{pending,applied,saved,resumed}-20261029-03.json` all PASS.

1. Parent home-picker resume and pending capture before apply: raw3/applied2, XP900, HP32/32, spent active Rage remaining1/max2.
2. Actual GUI selects Berserker and unowned Survival with explicit confirmation. Applied capture **before attack** proves prior ordered skills+[Survival], exact provenance record, remaining2/max3 (not full3), identical active12 record/clock/RNG/gear/currency/origin/expertise; HP still32/32, no duplicate award. Pending/applied RNG SHA `a9e2e86c68a9d61635fd1f11dd5b8d3c4349c3720f5b4cf3cb2593261682341d` unchanged.
3. Actual mouse Hamle yap opens composer twice, including close/reopen. `C10-composer-native-hit-test-green-20261029.json`: after real workspace scroll, center hit BUTTONtrue; wrapper and child each320px, bottom571.5; button y681.09375..725.09375, no overlap; textboxcount1. Parent observed unobstructed story after real right-workspace scrolling, no JS state mutation. This is desktop-native proof only, not all viewports/mobile.
4. Actual explicit Reckless Strength Greataxe hit naturally defeats Commoner4→0: damage16 = weapon d12 roll1 + Frenzy d6 rolls5,6 + STR2 + Rage2. PB2 is attack-only. No forced hit or 2014 exhaustion/bonus-attack behavior.
5. UI Save → controlled process restart → same-campaign home-picker resume. Exact full payload/active Rage/provenance/receipts/RNG. Natural combat cleanup removes turn_resources; no postkill live Frenzy-used marker persistence claim. Backend live combat tests own that marker proof; native owns observed dice/result/receipt and cleanup state.

| Final saved = resumed | SHA256 |
|---|---|
| Payload | `eab89fe1c01e5af153d3a771f5a99bd06d8e6602188ca32e380649d155afbfc2` |
| RNG | `f06e335ae32518c1c00d0a34081d50a7c1f8618f5b04575e6a40617e0cf7189d` |
| All receipt tables | `9f481985df291a2b08046424a0b1ac85b635fa29531bc6cd7d6071724423f1f0` |

Generation `ff684423-621b-4505-a6c8-4decfd9f0709` PID231 → `b0bae1a9-c392-451c-bcbc-ab068b11a59e` PID235. Real process replacement, not reload. Parent confirmed final03 shell prompt returned at16:14:31 and tab22 explicitly closed; ready03 absence was independently checked at16:15:14 and at handoff. Earlier01 prompt/tab20 closure16:05:54 and diagnostic02 prompt/tab21 closure16:08:11 were also confirmed. All owned native runs stopped.

## Open scope / backup

No public creation3, Primal Knowledge Strength substitution, all subclasses, higher features, complete Rage routes, full class/C06/C10, mastery, general armor/Unarmored Defense or opaque pack contents claim. Uncertified background wealth remains partial as documented previously. Deterministic engine/modelNone fixture does not prove model narration, Clerk or production authentication. No push/merge/deploy/security/personal-data changes.

Preserve01 mechanics captures,02 real pointer RED and launcher,03 pointer GREEN/four captures, runtime01/03 ZIPs/identity/sourcefreezes and static-only delta, all failed/final raw/guard evidence, source manifests, preflight/build/helper/launcher and UI records. Exclude screenshot binaries/live SQLite databases from checkpoint. No product edits while writing this handoff.
