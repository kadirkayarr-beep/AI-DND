# SDD ledger — plan: docs/superpowers/plans/2026-11-26-borc-sifirlama-plani.md

## G0.1 — Kadir answers applied (2026-11-26, "Hepsi öneri")
- Answers written to docs/agents/borc-sorulari-20261126.md (S1..S39).
- Closed (27): wontfix (Kadir, S2-S9): D-320, D-021, D-343, D-404, D-424, D-327, D-246, D-168. ertelendi S10/S11: D-149, D-307. ertelendi S12 (17): D-312, D-315, D-029, D-022, D-025, D-026, D-014, D-009, D-169, D-271, D-042, D-048, D-050, D-058, D-358, D-066, D-023.
- Noted, still open (29): D-024 (S1, waits Jarvis PHB p.376), D-177, D-262, D-263, D-260 (G1.3), D-530 (G1.8), D-592 (S18 b; closes in G1.8 per Ruling), D-425, D-419, D-012, D-498, D-403, D-451, D-349, D-536, D-445, D-490, D-544, D-286, D-287, D-253, D-381, D-382, D-310, D-589, D-591, D-600, D-598, D-599.
- Open count (plan definition, 284 before): 284 -> 257 (D-023 also leaves the hand list because it is now ertelendi). Script count says 258 with D-023 still hand-listed.
- Ruling: S24-S30 rows get a note only, closed in their own G2.x/G3.x tasks — G0.1 scope is S1-S12 — wrong costs a one-line status edit.
Task G0.3: complete
Task G0.2: complete (branch task/borc-g02-20261126, head 53d1b301, merge none: branch had no commits and was already an ancestor of the wave branch)
- Ruling: D-086 closed on the plan's already_fixed basis (revert confirmed); CI trigger stays unknown, noted in the cell — wrong costs a one-line status edit. D-517 stays "kısmen" (verifier: remainder is live by design). Park: plan G0.2 names nonexistent module test_turn_core_route (real: test_engine_parts_pilot.TurnCoreRoute).
Task G0.5: complete (branch task/borc-g05-20261126, head 404f8f36, merge cc33008c)
Task G0.4: complete (branch task/borc-g04-20261126, head cc33008c, merge none: branch head already an ancestor of the wave branch; measurement file olcum-g04.md, D-302 closed per R-D078)
Task G1.4: complete (branch task/borc-g14-20261126, head 4790fd35, merge a6b2acc8)
Task G1.1: complete (branch task/borc-g11-20261126, head 510a64a6, merge d6a05637)
- Ruling: D-531 closed by G1.4 although create_app is still 477 lines — plan G1.4 owns D-531, Opus review approved the split, remaining routes are cohesive app wiring — if wrong, reopen as a size row in a later wave.
- Ruling: flag-on runs in round 1 for G0.2, G1.1, G1.4 used labels without the fon token, so they ran flag-off; G1.1 and G1.4 rechecked flag-on in round 2 Recheck; G0.2 had no code change.
Task G1.5: complete (branch task/borc-g15-20261126, head 91935555, merge 1ab4a501)
Task G1.2: complete (branch task/borc-g12-20261126, head f6f59c4d, merge 3f65ba71)
Task G1.6: complete (branch task/borc-g16-20261126, head a336aa12, merge 79390bba)
Task G1.7: complete (branch task/borc-g17-20261126, head 485f3bb6, merge f97afe77)
Task G1.3: complete (branch task/borc-g13-20261126, head 08ecabab, merge 322eb7ec)
Task G1.8: complete (branch task/borc-g18-20261126, head 1e978cdc, merge 5886f800)
Task DK1.1: complete (branch task/borc-dk11-20261126, head d827a075, merge a8212fef)
Task DK1.2: complete (branch task/borc-dk12-20261126, head d5aa5402, merge ffd9213a)
Task DK1.A: complete (branch task/borc-dk1a-20261126, head b0596a63015556a5477536b9e6e03fadd5c9116d, merge 2d6e77bc8ffe553804ba75689725753faa40aea0)

Task DK1.B: complete (branch task/borc-dk1b-20261126, head 1ce42a4bf57137b82a7e3447b18fe03b5d93aa35, merge 205f151af75a8d568b7755046f61231c783c9f5a)

## DK1 fix (wf_14daa5f5-5e2) — 2026-11-26
- Regate green: K2 all exit 0/allowed, K4 only 2 lines, neither real growth (test_front_voice pyright 88 = main's own 88; skylos no result, out of DK1 scope). K5 green both flags (869/457/114).
- Pyright measured like-for-like vs origin/main: main 15176, wave 15142 (report gate-20261126-dalga1/pyright-method.md). DK1 +78 was mostly env artifact.
- dilim0-ui CRLF failure did not reproduce (wave 53/53).
- Approval list (may loosen, equal strictness claimed): DK1.B census exemption renamed to _click_and_stage (same exception, new name); dilim0-ui c14/c15 rewritten via *StartingLevelControl.
- Ruling: BLE001 in routes_ambient cleared by re-raise restructure, not noqa — reviewer approved, noted noqa might be more honest; behaviour same — if wrong, one-line revert.
- Ruling: skylos left out of DK1 verdict — tool times out (grep budget), already so on 2026-11-25 baseline — if wrong, skylos rerun at wave 5 end gate.
- K6: wave PR opened. oynayış bekliyor: no main merge before Kadir plays >=10 min.
- CI red on PR #179 (run 45879604330, shard 4, twice, so not a flake): test_roadmap_b01.test_baseline_pins_verified_sources_and_locks — lockfile digest pin stale after G1.5 (audit fix) and D-607 (package removal) changed the lock on purpose. Evidence: gate-20261126-dalga1/ci-red-45879604330 (logs + zip). Root commits 91935555, d5aa5402.
- DK1.C ac883bd9 (merge 2e3d250b): source-baseline.json lock digest 66c82a6b... -> 4ec37613... (= CRLF digest of the committed lock). Approval list (may loosen): pin refreshed, still exact.
- Ruling: no independent review for DK1.C — one-line data pin, no money/save/undo, CI is the red-green proof — if wrong, one-line revert.
- Ruling (finding): local slot runs pass with both old and new digest, so slots cannot check this test (slot copy of lock or baseline not synced); K5 missed it for that reason. Parked under D-612 (slot sync of web deps), not a new row — if wrong, add a row at wave 2.
- PR #179 CI green at 2e3d250b (run 45882945373). Wave 1 K6 done; K7 oynayış bekliyor.
- Ruling: Wave 2 not started — CLAUDE.md play gate (no play: next slice does not start) outranks the plan's 'continue under 90%'; wave 2 would stack on unplayed wave 1 and pile up play debt — if wrong, cost is idle hours, start wave 2 on Kadir's word. Weekly 69% at 2026-11-26 22:3x.

## Wave 2 — 2026-11-26
- Kadir 2026-11-26: "Dalga 2 te başla" (wave 1 not played yet). Wave 2 branch borc/dalga-2-20261126 stacked on wave 1 head 2e3d250b; its PR waits for wave 1 merge and play O1-O7.
- Ruling: wave 2 in rounds; round 1 = A: G2.1,G2.2,G2.4,G2.5,G2.6,G2.7 / B: G2.3,G2.10,G2.11,G2.24,G2.12,G2.17; check weekly usage before round 2 (stop new tasks at 88%) — wave 1 real cost ~7 points for 8 tasks + gate — if wrong, a round stops early at the cap.
- Ruling: implementers also check gate tools (ruff/radon/vulture) on touched files before DONE, to avoid a DK2 K4 red like DK1 — if wrong, cost is a few minutes per task.
Task G2.1: complete (branch task/borc-g21-20261126, head 5ddf104b, merge 88b3e471)
Task G2.3: complete (branch task/borc-g23-20261126, head a005f166, merge 1f4cff5f)
Task G2.2: complete (branch task/borc-g22-20261126, head 1b9612dd, merge 433545bf)
Task G2.4: complete (branch task/borc-g24-20261126, head 2a66f2ff, merge 011def9d)
Task G2.10: complete (branch task/borc-g210-20261126, head 26112b29, merge 1b74fcf1)
Task G2.11: complete (branch task/borc-g211-20261126, head 3cc5a67d, merge b75b564c)
Task G2.5: complete (branch task/borc-g25-20261126, head 7a444aff, merge ec0372ca)
Task G2.24: complete (branch task/borc-g224-20261126, head 3b49796c, merge 80dc34e0)
Task G2.6: complete (branch task/borc-g26-20261126, head dd573ab7, merge 0d9beb89)
Task G2.7: complete (branch task/borc-g27-20261126, head 92c48f38, merge 6c0f905c)
Task G2.12: complete (branch task/borc-g212-20261126, head d74d06b3, merge e00dc792)
- Task G2.17: complete (branch task/borc-g217-20261126, head 83e19d92, merge 0216cf8d)

## Wave 2 round 1 done (2026-11-27)
All 12 tasks merged (wave head 9bf079b2). Weekly 69% -> 77%.
- Ruling: D-410 and D-226 go back to "kısmen" (G2.1/G2.4 reports say partial; merge marked closed) — reports are the evidence — cost if wrong: a closed row shows partial until rechecked.
- Ruling: REDFIX task first in round 2 lane A: trace test_thread_errand ErrandTable (2) and test_narrative_rebalance fallback test reds to their commit and fix — CLAUDE.md "bilinen kırıklar" — cost if wrong: one Sonnet task.
- Ruling: implementers write reports by bash heredoc when Write refuses (5 round-1 reports missing) — reviewers need the file — cost: none.
- Ruling: G2.16 and DK2 wait for the 2026-11-29 reset; round 2 alone is expected to reach ~86% (stop line 88%) — cost if wrong: a day later.
- Agent rule slips to report: G2.2, G2.7 ran rm -f on their own scratch files; G2.10 left C:/Users/Kadir/Desktop/fix_main_new.py; G2.6 replaced slot 9 web copy (/root/aidnd-env-9/web, old at web.old-g26).
Task G2.18: complete (branch task/borc-g218-20261126, head 42ff0958, merge 38848704)
Task REDFIX: complete (branch task/borc-redfix-20261126, head f5afdd7e, merge 15d15998)
Task G2.19: complete (branch task/borc-g219-20261126, head cccf33e5, merge 1ff0f532)
Task G2.9: complete (branch task/borc-g29-20261126, head 66418001, merge d2b4bfcc)
- Ruling (2026-11-27, Kadir asked): every "kısmen" row is open by the plan's closure rule and gets a task. After each wave gate, a "kısmen sweep" task list is built from the register (one task per file area) and runs before the next wave; rows that cannot close without changing behaviour go to Kadir as one wontfix list — plan goal is all rows closed — cost: extra tasks, roughly 1 point per 3 rows.
Task G2.21: complete (branch task/borc-g221-20261126, head 834321a3, merge cacf1f6d)
Task G2.20: complete (branch task/borc-g220-20261126, head b5def1db, merge 566bdda7)
