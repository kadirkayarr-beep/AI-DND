# C10 — canonical Barbarian weapon proficiency: scoped acceptance

Frozen handoff: 2026-10-29 15:01 UTC. **PASS for the selected new-creation → save/load → actual weapon-use correction**, not full Barbarian/C10/C06 acceptance. Parent performed the native browser actions and reported final source/evidence review GO; this handoff binds inspected structured captures and raw test evidence. Independent review was static/source/evidence review, not an independent rerun.

## Product and source boundary

Only product changes relative to the final Rage02 source are `ai-dnd/api/character_creation.py` and `ai-dnd/game.py`: canonical new Barbarian creation explicitly maps source Simple/Martial training to `['simple', 'martial']`; optional weapon proficiency state is validated and preserved in save formats 4–6. Present fields in formats 1–3 refuse rather than silently dropping/promoting them. Historical absence remains absent and clears stale reused-session state. No inventory inference, client-supplied grant, automatic legacy adoption, other-class grant, mastery, weapon-consumer change, or new UI/API route.

Source: Barbarian Core Traits, PDF 50 / printed 51, as bound in `C10-core-traits-next-proposal-20261029.md`. External evidence paths below are relative to sibling `ai-dnd-recovered-work-20261029/`.

- `C10-proficiency-core-manifest-20261029.json`: three files; creation SHA `7d0220d573a8948b27116d853b29f4ee97bac5f56c32b7d8014632602e8d5ebb`, game SHA `29accd1d896be803b7eebfcb675cccaa42503b5207b512902c2e1d413977ac98`.
- `C10-weapon-proficiency-http-manifest-20261029.json`: new HTTP test plus genuine unchanged checkpoint12 receipt fixture.
- `C10-proficiency-native-source-freeze-20261029.json`: 287 bound source files; checked before/after packaging and at handoff.
- `cloud-proficiency-product-delta-20261029.diff` and `cloud-proficiency-runtime-delta-20261029.json`: only those two product files plus external factory assertion differ from Rage02; static assets are byte-identical. The factory asserts source-produced training; it does not assign it.

## Tests, failures, and review

Final guarded 48-module aggregate `c10-proficiency-final-combined-20261029-1450`: **1023 PASS, 0 failures/errors/skips, 185.832 s**. Inspected `child-1.raw.log` SHA256 `c63512aacd49056f9509cca6fe61da7aaf06fe2f4700c58e8f117ff80f2e8123`, `run-evidence.json`, and B06 guard proof. Exact command is retained in `run_c10_proficiency_final_20261029.sh`. Guard SHA remains `d0803047bca67beec76a27d7825cef6f655bafee81d290d5c940d530ec0a51c5`; target uses isolated environment and denies sockets/subprocess/forbidden probe reads. No intentional fixture expectation change was needed in this aggregate.

Retain rather than erase:
- `c10-proficiency-core-red-20261029-1448`: six genuine assertion failures, no errors.
- `c10-proficiency-core-green1-20261029-1449`: five PASS and one test oracle error expecting bare ValueError instead of the existing CampaignCorruptError wrapper. Corrected to the exact wrapper, not weakened refusal.
- `c10-proficiency-core-green2-20261029-1449`: ten PASS, 0.194 s.
- `c10-weapon-proficiency-http-red-01`: two actual HTTP failures showing missing canonical training and restored attack bonus 2 rather than 4.
- `c10-weapon-proficiency-http-green-01`: seven PASS, 1.570 s (five new HTTP tests plus genuine checkpoint12 stored receipt and prior absent/null Reckless wire hash). Covers fresh restore/use, PB exclusion from damage, composition, rejected client grant, legacy absence, SQLite precommit rollback/retry/reopen/exact replay.

Counts overlap and are not summed. No prechange Barbarian-specific stored receipt was captured; current absent-Barbarian characterization is not a historical receipt. Prior Rage01 proficiency=false evidence remains historically unchanged. No frontend changes or fresh frontend test/build claim: this fixture reuses the verified identical final Rage02 bundle and previously recorded frontend evidence.

## Immutable fixture and guarded preflight

Runtime `cloud-proficiency-runtime-20261029-01` and its ZIP, SHA256 **`f359d4988f3850aa0ba140a5ef325af5f07a1feb416330520c3143ceac398916`**; identity `cloud-proficiency-runtime-20261029-01.identity.json`. Launcher `launch-cloud-proficiency-fixture-20261029-01.sh`, run root `cloud-native-proficiency-01`, capture helper `capture_proficiency.py`, instructions `cloud-proficiency-fixture-handoff-20261029-01.md`. No worker socket launch or installs.

`preflight_proficiency.py` and `cloud-proficiency-preflight-20261029-01.{log,json}` prove actual factory/ASGI creation, initial save/fresh resume before attack, proficiency-derived attack bonus 4, natural outcome and final exact save/resume under the no-socket guard. Existing toolchain, env-i PATH=/usr/bin:/bin and synthetic HOME/TMP only. Canonical Barbarian2 Human/Criminal creation supplies STR15/PB2, source Greataxe, Rage pool2 and known-unarmored proof. Source Commoner has HP4/AC10. Bounded encounter ENTER/START and lawful own-turn progression establish reach; no HP/RNG/armor/resource/proficiency overrides.

## Parent native proof, completed 15:00 UTC

Campaign `47bf52fb-8f0d-45eb-b84e-d7697c6c95b8`. All four helper phases passed: `cloud-proficiency-{initial,loaded,saved,resumed}-20261029-01.json`.

1. UI Save **before activation/attack**, controlled restart and home-picker resume. Initial and loaded full payload are identical; training is already `simple/martial` after load, Rage2 inactive, no turn receipts.
2. Explicit Rage confirmation/activation, then explicit Reckless Greataxe attack. Recorded d20s `[3,10]`, selected10 + STR2 + PB2 =14 vs AC10; `proficient:true`, `proficiency_applied:true`, attack bonus4. Actual damage16 = d12 roll12 + STR2 + Rage2: **PB is not damage**. Source Commoner HP4→0 naturally, no forced roll. Rage remains active12 seconds with one use; typed submitted steps and receipt result are retained.
3. UI Save, second controlled restart and same-campaign resume. Final payload/RNG/all receipt hashes exact. Helper also retains training, owned inventory/equipment/currency and creation/proof state unchanged across the attack sequence.

| Pair | Full payload SHA256 | RNG SHA256 | All receipts SHA256 |
|---|---|---|---|
| initial = loaded | `335b9d8d3b567c27ae4e88410efa69cf0b08691a35aa8640c2ede3e51d520240` | `5cef403959826e2b10cfa968fad95ebb8dad530ad6c93f8030efe594f7d71e9e` | `5145290922cc861eb2a524b6394ca0b6090c65802b5bdd6b40cae97772c08350` |
| saved = resumed | `cc1a872c9d070603ee4614215668efdcb1487e3a20323b486a9e8e1a427e1b13` | `a11179e1c3cb19c36bef20dcfef380550f69d970b9a27d44c8f030b26243831e` | `b5b0b4b8b5d4bd89ebf0e46f4381f91bc0a22ae7f32bde0901c333ccef3ddaa6` |

Process generations: `07f6d645-d5ae-4072-91f7-5be2716c2477` PID191 → `df78c2e3-834e-40ee-9a4e-7449794b897d` PID196 → `40e8c57f-cead-4a47-8927-d9ab63a46fd3` PID200. Parent verified owned stop/native prompt and closed tab18; ready file absence checked at handoff. Restart is real process replacement, not just page reload. No model/auth/Clerk/live deployment claim.

## Remaining limits and handoff

This native proof is one canonical new Barbarian2 Greataxe flow, not all weapons/classes/routes. Legacy absence is deliberately not auto-granted. Gear/currency/package discrepancy remains open: source package A calls for four Handaxes, while current package supplies four Javelins; package B currency/gear mismatch is also not repaired here. Weapon Mastery, general armor/Unarmored Defense, broader class progression, full C10/C06 and other class coverage remain open. C19 stale preview disclosure remains separately tracked in `C19-disclosure-nonblocking-issue-20261029.md`; no frozen product fix is hidden in this change.

Preserve manifests, run logs/guard proofs, source deltas, runtime ZIP/identity, launcher/preflight/helper, and four structured native captures for checkpoint backup. Exclude screenshot binaries and live SQLite databases. No product edits, commit/push/merge/deploy or access/security changes were made while preparing this handoff.
