"""Read-only measurement (Plan 4 Task 1 input): where does the split's per-turn cost come from?
Plays the bench command list (api/tests/bench_engine_turn.py: SEED, COMMANDS) on fresh sessions with the offline
model and a fixed town, and prints:
  HOOK_CALLS_PER_TURN  calls of the Python-level _GameModule.__getattribute__ per turn (exact, sys.setprofile count)
  HOOK_CALLERS         top part/engine files whose frames made those calls
  READ_NS hook=<ns> plain=<ns>  cost of one module attribute read with the hook and with a plain module class
  EST_HOOK_MS_PER_TURN  HOOK_CALLS_PER_TURN x (hook - plain) / 1e6
  TURN_MS median=<ms>  plain median ms per turn of 5 sessions (same loop as the bench)
  PROFILE_SHARE_PCT  cProfile tottime of the hook (+ the module getattribute it calls) / total, in percent
Run from nowhere in particular: python hook_profile.py <ai-dnd root>. Writes nothing.
"""
import collections
import cProfile
import os
import pstats
import statistics
import sys
import time
import timeit
import types
import unittest

ROOT = os.path.abspath(sys.argv[1])
os.chdir(ROOT)
sys.path[:0] = [ROOT]
import game as engine  # noqa: E402
from api.tests.bench_engine_turn import COMMANDS, SEED  # noqa: E402
from api.tests.town_seed import fixed_town  # noqa: E402
from offline_test_support import offline_model  # noqa: E402


class _Case(unittest.TestCase):
    def runTest(self):
        pass


def play(runs, hook=None):
    case = _Case()
    per_turn = []

    @offline_model(engine)
    def body():
        with fixed_town(case, SEED):
            for _ in range(runs):
                session = engine.create_session(seed=SEED)
                messages = [{"role": "system", "content": "bench"}]
                if hook:
                    sys.setprofile(hook)
                started = time.perf_counter()
                for command in COMMANDS:
                    session.run_player_turn(command, messages)
                per_turn.append((time.perf_counter() - started) * 1000 / len(COMMANDS))
                sys.setprofile(None)
    body()
    case.doCleanups()
    return per_turn


cls = type(engine)
code = cls.__getattribute__.__code__ if cls is not types.ModuleType and "__getattribute__" in cls.__dict__ else None
print("MODULE_CLASS", cls.__name__, "HOOK", code is not None)
play(1)  # warm-up
calls, callers = 0, collections.Counter()


def counter(frame, event, arg):
    global calls
    if event == "call" and frame.f_code is code:
        calls += 1
        back = frame.f_back
        callers[os.path.relpath(back.f_code.co_filename, ROOT) if back else "?"] += 1


if code is not None:
    play(1, counter)
print(f"HOOK_CALLS_PER_TURN {calls / len(COMMANDS):.1f}")
print("HOOK_CALLERS", callers.most_common(12))
hook_ns = timeit.timeit("m.roll_d20", globals={"m": engine}, number=1_000_000) * 1000
engine.__class__ = types.ModuleType
try:
    plain_ns = timeit.timeit("m.roll_d20", globals={"m": engine}, number=1_000_000) * 1000
finally:
    engine.__class__ = cls
print(f"READ_NS hook={hook_ns:.1f} plain={plain_ns:.1f}")
print(f"EST_HOOK_MS_PER_TURN {calls / len(COMMANDS) * (hook_ns - plain_ns) / 1e6:.3f}")
print(f"TURN_MS median={statistics.median(play(5)):.2f}")
prof = cProfile.Profile()
prof.enable()
play(1)
prof.disable()
stats = pstats.Stats(prof)
total = stats.total_tt
own = 0.0
for (filename, _line, name), row in stats.stats.items():
    if (name == "__getattribute__" and filename.endswith("game.py")) or name == "<method '__getattribute__' of 'module' objects>":
        own += row[2]
print(f"PROFILE_SHARE_PCT {100 * own / total:.2f} (hook own+module getattribute {own * 1000:.1f} ms of {total * 1000:.1f} ms profiled)")
