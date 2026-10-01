---
name: Raw narration evidence boundary
description: Privacy and release-gate rules for persistent raw player input and narration in V1.1 smoke reports.
---

For V1.1 smoke reporting, persist complete player input and final narration only in the dedicated `narration-review.json` artifact. Keep recursively sanitized turn, summary, and API audit evidence free of transient prose. Require finalization to validate and hash the dedicated artifact; do not synthesize or retrofit it for historical reports.

**Why:** Manual narration review needs the actual text, but placing it in the existing sanitized files would weaken their privacy contract. Hashing the separate artifact makes approval refer to the same review material.

**How to apply:** When changing V1.1 smoke evidence or release review, preserve this separation and fail closed if the raw review artifact is absent or incomplete. Keep V1 finalization behavior unchanged.