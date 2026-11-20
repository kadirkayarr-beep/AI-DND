"""Read-only, outside the guard: one process plays the bench loop (api/tests/bench_engine_turn.py COMMANDS, SEED) on
one warm-up session and 5 measured fresh sessions; prints TURN_MS median=<ms>. Indicative only (no guard, no slot
sync); the binding speed numbers come from slot.sh benches. Usage: python turn_ms.py <ai-dnd root>
"""
import contextlib
import io
import os
import statistics
import sys
import time
import unittest

ROOT = os.path.abspath(sys.argv[1])
os.chdir(ROOT)
sys.path[:0] = [ROOT]
with contextlib.redirect_stdout(io.StringIO()):
    import game as engine  # noqa: E402
from api.tests.bench_engine_turn import COMMANDS, SEED  # noqa: E402
from api.tests.town_seed import fixed_town  # noqa: E402
from offline_test_support import offline_model  # noqa: E402


class _Case(unittest.TestCase):
    def runTest(self):
        pass


case, per_turn = _Case(), []


@offline_model(engine)
def body():
    with fixed_town(case, SEED):
        for i in range(6):
            session = engine.create_session(seed=SEED)
            messages = [{"role": "system", "content": "bench"}]
            started = time.perf_counter()
            for command in COMMANDS:
                session.run_player_turn(command, messages)
            if i:
                per_turn.append((time.perf_counter() - started) * 1000 / len(COMMANDS))


with contextlib.redirect_stdout(io.StringIO()):
    body()
case.doCleanups()
print(f"TURN_MS median={statistics.median(per_turn):.2f}")
