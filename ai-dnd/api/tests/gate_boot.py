"""Gate boot: the guarded launcher builds the test child's environment from scratch, so a flag set outside never reaches it.

The run root is `<stamp>-<label>` (`slot_gate.sh` appends `-<shard>`); the label's tokens say what the child turns on.
Put `api.tests.gate_boot` first in the selector list: importing it applies the tokens before any other test module loads.
It never imports the engine (`game`, `game_parts`).
"""
import argparse
import os
import sys
from pathlib import Path

from api.tests import engine_probe
from api.tests.engine_sources import engine_source_files

TOKENS = ("fon", "n4", "n7")


def tokens(run_root: str) -> set[str]:
    return set(Path(run_root).name.split("-")[1:])


def label_tokens(label: str) -> list[str]:
    # A token word glued to other text (`p2g0fon-a`, `fon_a`) would run with that token off: refuse it.
    parts = label.split("-")
    glued = [p for p in parts if p not in TOKENS and any(t in p for t in TOKENS)]
    if glued:
        raise ValueError(f"{', '.join(glued)} holds {'/'.join(TOKENS)} but is not a dash-separated token")
    return [t for t in TOKENS if t in parts]


def main(argv=None) -> int:
    # slot_gate.sh runs `python -m api.tests.gate_boot --label LABEL` before it stages or syncs anything
    parser = argparse.ArgumentParser(description="Print the tokens a slot_gate.sh label applies; refuse a glued one.")
    parser.add_argument("--label", required=True)
    label = parser.parse_args(argv).label
    try:
        print("TOKENS", " ".join(label_tokens(label)) or "none")
    except ValueError as exc:
        print(f"BAD_LABEL {label}: {exc}", file=sys.stderr)
        return 2
    return 0


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

if __name__ == "__main__":
    sys.exit(main())
