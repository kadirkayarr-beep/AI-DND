---
name: Primary campaign UI
description: The user's choice of primary frontend (the only browser artifact left is ai-dnd-experience; the other one, ai-dnd-web, was removed).
---

Use `artifacts/ai-dnd-experience` as the primary UI baseline. Do not replace it
with a new frontend unless a specific compatibility reason is proven (the old
`artifacts/ai-dnd-web` was removed).
Preserve its useful campaign library, creation/reveal/adventure structure,
separated combat components, responsive drawers and dark-fantasy bronze identity.

**Why:** The user explicitly selected this baseline for the campaign player experience
and prohibited a total frontend rewrite.

**How to apply:** Ground campaign UI work in the experience artifact.