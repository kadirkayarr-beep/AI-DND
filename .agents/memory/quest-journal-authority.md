---
name: Quest ledger authority
description: Why the campaign quest ledger stays empty until the Python engine has structured quest lifecycle data.
---

Do not infer quest creation, completion, or objective progress from Qwen narration or browser input. Keep the ledger empty until Python exposes structured, canonical quest outcomes.

**Why:** Narration can be descriptive or contradictory, and the existing canonical engine state does not provide a reliable quest lifecycle source. The user explicitly chose a validated, persisted empty ledger for Quest V1 rather than narrative inference.

**How to apply:** Only add automatic quest updates when the Python engine owns explicit accepted quest and objective state transitions. Keep browser data read-only, then validate, persist, and serialize those structured outcomes through the API.