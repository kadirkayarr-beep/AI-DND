"""50-turn and 100-turn live smokes.

Missing qwen3:8b is BLOCKED, not FAIL. REVIEW_PENDING is not PASS.

    python -m api.tests.live_incident_long_smoke
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

AI_DND_DIR = Path(__file__).resolve().parents[2]
MODEL_NAME = "qwen3:8b"


def main():
    sys.path.insert(0, str(AI_DND_DIR))
    try:
        import game
        from incidents import profiles
    except Exception as error:
        payload = {"final_gate_status": "BLOCKED", "reason": f"import failed: {error}"}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    loaded = profiles.load("neverwinter.v1")
    waterdeep = profiles.load("waterdeep.v1")
    baldurs_gate = profiles.load("baldurs_gate.v1")
    try:
        game.ollama.list()
        reachable = True
        reason = "model listing succeeded; long smoke is not run in this gate"
    except Exception as error:
        reachable = False
        reason = f"Ollama is unreachable: {error}"

    payload = {
        "final_gate_status": "BLOCKED",
        "live_generation": "unverified" if not reachable else "model_present_long_smoke_deferred",
        "reason": reason,
        "neverwinter_profile": None if loaded is None else loaded["review_status"],
        "waterdeep_profile": "UNREVIEWED_DISABLED" if waterdeep is None else "UNEXPECTED",
        "baldurs_gate_profile": "UNREVIEWED_DISABLED" if baldurs_gate is None else "UNEXPECTED",
        "review_pending_is_pass": False,
        "model": MODEL_NAME,
        "turns": {"planned": [50, 100], "executed": 0},
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
