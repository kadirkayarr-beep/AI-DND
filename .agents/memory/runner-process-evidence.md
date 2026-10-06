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

Keep timeout acceptance offline and use fixture-specific short deadlines rather
than reducing production gate limits to make acceptance fast.

**Why:** Import and loading hooks can hang before unittest has a result to
inspect. Real sleeping children prove the parent continues without requiring
gameplay, network access, or long production deadlines.

**How to apply:** Exercise imports/loading and scripts separately; retain
source-only preflight assertions and later-gate sentinels. Direct-child timeout
cleanup is not proof that subprocess descendants have also stopped.

Process-group timeout guarantees apply only to descendants that inherit the
gate's group; deliberately detached processes are outside that boundary.
Zombie descendants are not running work and must be reaped by their adopting
parent, not by an unrelated runner.

**Why:** POSIX group signals bound ordinary process-tree cleanup without
introducing Linux subreaper state into a runner that itself nests copied runners.
Treating zombie presence as ongoing execution creates false failures in
containers whose init does not promptly reap orphans.

**How to apply:** Verify live process state before a later gate runs and retain
fixture cleanup even on assertion failure. Do not claim detached descendants
or interruption cleanup from timeout-only acceptance.
