# C19 selected Font slot→points — scoped HTTP/UI/native acceptance

**2026-10-29, final handoff13:21 UTC. Accepted selected slice only.** Core/UI frozen13:01; API focus correction frozen13:13. Independent static review GO; final guarded394 PASS. Parent-managed native attempt02 accepted and stopped13:18. Attempt01 remains **NOT ACCEPTED** due conversation side effect, notwithstanding its resource/persistence PASS.

## Delivered, not blanket Font completion

Exact singleton `combat_action.steps=[{kind:'convert_spell_slot',slot_level:N}]`, strict N1–3, converts one existing slot into N Sorcery Points. Existing typed turn/pending/store/receipt authority, no new endpoint or parallel persistence. Default wire resource'action' is infrastructure, not Action cost; explicit bonus, extra fields and mixed bundles refused.

Current applied Sorcerer2–5 and optional adopted version1 pool remain authoritative. Valid available slot and enough room for complete gain required. This conservative no-overflow support is an engine boundary, not a PHB ruling on wasting excess points. No adoption/refill for absent legacy, load or raw XP; no Quickened-selection prerequisite. Reverse point→slot creation remains unsupported.

Active combat requires current player's participation/living consistency and no pending reaction. Outside combat uses existing living/status consistency without generic Action-condition gating. Conversion charges no Action/Bonus/Reaction/movement and changes no RNG, campaignclock, combat scheduler or slot_turn. Existing logical transaction/turn/history revision may advance. World slots debit1, points creditN; no lagging character-cache mutation or new resource maximum.

API admits only the exact recognized singleton into model-free MechanicalTurnContext. Prose, mixed and unknown commands do not gain a blanket model bypass. Optional adopted-only conversion options and live supported-scope disclosure intentionally change current GET; old checkpoint12 receipt replay remains exact. UI uses authoritative options, initially blank explicit slot choice and confirmation; shared submitTurn/pending/UUID/owner/reconciliation path, no client pool math or debit. Draft resets on context/source/pending/dispatch; placeholder cancels selection.

Final focus fix skips living-world scene planning and neutralizes only effective target for exact resource conversion, preserving submitted request hash/receipt semantics. It neither clears existing valid conversation nor changes ordinary conversation/planning behavior. Native02 verifies no new postkill focus; separate HTTP regression verifies existing actual barmen focus remains intact despite approach caption/stale envelope target.

## Evidence roots and source bindings

Candidate `ai-dnd-recovered-candidate-20261029`; external work `/workspace/scratch/a1b372df36be/ai-dnd-recovered-work-20261029`. Names below are relative to work unless explicit `/tmp` or candidate path.

- `C19-slot-to-points-implementation-plan-20261029.md`, `C19-next-slot-to-points-recommendation-20261029.md`; verified Sorcerer.md148–158 SHA256 `e0e176844a363498f64ba763d970c6cca0b239999e32abaf7886887ae2d13dfd`. Reverse creation159–179 excluded. No raw book/screenshot redistribution.
- Owner records: `C19-font-core-handoff-20261029.md`, `C19-font-http-implementation-ledger-20261029.md`, `C19-slot-to-points-ui-implementation-20261029.md`. Earlier pending statuses are historical; this final record binds subsequent correction/tests/native acceptance.
- Core manifest3, final API manifest247, UI manifest9: `C19-font-core-source-manifest-20261029.json`, `C19-font-http-source-manifest-20261029.json`, `C19-slot-to-points-ui-sha256-20261029.txt`. API prefocus manifest preserved separately, not replaced as evidence.
- Runtime02 combined `C19-font-native-source-freeze-20261029-02.json`:258 unique paths, SHA256 `718c30b48dd082dba3077ed8b81f71347f46704f1486ace4326c8225730f89a7`; all matched before/after build. New handoff is documentation only, frozen product unchanged.

## Final tests and independent review

Counts overlap; do not sum them as unique coverage.

- Final postfocus combined: **394 PASS/0 FAIL/0 SKIP,67.696s**, `c19-font-postfocus-final-combined-20261029-1317`. run-evidence.json statusPASS. Raw child-1 SHA256 `e33b994b01388b126cc023e441a2d0f8759b0418ff2ff59798b12c14a9351e2f`. Exact invocation/selectors in `run_c19_font_postfocus_final_20261029.sh` and run-evidence.json; env-i PATH=/usr/bin:/bin HOME synthetic TMPDIR=/tmp, existing Python, pinned actual B06 guard SHA `d0803047bca67beec76a27d7825cef6f655bafee81d290d5c940d530ec0a51c5` with denied-file proof. Handoff author read terminal raw result and hash, not independently reran suite.
- Prefocus combined383 PASS/65.759s remains historical (`c19-font-final-combined-20261029-1304`), not sufficient to excuse native01 defect. Postfocus HTTP27 PASS/6.328s, ordinary-dialogue regression11 PASS/1.485s; both genuine focus regressions included in final394.
- Focused core34 PASS includes15 new Font plus19 prior Quickened. Tests cover literal slot1/2/3 gain, no Quickened selected, exhausted budgets, malformed/legacy/wrongclass/dead/currentplayer/reaction/cap/slot refusals, raw-XP distinction, pure previews, cast locks both orders, Long Rest and save/rollback.
- Actual HTTP covers adapterNone conversion/model_calls0, no broad bypass, checkpoint12 stored receipt and canonical runtime preservation, intentional new live disclosure, owner/stale/duplicate/lost-ack/storefault/full/absent refusal, unchanged clocks/marker and fresh-manager replay. Actual historical fixture at candidate `ai-dnd/api/tests/fixtures/c19_checkpoint12_adopted_receipt.json`, SHA `dd6f1071ddc2021709bc7751825f71454b362f91e802eb4ca6ccecfa4322043c`; captured original SQLite user_version6 restored without migration or corruption-check relaxation.
- Frozen UI normal `/tmp/c19-font-ui-full-frozen.log`: standard **172 PASS/1 pre-existing SKIP**, C06 **103 PASS/0 SKIP**. Focused37 PASS `/tmp/c19-font-ui-green.log`; library/UI typechecks exit0. Generated final contracts8 PASS (4 Font+4 Quickened), client/Zod typechecks pass. Component/AST/scripted transport tests are not native HTTP/browser proof.
- Independent read-only reviewer gave GO after original scope and focused post-native correction; no remaining blocker. Static review and evidence inspection are not independently executed reruns. Parent owns native visual observations.

## Failed runs retained honestly

Core `c19-font-core-red-20261029-1258`:7 assertion failures/0 errors, genuine missing behavior. First green had4 outside-presence failures; canonical outside admission fixed, not test weakening. API initial schema/transport/disclosure RED and generated-parser RED retained as detailed in ledger. Initial checkpoint12 capture01 write outside approved synthetic DB/tmp subtree was denied; capture02 used approved TMPDIR, no guard relaxation/escalation. SQLdump reconstruction initially lacked captured header version and correctly failed migration guard; restored original captured version, not schema migration. Store fault alias/fixture issues corrected before claiming actual rollback proof.

UI missing-control/wiring/placeholder RED logs retained; initial full run171PASS/1 old exact-JSX-regex failure/1skip. Tests updated to exact new approved prop shape, no removed read-only assertions; final frozen suite clean except pre-existing skip.

### Native01 failure, cause, RED→GREEN

Preserve `cloud-font-runtime-20261029-01`, archive, preflight01/02, native runroot and all three captures unchanged. `cloud-font-native-01-acceptance-blocked-20261029.md` records explicit rejection. Conversion succeeded with expected resource/debit/persistence but unexpectedly set last_npc_id/active_npc_id null→npc_001 and expiry−1→10, activating dead Commoner conversation. Fixture rejected any non-null conversion target, proving no stale target was submitted. Generic scene planner inferred person-directed caption and mutated referent focus before resource dispatch. UI displayed real erroneous state; no UI masking used.

Genuine `c19-font-focus-red-01` reproduces canonical source Commoner/actual UI caption untargeted; `c19-font-focus-red-03` reproduces existing barmen focus replaced under stale target/approach caption. Red02 compound caption happened not to reproduce and passed, not mislabelled RED. Minimal fix only API main/test; core/game/dialogue unchanged. Green27 plus dialogue11 then final394 pass. `cloud-font-capture-focus-red-20261029.log` additionally demonstrates new capture invariant fails on preserved native01, read-only with no overwrite.

## Immutable runtime02 and guarded preflight

`cloud-font-runtime-20261029-02` and ZIP SHA256 `c49cbf90a335a6d328f655c2cd855580030efed22789b608f91455801a227768`:232 files/8 assets, same reviewed finite launcher and synthetic owned identity/DB/HOME/tmp. Existing sorcery_points.py explicitly included; no installation. Build log `cloud-font-build-20261029-02.log`; factory diff02, identity, combined source freeze and `cloud-font-fixture-handoff-20261029-02.md` retained. Identity native_tested:false is historical packaging-time truth; actual acceptance below supersedes, not overwrites it.

`preflight_font_02.py`, `cloud-font-preflight-20261029-03.log/.json`: pinned actual no-socket guard, archive verification, actual factory adapterNone; canonical public Sorcerer2 and selected Quickened, source Commoner4HP ENTER/START, real Dash→Quickened natural defeat→outside conversion. No HP/stat/RNG/resource override, model, alternate encounter or reseed. Three operations diagnostics model_calls0. Conversion keeps RNG/clock/combat/slot_turn/all nonlogical flags/public conversation exact, old turn receipts exact plus one new receipt; save/fresh factory exact payload/receipts. Fixture boundary negatives do not replace separate API predicate tests. Capture02 saved-phase assertions dry-validated against actual guarded snapshots; no native evidence fabricated. Worker never launched sockets.

## Parent-managed native02 — accepted bounded proof

Campaign `18780009-f27f-4c52-9424-834b41e98520`, runroot `cloud-native-font-02`.

1. Parent used actual Dash, selected source target/slot1, explicitly checked Quickened; actual Magic Missile dealt **10 damage**, Commoner4HP→0 naturally. Points0/2 slots2. `cloud-font-quickened-20261029-02.json` captured real committed state before conversion.
2. Opened character drawer, observed blank slot choice, selected1, clicked conversion. Points1/2 slots1; no “Konuşuyorsun” bar. Typed trace exact single convert_spell_slot1, result slot_spent1/points_gained1/remaining1. UI Save then `cloud-font-saved-20261029-02.json` PASS.
3. Capture verifies RNG/clock/endedcombat/slot_turn and all canonical flags except permitted logical turn_index unchanged: last_npc_id=null, active_npc_id=null, active_npc_until_turn=−1, pending_destination=null. Public conversation remains `{active:false,interlocutor:null}` before/after. Old turn receipts unchanged and exactly one new conversion receipt; normal logical revision is allowed.
4. Controlled restart generation `098ad762-52d5-4751-9a88-1c40edbcf1d4` PID148 → `b18ef013-28cb-49d2-9022-4be572ce93e6` PID152. Parent resumed same campaign, confirmed points1/2 slots1 and no conversation bar. `cloud-font-resumed-20261029-02.json` PASS exact saved payload/RNG/all captured receipt+intent table hashes:
   - Payload `1b39a59b09aeea153ef7452e5f3957958e0484964890bfaf111125f6bcec14fd`
   - RNG `90a8fd680372b6fa7e3ec3937dd3cd489ce8fcd94c525d0075ecdc90bee44f9d`
   - Receipts `7a855024b594f3c3aedca246344c8d0a6d8d71b7fdc06856810cdb4ce7908990`
5. Parent issued owned stop, verified terminal prompt/ready.json removal and closed tab14. Handoff author independently inspected all capture values and ready absence. Nothing remains running for this acceptance.

## Limits and freeze

Native proves selected slot1→points **outside combat after natural defeat**, explicit selection, precise debit/gain, unchanged focus/conversation and durable restart. Active-combat no-Action conversion, preserving existing active focus, slot2/3 and historical checkpoint12 receipt compatibility are separate core/API evidence, not native claims. Natural kill clears combat economy; no postkill Bonus-spent flag or surviving-target Action claim.

No reverse slot creation, full Font/C19/C06/class completion, full browser matrix, live Clerk/model validation, deployment/private-publication readiness or exactly-once creation certification. No commits/push/merge/deploy/install/auth/access/security/personal-data changes. Slice is complete and frozen for checkpoint packaging; retain failed01 plus corrected02 and all raw evidence. Further mechanics require new scope, not automatic reverse conversion.
