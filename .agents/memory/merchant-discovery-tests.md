---
name: Merchant discovery test boundaries
description: Assertions for offline merchant discovery persistence across failure and reopening.
---

Test merchant creation by its shop-to-shopkeeper relationship rather than by the total number of newly materialized NPCs. An initial city search can create unrelated local NPCs alongside the merchant.

**Why:** Counting all NPCs as merchants made a legitimate offline discovery fail the regression; city materialization creates additional bystanders.

**How to apply:** Verify one shop and one NPC linked to that shop; compare complete pre/post state for failed-save rollback. On a resumed campaign, compare persisted engine, journal, history and receipts rather than assuming the entire campaign record is identical: resume can refresh metadata timestamps without altering gameplay.

Negative city-search fixtures must materialize the ordinary city scene before
taking a baseline that requires unchanged NPC identities.

**Why:** A first city visit can select a Python-owned BLUE event and create its
referent NPC. That legitimate, variable scene outcome is not merchant rediscovery.

**How to apply:** Use a real observation turn before merchant discovery; retain
the strict no-new-shop/NPC-identity and persisted replay assertions afterward.

Offline negative-search HTTP regressions should fixture only the model boundary, not replace the engine turn or require that no model call occurs.

**Why:** Deterministic merchant discovery can succeed without a model, while a declined search with the saved merchant still active can legitimately reach intent parsing and narration. A client that rejects every model call tests unavailability instead of the accepted non-search action.

**How to apply:** Supply non-mutating model packets for the negative input, observe the signature-preserved real turn, and assert the non-search outcome, saved narration/history, and unchanged shop/NPC identities.
