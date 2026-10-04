---
name: Primary campaign UI
description: The user's choice of primary frontend when the workspace contains two AI-DND browser artifacts.
---

Use `artifacts/ai-dnd-experience` as the primary UI baseline. Do not replace it
with `artifacts/ai-dnd-web` unless a specific compatibility reason is proven.
Preserve its useful campaign library, creation/reveal/adventure structure,
separated combat components, responsive drawers and dark-fantasy bronze identity.

**Why:** The user explicitly selected this baseline for the campaign player experience
and prohibited a total frontend rewrite.

**How to apply:** Ground campaign UI work in the experience artifact. Do not choose
the other browser merely because it is mounted at the root preview path.