"""Gate boot: the guarded launcher builds the test child's environment from scratch, so a flag set outside never reaches it.

The run root is `<stamp>-<label>` (`slot_gate.sh` appends `-<shard>`); the label's tokens say what the child turns on.
Put `api.tests.gate_boot` first in the selector list: importing it applies the tokens before any other test module loads.
It never imports the engine (`game`, `game_parts`).
"""
import os
import sys
from pathlib import Path

from api.tests import engine_probe
from api.tests.engine_sources import engine_source_files


def tokens(run_root: str) -> set[str]:
    return set(Path(run_root).name.split("-")[1:])


def boot(run_root: str, environ=os.environ, tool_id: int = sys.monitoring.COVERAGE_ID) -> set[str]:
    applied = set()
    found = tokens(run_root)
    if "fon" in found:
        environ["AI_DND_FRONT_PROPOSAL"] = "1"
        applied.add("fon")
    if "n4" in found:
        engine_probe.install_ledger(Path(run_root) / "engine-probe")
        applied.add("n4")
    if "n7" in found:
        engine_probe.install_lines(Path(run_root) / "engine-probe", engine_source_files(), tool_id)
        applied.add("n7")
    return applied


boot(os.environ.get("AI_DND_GUARD_RUN_ROOT", ""))
