"""D-218: run every Python test module (api/tests/test_*.py) in CI, optionally as one shard of N.

api/tests has no __init__.py, so `unittest discover` cannot start there; modules are passed by dotted name instead.
Usage (from ai-dnd/): python scripts/full_python_suite.py --shard 2 --of 4
"""
import argparse
from pathlib import Path
import subprocess
import sys


def modules(root: Path) -> list[str]:
    return sorted("api.tests." + path.stem for path in (root / "api" / "tests").glob("test_*.py"))


def shard(names: list[str], index: int, count: int) -> list[str]:
    if count < 1 or not 1 <= index <= count:
        raise ValueError(f"shard {index} of {count} does not exist")
    return names[index - 1::count]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, default=1)
    parser.add_argument("--of", type=int, default=1)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    chosen = shard(modules(root), args.shard, args.of)
    print(f"shard {args.shard}/{args.of}: {len(chosen)} modules", flush=True)
    return subprocess.call([sys.executable, "-m", "unittest", *chosen], cwd=root)


if __name__ == "__main__":
    sys.exit(main())
