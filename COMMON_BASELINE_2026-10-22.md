# Common development baseline, 2026-10-22

This combines local checkpoint `68459ab09027d0e18befdd1ef1cb4a4667185125`
with remote dev `853d0e448402b2a8923a62d1c12799336c99e02a`.
It is a development checkpoint, not a stable release or live-play acceptance.

## Resolution

- Retain the reviewed P2 condition/target independence, named-place and sitting
  corrections, split NPC speech/stage-direction validation and Claude verbatim
  input delimiters. Preserve remote grounded-planner dry-run protection.
- Remove an automatically duplicated older NPC speech block that would overwrite
  the current acceptance decision. Keep existing validators intact.
- Include remote experience UI, undo reconciliation/race handling and its tests.
- Use the remote canonical names for the existing undo contracts; regenerate both
  clients with installed Orval 8.30.0 from OpenAPI. No generated hand patches.
- Retain all unit tests plus the separate browser UI gate. Make that existing
  browser gate portable to Windows by launching installed Vite through Node and
  applying POSIX executable-mode checks only on POSIX. Keep file/access checks
  and all browser assertions.
- Adapt two old last-physical-line prompt assertions to check exact player text
  in one delimiter block and follow-up context outside its closing boundary.
- Preserve local ownership behavior and launcher. Do not adopt remote automatic
  process stopping, different default campaign DB, env loading or default speech
  debug logging. The newly introduced remote `.env.example` is excluded.

## Validation

- Contract parity: 46/46, matching 42 documented/runtime routes.
- Claude 11/11, P2 conditions 7/7, places/sitting 17/17, prompt branches 2/2.
- Expanded NPC/undo/isolation classes: 72/74; the two failures below are preserved.
- TypeScript libraries and UI: pass. UI build: pass, with a non-fatal existing
  tooltip source-map warning.
- UI unit tests: 150 pass, one existing real-HTTP fixture skip.
- Isolated mocked browser fixture: pass at 360x800, 390x844, 360x640 and 1440x900.
- Synthetic providers and scratch databases only. No real model, live API,
  personal save or existing browser session was used. No dependency installation.

## Known failures and exclusions

`TwoPlayerIsolationTests` still fails:

- `test_a_saved_but_inactive_campaign_is_409_for_its_owner_and_404_for_everyone_else`
- `test_a_signed_in_stranger_gets_the_same_answer_as_for_a_missing_record`

The preserved local inactive-save behavior returns 409 where remote tests expect
404. The second test also demonstrates distinguishable responses for an active
foreign campaign and a missing campaign. Both failures reproduce on the unchanged
pre-merge local source. No assertion was weakened and no ownership change was made.
This baseline is not a full security-gate pass.

Reported live gameplay defects remain open. The observed game UI was running from
another checkout and older processes; disk source synchronization does not update
those processes. Runtime switching and save/session preservation remain separate.

PRs #13/#21/#22/#23 overlap the reviewed package sources; they were inspected by
exact head rather than merged again blindly. Their histories are not claimed
merged solely because functions/tests overlap. PRs #1/#2/#24 and other experiments
remain outside this integration. Local agent hooks/configuration, personal
records, credentials and unreviewed local evidence are not added.

The inherited SECURITY_POSTURE.md is a historical report of the earlier helper;
its flattened-input wording is stale and is not a fresh security certification.
