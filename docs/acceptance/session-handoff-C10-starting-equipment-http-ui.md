# C10 — new Barbarian starting equipment: scoped acceptance

Frozen handoff: 2026-10-29 15:28 UTC. **PASS for the selected new-creation source package/cash correction and its bounded UI/persistence proof.** Not full Barbarian/C10/C06, pack-content, background-wealth, or general quantity acceptance. Parent performed native GUI actions and reported final independent source/evidence review GO; the author inspected structured captures and final raw test evidence. Static independent review is not claimed as an independent test rerun.

External artifact names below are relative to sibling `ai-dnd-recovered-work-20261029/`.

## Source and implementation boundary

`C10-starting-equipment-implementation-plan-20261029.md` and proposal bind Barbarian Core Traits, PDF50/printed51, source SHA `7c9beb785364945923f78a9b0fd9830786c3b33d4838ea545847b3ad1d9c41f2`:
- Class A: Greataxe, four Handaxes, opaque Explorer's Pack, 15GP.
- Class B: 75GP and no class items; hands explicitly empty, no phantom default sword.

Product owners are `api/dnd_2024_rules.py` and `api/character_creation.py`, plus narrow frontend disclosure. Class aggregate expansion follows existing display deduplication, so a legitimate additional background Handaxe survives. Exact known class cash and certified background cash occurrences are removed separately; fresh canonical player currency receives their verified sum, not a prior wallet balance. Background A without numeric certification retains its inventory cash label unconverted; unknown is not zero and that wallet is explicitly partial. No general coin parser, stack engine, pack expansion, receipt authority, migration, load adoption or remint hook. Existing materializer, save/load and weapon consumers are unchanged.

UI uses the existing corrected catalogue and request shape. Shared `StartingEquipmentNotice` appears in custom selection/summary and actual random result. Verified class cash statements require the exact source catalogue signature; random copy does not infer selected package or total. Missing catalogue does not invent cash or block creation. No API schema/client/codegen changes.

Freeze bindings: `C10-starting-equipment-core-manifest-20261029.json` (four files), `C10-starting-equipment-http-manifest-20261029.json` (new test and genuine old fixture), `C10-starting-equipment-ui-sha256-20261029.txt` (five files), combined `C10-starting-equipment-native-source-freeze-20261029.json` (294 source paths). Combined hashes were verified before and after packaging and again after this documentation-only write.

## Evidence and retained failures

Final guarded 52-module `c10-starting-equipment-final-combined-20261029-1510`: **1082 PASS, 0 failures/errors/skips, 187.879 s**. Inspected `child-1.raw.log` SHA256 **`21f26e307e6e57f1d2b716bd908aedfe145a8da72877a1785f71c48b63c90eba`**, `run-evidence.json` and B06 guard proof. Guard SHA remains `d0803047bca67beec76a27d7825cef6f655bafee81d290d5c940d530ec0a51c5`. No sockets/model/install in guarded tests.

Preserved core evidence:
- `c10-starting-equipment-red-20261029-1506`: five assertions plus a missing-wallet KeyError; strengthened oracle then `red2` gives six genuine assertion failures/no errors before product patch.
- `c10-starting-equipment-green1-20261029-1508`: 18 PASS/1 FAIL because the old B oracle expected a phantom default sword. This was an intentional source correction, **not** a preexisting baseline failure. Exact B expectation corrected to empty hands; other-class control remains unchanged.
- `c10-starting-equipment-green2-20261029-1509`: 61 PASS, 0.368 s. Covers actual creation1/2 A/B, lazy materialization to four unique IDs, repeated materialization/restore, exact-ID drop, no regrant on historical load/advance, late creation rollback and synthetic coin-collision/extra-background-weapon boundaries. Synthetic patched backgrounds are not asserted PHB grants.

HTTP `c10-starting-equipment-http-red-01`: two genuine failures (A+backgroundB5000 instead of6500 and wrong catalogue). Initial green8 PASS retained; strengthened final `c10-starting-equipment-http-green-02`: nine PASS, 1.429 s (eight new plus genuine checkpoint12 replay). Actual A/B1/2 cash6500/12500 with backgroundB; certified Artisan4700/10700; uncertified Criminal label retained with class-only1500/7500; deterministic random source creation; exact-ID SQLite precommit fault/rollback/retry/fresh replay; creation INSERT failure publishes no campaign/session; stale labels and unauthorized money/quantity rejected. Newly authored legacy inventory characterization is **not** a historical receipt. Creation is not claimed exactly-once.

Frontend evidence in `C10-starting-equipment-ui-implementation-20261029.md`: genuine five-test RED; focused six PASS (sixth request-path regression added after implementation, not falsely RED); typecheck exit0; standard172 PASS/1 existing SKIP and separate C06 chain135 PASS. Counts overlap and are not summed. New static build succeeded with existing Vite/toolchain; no install.

## Immutable fixture and lifecycle correction

Launchable runtime **02**, `cloud-starting-equipment-runtime-20261029-02` and ZIP SHA256 **`07f96aa24da0a70b53538de9bfda9d793a0cde9d5e1394879b5bd60fc110c292`**,233files/8assets. Identity, `launch-cloud-starting-equipment-fixture-20261029-02.sh`, `cloud-starting-equipment-fixture-handoff-20261029-02.md`, `prepare_starting_equipment_fixture.py`, `preflight_starting_equipment.py`, `capture_starting_equipment.py` bind this run. Factory remains creation/save/resume-only, with minimal selected package/background trace fields. No seeded campaign, posthoc grant, combat, model adapter or worker socket launch.

Retain `cloud-starting-equipment-build-attempts-20261029.md`: first build lacked required BASE_PATH; corrected command PORT=29991 BASE_PATH=/ succeeded in build02 log. Packaging runtime01 omitted Python -B and created an unmanifested pycache on verification import; verifier refused correctly. Runtime01 remains unlaunchable historical evidence; runtime02 cleanly verified under -B.

Preflight02 exposed a **fixture oracle error**, not a product failure: actual creation/save stores six source strings and semantic hand, not eagerly materialized item dictionaries. Existing `/item list` owns lazy IDs and currently requires adapter readiness at API entry; it is not a modelNone native route. Parent explicitly approved the narrower honest native scope. No fake adapter, readiness bypass, new UI/route or product change was added. Preserve `preflight_starting_equipment-eager-id-oracle.py`, corresponding capture draft and failed preflight02 log/JSON. Corrected guarded preflight03/04 PASS prove actual catalogue/create/save/fresh-factory resume, exact displayed request items,6500CP, source order, proof/proficiency/Rage state, whole payload persistence and refusal of unlisted level-up route. Preflight04 also dry-validates the capture assertions against its real synthetic snapshot; no dry-run output is relabeled native.

## Parent native GUI, completed 15:25 UTC

Actual wizard campaign `ef70ed07-f9de-4345-a5e0-2eb40aee0570`: Human Barbarian2, Criminal, classA/backgroundB, Lucky, standard STR15/DEX14/CON13/INT10/WIS12/CHA8 then backgroundDEX2/CON1; Athletics/Perception and HumanPersuasion, languages Dwarvish/Giant. Parent observed corrected A four-Handaxes and B75GP choices, selected A15GP plus known backgroundB50GP disclosure. **B option visibility is native; actual B application remains HTTP-only.** No uncertified CriminalA wealth claim.

Character inventory visibly shows Greataxe, four Handaxe entries and Explorer's Pack. Captured canonical wallet is6500CP, **store proof, not a claim that a GUI balance was displayed**. Persisted ordered inventory is exactly six strings; semantic equipment is `{main_hand: 'greataxe', off_hand: null}`. Simple/Martial training, inactive Rage2 and known-unarmored proof remain present. Native does **not** prove canonical owned item IDs; actual backend HTTP/materializer tests do.

UI Save → controlled backend restart → home-picker resume of the same campaign. `cloud-starting-equipment-saved-20261029-02.json` and `cloud-starting-equipment-resumed-20261029-02.json` both PASS; full source-item order/currency/hands/proof and complete payload exact:

| Evidence | Saved = resumed SHA256 |
|---|---|
| Full payload | `2c95af95a3b1107a48bf6c3fb5c3f26a5804dfb0591f7215b7dbe458ac38d84c` |
| RNG | `890337323cb52af585523b946115288c1a7f449d08b0eb707f74c739e383f749` |
| All receipt tables (empty) | `5145290922cc861eb2a524b6394ca0b6090c65802b5bdd6b40cae97772c08350` |

Generation `a826e49e-7e2a-49a7-abf8-993210d027ea` PID205 → `90b9e28b-6d68-43e0-9129-63a0dd865a0c` PID211. Real process replacement, not page reload. Parent verified owned stop/native prompt, tab19 closed; `cloud-native-starting-equipment-02/ready.json` absence independently checked. No native item command or combat was issued.

## Open scope and checkpoint

Opaque Explorer's Pack contents, uncertified background A cash/packages, other-class corrections, general quantities, armor/Unarmored Defense, Weapon Mastery and full class/C10/C06 remain open. This closes the selected **new Barbarian class package** discrepancy, not historical saves or every background. Prior Rage/proficiency proofs stay historically unchanged. C19 stale preview disclosure remains separately open.

Retain source manifests/deltas, core/API RED and GREEN evidence, final raw/guard proof, UI logs, both packaging attempts and lifecycle oracle failures, successful runtime02 ZIP/identity, build/preflight/helper/launcher and the two structured native captures. Backup excludes screenshot binaries/live SQLite databases. No push/merge/deploy/install/personal/auth/security change; no model/Clerk/full-route acceptance claim.
