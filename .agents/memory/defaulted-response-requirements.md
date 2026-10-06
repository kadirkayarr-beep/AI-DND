---
name: Defaulted response requirements
description: Interpret required health response fields without weakening the published contract or changing runtime behavior.
---

Compare required health response fields against the fully serialized runtime model, not its construction-time required list.

**Why:** Pydantic defaults allow callers to omit health fields when constructing the model, but the health response always emits those fields. The owner requested response contract regression coverage without server behavior changes; using construction requirements would instead weaken the existing response guarantee.

**How to apply:** Use the serialization schema for field types and serialized model keys for response presence guarantees. Reconsider this rule if the endpoint begins excluding defaulted or unset fields.
