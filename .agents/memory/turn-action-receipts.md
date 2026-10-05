---
name: Turn action receipt semantics
description: Preserve exactly-once replay when campaign turns are retried.
---

Campaign turn IDs are scoped to a campaign. Reusing an ID with the same request must replay the saved response; reusing it with a different request must conflict. Persist the engine state, campaign history, and response receipt within the same transaction.

**Why:** A response can be lost after the engine has changed state. Atomic persistence lets a retry return the original result without repeating game effects.

**How to apply:** When changing campaign saves or schema migrations, keep action receipts in the same commit boundary as the turn and keep unrelated save invariants, such as history trimming, independent of whether a receipt is present. Test same-session replay, replay after resume, and payload mismatch.

Persistence revisions are coordination tokens, not gameplay checkpoint state.
Receipt replay must precede stale-context checks; new stale writes must reject
rather than overwrite newer accepted campaign truth.

**Why:** Independent managers can hold old copies, while Normal death deliberately
rewinds gameplay without reclaiming old persistence ownership or rewinding RNG.

**How to apply:** Bind revision ownership on actual campaign load/create and
advance it only after commit. Keep Normal checkpoint semantics separate from
failed-persistence restoration.

Retained structured legacy action provenance must be reserved before bounded
journal trimming, without inventing a historical response or request.

**Why:** Otherwise trimming an old event identity can make its action ID reusable.

**How to apply:** Reuse the existing campaign receipt owner; preserve original
receipts, reject ambiguous identities safely, and retain the event owner's
ALREADY_APPLIED projection instead of inventing another gameplay resolution.

Do not equate combat turn advancement with RNG consumption in replay regressions.

**Why:** A completed turn can advance the scheduler and reset resources while an
enemy's range gate rejects its attack before any dice are rolled. Requiring that
later turn to consume RNG makes the replay check depend on unrelated geometry.

**How to apply:** Prove that the later turn changes canonical combat state, then
compare the complete RNG state immediately before and after each replay.

For replay assertions after campaign resume, compare persisted campaign metadata
against a snapshot taken after resume, not before it.

**Why:** Resume may legitimately update the last-played timestamp; comparing
against the pre-resume record makes an otherwise correct replay test fail at a
timestamp boundary.

**How to apply:** Assert the saved engine state, history, and receipt survive
resume separately, then capture the store immediately before replay and verify
replay itself does not write.

Distinguish retry after failed persistence from replay of a committed receipt.
The former must reproduce gameplay and restore RNG, but need not reuse generated
identities for history entries that never committed.

**Why:** Requiring full response equality with an uncommitted attempt incorrectly
treats newly generated history identities as a gameplay rollback failure.

**How to apply:** Compare mechanical outcomes and narration across failed-save
retry; require exact accepted-response equality only once a receipt has committed
(apart from the current session ID after reopening).

Validate saved responses against the receiving command's contract before
rewriting the session identity. Do not impose a single response schema on the
shared receipt store.

**Why:** Turn, species, and ambient-event receipts share storage, and legacy
ambient receipts intentionally reserve identities without a complete HTTP
response. Replacing a session ID first can conceal a missing required field.

**How to apply:** Reject incomplete replay contracts explicitly at the command
boundary, without mechanics or persistence, while preserving legacy identity
reservation and valid response replay.