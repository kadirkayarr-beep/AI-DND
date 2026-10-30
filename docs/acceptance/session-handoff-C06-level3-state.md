# C06 Sorcerer level3 progression/state — 2026-10-28

ACCEPTED bounded core-state leaf after pre-implementation leaf review, genuine TDD and independent static implementation review. Production MAX_SUPPORTED_LEVEL is now3; levels4+ remain blocked. This is NOT full Sorcerer3 playability or C06/C19 completion.

Actual unpatched preview/apply/create/save/load supports all four sourced subclass IDs, six total ordinary prepared spells, slots1=4/2=2, prior choices, spent-slot deltas and sourcePB2. Level3 rests restore both buckets. Partial-XP jumps pay only unpaid HP; replay does not pay twice. Invalid late creation choices restore the populated session's trusted snapshot and top-level container identity. Successful recreation clears prior progression/metamagic/subclass/HitDice state.

Detect Magic was added only as verified Sorcerer level1 selection metadata (PDF138/142) so six PHB choices do not force legacy Chaos Bolt. Chaos Bolt compatibility remains. No DetectMagic resolver is claimed.

Innate Sorcery, Font of Magic, Metamagic effects, selected subclass features/always-prepared grants and optional replacement choices remain explicit pending obligations. A stored subclass ID is not an implemented subclass. Level2 MagicMissile casting is the next selected dependency; current base-slot casting at reallevel3 passed.

Evidence: c06-level3-red-confirmed12methods/19assertionfailures, zeroerrors;137relatedGREEN; after adding isolatedsubclass-injection andHitDice-recreation proofs, c06-level3-wide910executionsPASS/exit0. Exactunique ledger is in evidence/c06-level3-state-20261028. Three old unsupportedlevel3 assertions were deliberately advanced tolevel4; unearned/missing-choice level3 saves stillreject. No numericoracle weakened. Staticreview, not independent rerun.

The unchanged save format does not grant downgrade compatibility: the oldMAX2 reader rejects appliedlevel3 saves. Revert only with prechange snapshots. No personal records migrated; no push/merge/deploy. Earlier16:43ZIP predates this leaf.
