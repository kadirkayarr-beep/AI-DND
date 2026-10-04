---
name: Development evidence cleanliness
description: Owner-required separation of tool outputs from genuine checkout changes.
---

Sequential Health Check → Final Gate must not fail solely because the first tool
generated its own evidence. Genuine pre-existing user changes and source changes
during execution must still block; historical records must remain protected.

**Why:** The owner explicitly requested this after a clean checkout passed Health
Check but failed Final Gate solely on the Health Check's two new evidence files.

**How to apply:** Keep raw Git state visible. Do not blanket-ignore evidence folders
or treat fingerprint exclusions as permission to overlook user edits. Ownership
bookkeeping does not certify test results, historical claims, or server identity.