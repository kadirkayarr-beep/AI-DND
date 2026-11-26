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
