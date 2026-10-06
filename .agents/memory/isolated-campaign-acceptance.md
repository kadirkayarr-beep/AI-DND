---
name: Isolated campaign acceptance
description: Safe live HTTP and browser verification for campaign gameplay.
---

Live HTTP and browser tests that create or advance campaigns must use a dedicated
temporary campaign store. Build fixtures through normal API routes and canonical
engine actions; use deterministic session seeding only to make valid gameplay
repeatable, not to replace or bypass engine outcomes. Route the test browser's API
traffic to the isolated server rather than the primary preview backend.

**Why:** The primary campaign experience can connect to persistent owner data, so
even a legitimate acceptance action could otherwise create or alter a real campaign.

**How to apply:** Start an isolated API process with a temporary data store, seed
only through public routes and supported actions, and verify browser interactions,
save, and reopen against that same isolated store.
