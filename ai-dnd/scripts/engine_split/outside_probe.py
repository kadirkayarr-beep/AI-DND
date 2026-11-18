"""Outside-the-guard start probe for the engine split (D-341): the checks the guarded test child cannot run.

The guarded launcher blocks child processes, so run this with the slot's Python outside the guard (SLOTPY):
    cd /root/aidnd-env-<N>/src/ai-dnd && /root/aidnd-env-<N>/proj/.venv/bin/python scripts/engine_split/outside_probe.py
Steps: both import orders in fresh interpreters (`import game, game_parts` / `import game_parts, game`), each printing
the loaded `game_parts.*` modules; `python game.py` from a fresh temporary folder with the input `2`, `zar at`, `exit`
(rc 0, one `D20 sonucu:`, one `Oyun kapatılıyor`); the same start with stdin closed (rc 1, `EOFError`).
Prints `PROBE ok parts=<list>` and exits 0, or `PROBE FAIL <step>` and exits 1.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHOW_PARTS = "import sys; print(sorted(n for n in sys.modules if n.startswith('game_parts.')))"


def _run(args: list[str], cwd: Path | str, **kwargs) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=env, timeout=120,
                          **kwargs)


def _fail(step: str, done: subprocess.CompletedProcess) -> int:
    print(f"PROBE FAIL {step}")
    print(f"rc={done.returncode}\n--- stdout tail\n{done.stdout[-1500:]}\n--- stderr tail\n{done.stderr[-1500:]}",
          file=sys.stderr)
    return 1


def main() -> int:
    seen = []
    for order in ("game, game_parts", "game_parts, game"):
        done = _run([sys.executable, "-c", f"import {order}; {SHOW_PARTS}"], ROOT)
        if done.returncode != 0:
            return _fail(f"import {order}", done)
        seen.append(done.stdout.strip())
    if seen[0] != seen[1]:
        print(f"PROBE FAIL import orders differ: {seen[0]} / {seen[1]}")
        return 1
    with tempfile.TemporaryDirectory() as cwd:
        game_py = str(ROOT / "game.py")
        done = _run([sys.executable, game_py], cwd, input="2\nzar at\nexit\n")
        if (done.returncode, done.stdout.count("D20 sonucu:"), done.stdout.count("Oyun kapatılıyor")) != (0, 1, 1):
            return _fail("python game.py", done)
        done = _run([sys.executable, game_py], cwd, stdin=subprocess.DEVNULL)
        if done.returncode != 1 or "EOFError" not in done.stderr:
            return _fail("closed stdin", done)
    print(f"PROBE ok parts={seen[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
