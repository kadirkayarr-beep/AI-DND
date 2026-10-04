---
name: Regression evidence authority
description: Historical claims and real HTTP acceptance cannot be certified by new suite evidence.
---

Treat every newly executed AI-DND regression run as new evidence, never as
certification of an older run whose durable execution evidence is missing.
Keep suite-run evidence distinct from real-network HTTP acceptance evidence.
The historical bounded encounter 563/563 claim remains independently unverified.

**Why:** The owner requires verifiable future runs without retroactive historical
certification, and explicitly excludes push, publication and commit-provenance
changes from evidence-retention work.

**How to apply:** When reporting future regression results, link the retained
run record and distinguish its exact scope from older claims and HTTP
acceptance. Preserve failed development attempts with their limitations rather
than replacing them with a later successful run.

Offline tests of HTTP archive handling are not live HTTP acceptance evidence,
even when they exercise the entire verifier with fake responses. Keep their
temporary fixture records out of retained real-network acceptance archives.

**Why:** Testing evidence retention must not silently authorize a live campaign
run or produce a misleading real-network acceptance claim.

**How to apply:** Validate archive behavior offline unless the owner separately
approves live acceptance; distinguish those contract checks from gameplay proof.

Keep legacy model-mock regression runs separate from API adapter suites until
their shared-mock isolation is repaired. A passing isolated run does not turn a
failed combined invocation into passing evidence.

**Why:** API suite imports can mutate the legacy shared model mock's chat
callback during collection, causing unrelated regression functions to fail
when they configure mock responses. Separate processes passed while the combined
invocation retained those errors.

**How to apply:** Retain both failed combined attempts and passing isolated
invocations, state their scopes explicitly, and do not expand a passing count
to cover an invocation that was not successful.