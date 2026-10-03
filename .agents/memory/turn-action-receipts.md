---
name: Turn action receipt semantics
description: Preserve exactly-once replay when campaign turns are retried.
---

Campaign turn IDs are scoped to a campaign. Reusing an ID with the same request must replay the saved response; reusing it with a different request must conflict. Persist the engine state, campaign history, and response receipt within the same transaction.

**Why:** A response can be lost after the engine has changed state. Atomic persistence lets a retry return the original result without repeating game effects.

**How to apply:** When changing campaign saves or schema migrations, keep action receipts in the same commit boundary as the turn and keep unrelated save invariants, such as history trimming, independent of whether a receipt is present. Test same-session replay, replay after resume, and payload mismatch.