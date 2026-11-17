"""Fixed turn benchmark for the game.py split (spec T0.5): the same command list on five fresh sessions.

Not a pass/fail check on speed. The stage gates compare the TURN_BENCH line before and after a move.
Ruling: the list below is the player-input kind the engine surface tests already use (test_regression.py:
looking around, doors, stealth, talking, inventory, rest), played with the offline model on a fixed town
and a fixed dice seed. No scenario file is used: a journey scenario needs the campaign store and a scripted
model, which would time those instead of the engine turn.
"""

from __future__ import annotations

import statistics
import sys
import time
import unittest

import game as engine
from api.tests.town_seed import fixed_town
from offline_test_support import offline_model

SEED = 20261117
RUNS = 5
COMMANDS = (
    "etrafıma bakıyorum",
    "gizleniyorum",
    "kapıyı açıyorum",
    "barmenle konuşuyorum",
    "envanterime bakıyorum",
    "etrafı dikkatle arıyorum",
    "masayı inceliyorum",
    "bir adım ilerliyorum",
    "etrafıma bakıyorum",
    "kendime bir içki istiyorum",
    "dinleniyorum",
    "etrafıma bakıyorum",
)


class EngineTurnBenchmark(unittest.TestCase):
    @offline_model(engine)
    def test_fixed_command_list_on_five_fresh_sessions(self):
        per_turn_ms = []
        with fixed_town(self, SEED):
            for _ in range(RUNS):
                session = engine.create_session(seed=SEED)
                messages = [{"role": "system", "content": "bench"}]
                started = time.perf_counter()
                for command in COMMANDS:
                    session.run_player_turn(command, messages)
                per_turn_ms.append((time.perf_counter() - started) * 1000 / len(COMMANDS))
        self.assertEqual(len(per_turn_ms), RUNS)
        # stderr: where "Ran N tests" already reaches the run's target.log (preflight F13).
        print(f"TURN_BENCH median_ms_per_turn={statistics.median(per_turn_ms):.2f} turns={len(COMMANDS)}",
              file=sys.stderr, flush=True)


if __name__ == "__main__":
    unittest.main()
