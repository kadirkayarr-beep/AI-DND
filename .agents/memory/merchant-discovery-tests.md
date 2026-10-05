---
name: Merchant discovery test boundaries
description: Assertions for offline merchant discovery persistence across failure and reopening.
---

Test merchant creation by its shop-to-shopkeeper relationship rather than by the total number of newly materialized NPCs. An initial city search can create unrelated local NPCs alongside the merchant.

**Why:** Counting all NPCs as merchants made a legitimate offline discovery fail the regression; city materialization creates additional bystanders.

**How to apply:** Verify one shop and one NPC linked to that shop; compare complete pre/post state for failed-save rollback. On a resumed campaign, compare persisted engine, journal, history and receipts rather than assuming the entire campaign record is identical: resume can refresh metadata timestamps without altering gameplay.
