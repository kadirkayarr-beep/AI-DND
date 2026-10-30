# C06 Barbarian level 1→2 state — 2026-10-29

## Narrow acceptance
Independent static review approved the existing-character Barbarian1→2 preview/apply/save-load state leaf. No full C10 effects, Barbarian higher-start creation, UI/API expansion or full C06 acceptance.

Source-bound two-level table adds no caster columns. Per-class ceiling allows raw XP level3/applied2 while rejecting applied3. Noncaster apply requires exactly empty choices, preserves absence of spellcasting world state, preserves supported legacy zero-slot mirrors, and rejects foreign subclass/malformed Metamagic. Even an injected spellcasting_v1 key with None is rejected. Sorcerer higher-start creation remains the only supported high-start path.

HP is added once through existing owner; XP-first apply adds no second HP. Hit Dice derive from applied level and preserve spent count. Existing XP initialization fix remains unchanged. No new effect, rest or receipt owner.

## Evidence
Initial actual RED9 methods/8 assertion failures/0 errors. Strengthened legacy None-key rejection exposed another assertion failure, then fixed before final run. Final unchanged-guard related regression164 executions PASS, 0 failures/errors/skips; actual raw evidence retained under docs/acceptance/evidence/c06-barbarian-level2-20261029. Independent reviewer read code, source and terminal proof but did not rerun.

Minor nonblocking test gaps: final world-state injection negatives prove rejection without separately checking target snapshot equality in those two cases; other malformed-player cases check snapshot. Current-HP and successful RNG preservation rely partly on limited code mutation plus existing regression, not a new dedicated assertion. Do not inflate coverage.

## Identity and runtime distinction
Actual historical HEAD96e0 + dirty restored snapshot, not originala963 ancestry. No commit/push/merge/deployment. Frozen live cloud UI fixture is the earlier Sorcerer3+starting-XP build; Barbarian state changes are NOT in it, and its browser/human acceptance remains separate.
