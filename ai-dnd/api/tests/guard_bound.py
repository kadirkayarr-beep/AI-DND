"""Tests the B06 guard cannot host, marked by what the guard denies.

The guarded launcher forbids child processes, sockets and any path with an
"evidence" or ".git" part. A test that needs one of those cannot run there, so
it is skipped under the guard and only under the guard. A skip is not a pass:
these tests have run nowhere in a guarded regression, and the guard-bound list
in the test baseline names how each was classified.
"""

import os
import unittest

GUARDED = bool(os.environ.get("AI_DND_GUARD_RUN_ROOT"))

CHILD_PROCESS = "needs a child process"
GIT_FIXTURE = "needs git and a fixture repository under a protected path"
LISTENER = "needs a real local socket"
EVIDENCE_READ = "reads the protected docs/evidence tree"


def guard_bound(reason):
    return unittest.skipIf(GUARDED, f"guard-bound: {reason}")
