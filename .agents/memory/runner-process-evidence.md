---
name: Runner process evidence
description: Why release acceptance needs whole-process termination fixtures as well as Python exception fixtures.
---

Offline runner acceptance must exercise direct child-process termination, not
only catchable Python exits. Source definition checks are not runtime
completion evidence.

**Why:** A loading hook can terminate with `os._exit(0)` without raising an
exception or producing a unittest result. A zero process status therefore does
not prove assertions ran successfully.

**How to apply:** Preserve separate source-only and real-child-process checks
when changing release infrastructure. Completion evidence detects accidental
early termination; it is not a security boundary against malicious test code.
