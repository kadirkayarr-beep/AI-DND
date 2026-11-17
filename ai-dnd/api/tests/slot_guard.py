"""Is the run inside the B06 test-slot guard (tools/acceptance/linux_guard)?

The guard is an audit hook that refuses child processes and any socket but an AF_UNIX stream. It is the slot's
safety rail and CI has none, so a test that needs a child process or a TCP loopback socket cannot run under it
(D-294, D-304). The slot launcher sets AI_DND_GUARD_EXPECTED_SHA256 for the target run; CI never does.
"""
import os

GUARDED = bool(os.environ.get("AI_DND_GUARD_EXPECTED_SHA256"))
