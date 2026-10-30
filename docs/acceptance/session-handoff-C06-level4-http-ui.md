# C06 selected earned Sorcerer 3→4 HTTP/UI — ACCEPTED

Acceptance is limited to the existing-character, earned-XP, CON+2 flow. Public preview/apply requires raw level 4, applied level 3 and XP ≥2700 plus valid prior choices. Direct core/save compatibility remains unchanged. Creation remains levels 1–3. No full C06/C19, general ASI/feat, creation4, Clerk, model, deployment or personal-campaign acceptance.

## Delivered and reviewed
Existing session ownership, campaign revision, durable pending intent/receipt, rollback, canonical persisted recovery and generated contracts are reused. UI selects one fifth cantrip, one seventh prepared spell and CON+2; no client arithmetic or free-level button. Independent backend and frontend code reviews approved. One genuine server-only applied/null recovery state-gate defect was corrected and regression-tested; pending is not cleared before canonical state is accepted.

## Evidence and limits
Evidence is bound under `evidence/c06-level4-http-ui-20261029/`, with file digests and final source hashes.
- Backend related run `c06-four-http-related2-20261029-0921`: **104 PASS**. Exact command/modules, guard and raw logs copied. Initial HTTP assertion RED retained. Prior combined run failed/timed out on historical global `api.main.app=None` parity setup; raw failure retained, not described as clean. Narrow actual-factory schema parity passes.
- Accepted core run: **323 PASS**, separate overlapping scope; see `session-handoff-C06-level4-con.md` and its evidence. Do not sum counts.
- UI: **160 PASS, 1 pre-existing skip**, including **22 focused PASS**; declarations/typecheck PASS. Raw logs and implementation note copied. Initial controller coverage was partly post-implementation, not all claimed TDD.
- Headless scripted browser harness was **BLOCKED by EPERM**. Do not claim the whole browser matrix passed Chrome. The scripted-only fixture had an erroneous 30/26 HP state; corrected test-only. Earlier managed failure observations remain part of the record, not evidence against the correct real backend.

## Actual managed Chrome + real HTTP proof
Parent operated the final built UI against the finite loopback synthetic-principal fixture (not Clerk). Real creation3 then real XP award1800 produced raw4/applied3/XP2700. Selected Shocking Grasp, Mage Armor and CON+2. Apply and save returned200; GUI showed **26/30 HP**, CON16, XP2700, applied4, slots4/3, five cantrips/seven prepared spells. ASI did not heal.

Backend restart changed generation `d60b37e2-adb5-4d46-be20-86e937761abd` (pid67) to `9e76b12e-1ef3-4c7b-bb52-b6c5bf2034d6` (pid71). Same campaign `163d7f4d-7177-4249-88c3-490ae73a0166` resumed200 with the same visible state. Parent observed subsequent preview `target_not_above_applied_level`; request trace records200, not response body. Read-only SQLite captures prove revision3, exact unchanged payload SHA256 `b041f6f34bfb69006164d8f0406866c90cc37db444fabde6e3a32cf7395de9e3`, unchanged selected state and receipt, exactly one level-up POST and one durable receipt across generations. No replay was performed for evidence capture.

Runtime ZIP: external `cloud-level4-runtime-20261029-0925.zip`, SHA256 `9127c2f18146fd730f769a6523c075329715bfaa9ef7d860a865cc7827319c73`; final UI build and identity manifest copied. Dedicated synthetic DB/HOME, no model or personal data. Parent reports owned stop requested and terminal prompt returned09:33 UTC; tabs closed. No source changes during browser proof. Source remains frozen for private backup; no push/merge/deploy performed.
