"""Plan 4 (D-355): sensitivity.classify on game.py and every game_parts file of <ai-dnd root>; set difference against sensitive.json (read-only).
Usage: python classify_all.py <ai-dnd root>
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "scripts"))
from engine_split.sensitivity import classify  # noqa: E402

lock = json.loads((ROOT / "api/tests/engine_split_locks/sensitive.json").read_text(encoding="utf-8"))
locked = set(lock["functions"])
removed = {row["name"] for row in lock["removed"]}
files = [ROOT / "game.py"] + sorted((ROOT / "game_parts").glob("*.py"))
flagged = {}
for path in files:
    for name, reasons in classify(path).items():
        flagged.setdefault(name, []).append((path.relative_to(ROOT).as_posix(), reasons))
print(f"FILES {len(files)} FLAGGED {len(flagged)} LOCKED {len(locked)} REMOVED {len(removed)}")
extra = sorted(n for n in flagged if n not in locked and n not in removed)
for name in extra:
    for rel, reasons in flagged[name]:
        print(f"NOT_IN_LOCK {rel}: {name} {reasons}")
for name in sorted(locked - set(flagged)):
    print(f"LOCKED_NOT_FLAGGED {name}")
in_parts = sorted(n for n, hits in flagged.items() if any(rel.startswith("game_parts/") for rel, _ in hits))
print("FLAGGED_IN_PARTS", in_parts)
print(f"DIFF not_in_lock={len(extra)} locked_not_flagged={len(locked - set(flagged))}")
