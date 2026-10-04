---
name: Regression evidence authority
description: Historical claims and real HTTP acceptance cannot be certified by new suite evidence.
---

Treat every newly executed AI-DND regression run as new evidence, never as
certification of an older run whose durable execution evidence is missing.
Keep suite-run evidence distinct from real-network HTTP acceptance evidence.
Verify historical claims against the original evidence actually available in
the environment performing the review; never substitute a newly executed run.

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

A local verifier source fingerprint never proves the source revision of the
server under test, including servers reached through localhost.

**Why:** The owner explicitly requires verifier/server identity separation;
the verifier checkout and the running server need not contain the same code.

**How to apply:** Keep server identity unknown/unverified unless independently
established. Exclude generated archives and exports from local source hashing
so evidence writes do not look like source edits.

Retain combined legacy/API regression evidence in both selector orders when
changing shared model-mock ownership. A passing isolated run does not turn a
failed combined invocation into passing evidence.

**Why:** API suite imports previously mutated the legacy shared model mock's
chat callback during collection. Isolated processes hid the ownership defect;
collection-order checks are needed to demonstrate that it is repaired.

**How to apply:** Keep historical failed combined and passing isolated records,
and label new passing combined invocations separately. Exercise scoped mocks
through the retained function-test runner as well as API fixtures, rather than
relying on fixtures available only under a different test framework.

Do not repair unrelated legacy gameplay assumptions as part of model-binding
isolation. A cleanup contract may explicitly check an existing gameplay refusal,
but its passing result must not be reported as a passing gameplay entry point.

**Why:** Broader isolation runs can expose old fixture failures unrelated to
model ownership; changing gameplay or silently swallowing them would hide the
distinction the owner needs.

**How to apply:** Retain the failed attempt, identify the specific pre-existing
refusal, label cleanup-only evidence, and propose the fixture repair separately.