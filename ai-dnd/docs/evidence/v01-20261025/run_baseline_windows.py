"""Record the release-gate baseline on Windows, where run_tests.py cannot run.

ai-dnd/run_tests.py raises "Gate process-tree cleanup requires a POSIX runtime"
on Windows, so the daily gates cannot be recorded with it. This evidence helper
runs the same 33 gates with the same commands (unittest completion receipt for
api/tests modules, plain script execution for the rest), one child process per
gate with a timeout, and writes one JSON line per gate. It changes no product
code and reads no save or secret.

Usage (from the ai-dnd directory, PYTHONUTF8=1):
    python docs/evidence/v01-20261025/run_baseline_windows.py OUT.jsonl [LABEL]
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import run_tests  # noqa: E402  (reuses the real gate list)

TIMEOUT_SECONDS = 1200


def run_gate(test_name):
    started = time.time()
    if Path(test_name).parent != Path("."):
        module = ".".join(Path(test_name).with_suffix("").parts)
        with tempfile.TemporaryDirectory(prefix="unittest-gate-") as directory:
            receipt = Path(directory) / "completed"
            command = [
                sys.executable, "-c",
                "import sys; from run_tests import run_unittest_gate; "
                "sys.exit(run_unittest_gate(sys.argv[1], sys.argv[2]))",
                module, str(receipt),
            ]
            outcome = _spawn(command)
            outcome["receipt_ok"] = receipt.exists() and receipt.read_text(encoding="utf-8") == module
            if outcome["exit"] == 0 and not outcome["receipt_ok"]:
                outcome["exit"] = -2
    else:
        outcome = _spawn([sys.executable, str(ROOT / test_name)])
    outcome["seconds"] = round(time.time() - started, 1)
    return outcome


def _spawn(command):
    try:
        completed = subprocess.run(
            command, cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        text = (completed.stdout or "") + (completed.stderr or "")
        return {"exit": completed.returncode, "tail": text.strip().splitlines()[-6:]}
    except subprocess.TimeoutExpired:
        return {"exit": -1, "tail": [f"TIMEOUT after {TIMEOUT_SECONDS}s"]}


def main(argv):
    out_path = Path(argv[0])
    label = argv[1] if len(argv) > 1 else ""
    with out_path.open("a", encoding="utf-8") as out:
        for test_name in run_tests.TESTS:
            row = {"label": label, "gate": test_name,
                   "start_utc": datetime.now(timezone.utc).isoformat()}
            row.update(run_gate(test_name))
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            print(f"{row['exit']:>3} {row['seconds']:>7}s  {test_name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
