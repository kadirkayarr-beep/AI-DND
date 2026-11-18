"""Gate boot: the guarded launcher builds the test child's environment from scratch, so a flag set outside never reaches it.

The run root is `<stamp>-<label>` (`slot_gate.sh` appends `-<shard>`); the label's tokens say what the child turns on.
Put `api.tests.gate_boot` first in the selector list: importing it applies the tokens before any other test module loads.
It never imports the engine (`game`, `game_parts`).
"""
import os
from pathlib import Path


def tokens(run_root: str) -> set[str]:
    return set(Path(run_root).name.split("-")[1:])


def boot(run_root: str, environ=os.environ) -> set[str]:
    applied = set()
    found = tokens(run_root)
    if "fon" in found:
        environ["AI_DND_FRONT_PROPOSAL"] = "1"
        applied.add("fon")
    return applied


boot(os.environ.get("AI_DND_GUARD_RUN_ROOT", ""))
