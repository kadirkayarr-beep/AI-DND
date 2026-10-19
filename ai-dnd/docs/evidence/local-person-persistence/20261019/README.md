# Local-person persistence verification — 2026-10-19

Implementation is committed on `feature/ai-freedom-first-slice-20261019` at `65803c7`.

## Behavior covered

- A model-proposed local person becomes campaign-owned content only when Python classifies the player's request as a person-search intent and canonical NPC validation accepts it.
- Repeated requests reuse the same campaign/location-scoped request identity, including after save/resume.
- A descriptive follow-up resolves to the persisted person; a second campaign does not inherit that person's data.
- Past-promise/reward claims do not create an NPC, event, or character reward; a same-name/different-role canon collision rejects the proposal.
- Model-generated history, knowledge, rewards, and mechanics are not stored in the new NPC.

## Verification

- `api.tests.test_local_person_persistence` plus the focused pipeline case: 4 tests passed.
- The local-person HTTP acceptance test against base `13c8b5c`: failed at the expected assertion (`0 != 1` accepted NPCs). Against `65803c7`: all 4 focused tests passed.
- `api.tests.test_identity_suggestion`: 16 passed on both base and current code.
- Final gate at `65803c7`: 305 Python regression tests split into 246 + 59. The 59-test group passed; the 246-test group had 242 passes and 4 failures. All four failures were reproduced against base `13c8b5c`; details are in `local-person-baseline-comparison.log` and the retained suite records.
- Frontend libraries, typecheck, tests, mocked-auth browser UI, and production build all passed after offline installation of the existing frozen lockfile dependencies. No packages were added or lockfiles changed.
- Live HTTP and live Qwen were not run. No live-model success is claimed. The preview screenshot showed the sign-in screen; the signed-in UI was not verified.

The final gate is `NO-GO` because of the four pre-existing regression failures above, not because of the local-person acceptance tests or frontend checks. No push, merge, or deploy was performed.
