# C10 selected Rage1–2 — scoped HTTP/UI/native acceptance

**2026-10-29, final handoff14:42 UTC. Accepted bounded leaf, not full Rage/C10/C06/class completion.** Final corrected-feedback aggregate1008 PASS and independent static GO. Runtime01 comprehensive mechanics/rest native proof and runtime02 narration correction proof are separately source-bound. Both owned fixtures stopped; no further native process pending.

## Implemented scope and ownership

Canonically created, source-known-unarmored applied Barbarian1/2 has optional strict `world_state.rage_v1` pool0..2/active record and `worn_armor_v1={version:1,armor_id:null}` proof. Proof comes only from existing creation/equipment owner; no AC/inventory guess or legacy migration. Missing proof/pool stays absent; formats4–6 supported, wrong class/shape/type/levels/proof refused. Applied1→2 preserves spent uses. No new save version, scheduler, endpoint, XP or receipt authority.

Activation/manual extension reuse current-player combat Bonus Action through exact singleton commands `{kind:'activate_rage'|'extend_rage',resource:'bonus'}`. Explicit extra/null/target/mixed/action-default shapes reject. Out-of-combat activation/manual extension is deliberately unsupported engine scope, not a PHB prohibition. Pure projection never adopts/refills/advances time. Existing pending/revision/ownership/replay/rollback remains authoritative.

Active selected benefits: +2 flat damage for supported Strength weapon/unarmed damage, B/P/S resistance through existing mitigation order, Strength checks/saves advantage, supported spell-cast refusal and qualifying enemy-roll/save extension. Flatbonus before clamp/mitigation and once on critical; STR8 unarmed max(0,1−1+2)=2, inherently nondamaging grapple/shove excluded. Existing resistance/immunity/vulnerability and Reckless cancellation remain owned by prior resolvers. Current death/zeroHP/incapacitation mutation observations terminally clear activity; unsupported general condition/concentration routes are not invented.

Duration is a pinned **engine bridge**, not source text defining free-running seconds: initial12 softseconds, actual own END subtract6 once per combat/attack-turn identity; later qualifying extension refreshes12 without changing started_at. Outside actual elapsed time decrements exact soft budget; combat round clock does not double-debit it. Every mode enforces started_at+600 hard cap; fractional1–5seconds never round up on reentry. Old-mode settlement before combat transitions keeps natural-kill Rage active. No UI timer, wallclock polling, button-time debit or reload refresh.

Completed Short Rest restores one capped at2, completed Long Rest full2. Scheduled interrupted Long Rest before3600 restores none, at3600 grants only Short Rest benefit, not full recovery/completion stamp. Other interrupted species-recovery behavior remains outside this fix. New UI requires explicit confirmation, uses authoritative availability/resource snapshot and existing mutation owner; read-only CharacterPanel retains active status outside combat. No class/armor inference or client expiry math.

## Source and evidence bindings

External work root `/workspace/scratch/a1b372df36be/ai-dnd-recovered-work-20261029`; candidate `ai-dnd-recovered-candidate-20261029`. Names below relative to work unless `/tmp` or candidate specified.

- Plan `C10-selected-rage-implementation-plan-20261029.md`; source Barbarian.md47–80/96–97 SHA256 `7c9beb785364945923f78a9b0fd9830786c3b33d4838ea545847b3ad1d9c41f2`; original approved C10 plan anchors and exact bridge decisions recorded there. No rawbook/screenshot redistribution.
- `C10-rage-core-handoff-20261029.md`, `C10-rage-combat-progress.md`, `C10-rage-api-ledger-20261029.md`, `C10-rage-ui-implementation-20261029.md` preserve owner evidence and earlier statuses. Final acceptance below supersedes pending labels without rewriting old claims.
- Core7, mechanics afterSHA, API final manifest and UI9 hashes: `C10-rage-core-source-manifest-20261029.json`, `C10-rage-combat-after.sha256`, `C10-rage-api-source-manifest-20261029.json`, `C10-rage-ui-sha256-20261029.txt`. Prechange and core-prefeedback manifests retained.
- Runtime01 combined284 paths `C10-rage-native-source-freeze-20261029.json` SHA `2e63ecef5c9e124939a46f1156bb85b5cc652df435340ae9758f642c69c1026f`; runtime02 final285 paths `C10-rage-native-source-freeze-20261029-02.json` SHA `9a696bd82965a82ef45ff344de72ac8ba59ac54650e3607ec2be47290f08a61c`. All final paths verified after build. This handoff adds documentation only.

## Final tests / review (overlapping, not additive unique counts)

- **1008 PASS,0 FAIL,0 SKIP/193.282s**, `c10-rage-final-combined3-20261029-1433`; raw child-1 SHA256 `ea180173397de7f5e0f59dc59b4e74800ee9ecf3fd4be02d2416ba216704850d`. Same46 deduplicated modules `C10-rage-final-selectors-20261029.json`, exact env-i invocation `run_c10_rage_final3_20261029.sh`, full child/source identity in run-evidence.json. Actual frozen B06 guard SHA `d0803047bca67beec76a27d7825cef6f655bafee81d290d5c940d530ec0a51c5` denied-file proof; existing external Python, synthetic HOME/TMP, no installation. Author independently inspected raw terminal result/hash, not independently reran suite.
- Core actual canonical proof/pool/save, legacy absence, strict raw/applied order, actual XP-ahead5, exact use/Bonus and END, fractional reentry, actual round-clock no double cost, later extension,599/600 cap, Long/Short Rest and real scheduled3599/3600 interruption, shared timed route without speciesstate, actual zeroHP/terminal condition, repeatedrestore and late fault rollback.
- Mechanics actual Strength attacks/unarmed/critical and zero subtotal, defense damage order, Strength check/save advantage/cancellation, enemy extension before lethal cleanup, ally/companion exclusion, supported spell block and failure rollback. Surviving targets, injected clocks/conditions/faults are declared synthetic branch tests—not native encounters.
- HTTP actual typed commands/projection, source canonical creation, strict singleton schema, ordinary hash/legacy omission, no-focus activation, owner/stale, precommit/real SQLite error, lost acknowledgement/exact replay, fresh manager and historical stored response. Corrected narration tests prohibit mechanic and renderer rerun on stored replay; no old receipt rewriting. Generated parser/schema/typecheck evidence remains API-owned.
- Frozen UI `/tmp/c10-rage-ui-full-frozen.log`: standard **172 PASS/1 pre-existing SKIP**, C06 **129 PASS/0 SKIP**. Focused45 `/tmp/c10-rage-ui-green.log`; library/UI typechecks exit0. Genuine checkbox/panel wiring RED, actual hook-boundary reset/duplicate/Bonus summary plus existing exact UUID lost-response retry. Scripted component/transport tests are not native proof.
- Independent static reviewer found no blocker on strict proof/lifecycle/benefit boundaries and later narration-only correction. Static/evidence GO does not mean independent reruns or reviewer-operated native acceptance; parent owns actual UI observations.

## Failures retained without baseline laundering

Core8 genuine missing-behavior RED; strict rawbool RED; review2 genuine failures for soft-expired outside save and interrupted3600s recovery, then corrected core41 PASS. Mechanics initial red attempts and Danger Sense fixture errors retained: synthetic fixtures deliberately corrupting class/applied state now remove unrelated optional Rage/proof first, not weaken new validation. Owner logs distinguish oracle/precondition errors from genuine assertions.

First aggregate `c10-rage-final-combined-20261029-1417`:1005/1006 PASS, one creation_http random-one assertion failed because newly admitted Barbarian1 legitimately has Rage/pending disclosure. This was an intentional new live-projection change, **not a preexisting failure**. Test corrected narrowly to assert canonical proof/pool2/inactive/disclosure for Barbarian while unrelated classes retain absence assertions; no product patch. Focused creation8 PASS; combined2 then1006 PASS/188.908s, rawSHA `0e899710aac6de3d4c5924134903af454beeb8d3e69a55d0e1caa33d46e5d54b`. Final1008 supersedes it after feedback fix, counts not summed.

UI old AST harness ReferenceErrors after new imports retained; actual exported helper/control injected, no assertions removed. Initial UI normal result preceded final generated-type/reset additions; frozen chain supplies final counts.

### Runtime01 missing activation summary → runtime02

Runtime01 successful activation mechanically debited/activated correctly but displayed generic failure-style fallback because completed Rage kinds had no `action_economy.resolved_narration` summary. Keep observation and all01 captures; this was **not** a mechanics/rest failure. Core `c10-rage-narration-red-20261029-1432` has one actual assertion failure across two methods; API `c10-rage-narration-http-red-01` has two actual HTTP assertion failures. Core17/API3 then GREEN. Strict completed active/integer remaining-count guard avoids claiming success for malformed results.

Only product delta is10 lines in `ai-dnd/action_economy.py` resolved_narration activation/extension summaries; no benefit/time/resource/persistence owner changed. `cloud-rage-narration-product-delta-20261029.diff` and `cloud-rage-runtime01-to02-delta-20261029.json` map exact runtime members: action_economy.py plus fixture manual_c06_fixture.py adds response narration trace; **all static assets identical**, every other runtime product member identical. Comprehensive01 mechanics/rest can therefore be paired honestly with focused02 feedback proof; full guarded02 preflight also reran mechanics/rest.

## Immutable fixtures / no-socket preflight

Runtime01 ZIP SHA `8494ae76a59dbff0cd28183ea38e96b917f29fa898c4174fb43886effd1f90d5`; runtime02 ZIP SHA `ccfb00fe53aecd065d53baf06329dec51619d6c65e8307c094cb1a12f984e66f`. Both233files/8assets, newbarbarian_rage.py explicit inventory plus current game/effect_lifecycle/equipment/creation/weapon/spell owners, same reviewed finite1200s launcher/synthetic identity/owned DB/HOME/tmp/loopback. Packaging identities' native_tested:false stay historical packaging truth, not overwritten after actual proof.

Canonical direct public Human Criminal Barbarian2, source Greataxe/unarmored proof and normal2use pool; existing equipment materialization, source Commoner4HP ENTER/START. Natural own endturn only if needed to let authored Commoner reach5ft; no HP/geometry/RNG/armor-proof override, no detached recreation, no XP award/reseed. Boundary exact RageBonus, Recklessattack, natural endturn and existing exact short_rest endpoint. No new timeUI/model/generalturn bypass.

Pinned guarded preflights01/02 and corrected-feedback03 use actual factory adapterNone without sockets: activate→naturalhit→Rage remains afterkill→active save/freshresume→real3600s ShortRest expiry+one-use recovery→rested save/freshresume. Corrected03 also checks exact narration. Capture helpers dry-validated against actual guarded snapshots; no native evidence fabricated. Build logs/factorydiff/identities/handoffs and all preflights retained. Worker never launched native sockets.

## Native01 comprehensive mechanics/rest proof — parent observed

Campaign `b05060ac-4e2a-449b-847a-165d2312fca6`, root `cloud-native-rage-01`. Explicit rage-confirm/activate, authoritative use2→1 and Bonus spent/Action free. Explicit Reckless/Greataxe hit **7 damage=die3+STR2+Rage2**, source Commoner4HP→0; active12seconds/use1 remains outside combat. No forced hit or reseed. Parent Save then `cloud-rage-saved-20261029-01.json`, controlled restart then `cloud-rage-resumed-20261029-01.json`, exact active state/proof/RNG/receipts:

- Active payload `4d4f34505610bda11ab331aa2d820ece0ea264375f81ed1ca9e8195978c7bd08`
- Active receipts `a05d36b22faefc6c9f15396124d0d4d4ec1b84ac654f63a4961d81364f6efe35`
- Generation `161e60fc-8b44-46b2-8dbf-36a13e42caad` PID166→`23fd75c6-8491-4b36-bb0a-cfaf84ed9cd3` PID170.

After active persistence proof, parent worlddrawer→Combat→existing `species-action-short-rest`: actual3600seconds completed, Rageinactive and use1→2. This jointly proves **expiry AND Short Rest recovery**, not isolated soft-expiry or fractional reentry. Parent saved/rest-captured/restarted again; `cloud-rage-rested-20261029-01.json` and `cloud-rage-rest-resumed-20261029-01.json` PASS:

- Rested payload `e412459d3520e2e5a3759f0922eff61a120180b068bededdf947759bd36a98f8`
- Rested receipts `12a63321ce9b5900ff8a1970277494fca67a5c13ae52ac165bd920b437ebafab`
- RNG throughout active/rest phases `3df42102843cbcc5037111d9a0a33f952803a7a728076f6405aa5745d68b2233`
- Second restart generation `46ebdfa2-c74a-49b6-ba4d-7e43c2105e05` PID175.

Parent owned-stop/prompt/ready removal and tab16 close; handoff author inspected all four captures and ready absence. Source proof immutable; no refill on load, exactly one new rest receipt, prior turn receipts retained.

## Native02 corrected-feedback proof — parent observed

Campaign `cdb89ecf-c5b4-421e-8afc-9c582dd863a7`, root `cloud-native-rage-02`. Explicit activation story now exactly **“Bonus Action ile Rage başlatırsın; kalan kullanım: 1.”** and active12seconds/use1, Bonus spent/Action free. Brief flow deliberately did not attack/endturn/rest; runtime01 owns those native observations. Parent Save/restart/resume kept exact activecombat payload/RNG/receipt and correct story. `cloud-rage-feedback-saved-20261029-02.json` and `cloud-rage-feedback-resumed-20261029-02.json` PASS:

- Payload `2ec1e90b2542f039700defc1ba3d8489876f6562f052071cce11505865cb21be`
- RNG `2e0178912a7afeef2680e848f7748bf4f4a8329165f823f593badb6d37961bd7`
- Receipts `d42d9e980ce428a21dd56fe0727befb0752e60ceb7f7261bcadd0dba8d8d819e`
- Generation `9b4c69bf-311c-4113-b662-dc2687f26315` PID180→`da96f962-b4c2-42e3-bf75-7e85b195d5a5` PID185.

Parent owned-stop/prompt/ready absence/tab17 close14:38. Handoff author independently inspected both captures and confirmed both01/02 ready files absent. No active fixture remains.

## Open gaps / honest limits

- **Greataxe proficiency gap:** canonical Barbarian2 source Greataxe attack currently reports proficient:false/attackbonus2, omitting expected weapon-proficiency contribution. Rage damage itself independently shows die+STR2+Rage2. Recorded in `C10-rage-native01-mechanics-and-known-gaps-20261029.md`; not silently fixed, not claimed complete weapon/class integration. Follow-up needs existing gear/proficiency owner/source work.
- **C19 stale preview disclosure** remains open: `C19-disclosure-nonblocking-issue-20261029.md` and `C19-disclosure-runtime-evidence-20261029-1340.json`. Existing level-up/generic source text may disagree with live adopted-resource support; no frozen broad copy patch.
- Rage native proof covers actual activation, Strength damage/Reckless, natural-end persistence, active save/restart and complete Short Rest time/recovery. Defense/STRsave/check/critical/miss extension, later-turn extension, fractional/hardcap/reentry and interruption branches are separate backend tests, not all observed native paths.
- General armor/don-doff, Unarmored Defense, Weapon Mastery, other classes/subclass3+, arbitrary concentration/condition routes, out-of-combat activation/manual extension and broader C10/C06 remain open. No full Rage-all-routes, full project/browser matrix, live Clerk/model, deployment/readiness or exactly-once creation claim.

No commits/push/merge/deploy/install/auth/access/security/personal-data changes. Final bounded acceptance complete; preserve all failures and both source-bound native proofs for checkpoint packaging. Further gaps require separately approved scope.
