"""N7 per-function executed lines: merge the probe's `lines-<pid>.json` files (api/tests/engine_probe.py) into one count
per top-level engine name and compare a run with two bases.

A count is the number of executed lines inside a name's `def_line..end`, summed over game.py and every part by name.
Only functions, classes and assignments count: import lines (a move's re-export) and line-numbered statements
(`<If@N>`) would change on every move.
The index is built on the measured tree (`--engine-root` = a `git archive <measured sha>` copy of ai-dnd), never on
the current worktree: line numbers only mean something in the tree that produced them.
A base is two equal runs (`--base`, `--base2`); names they disagree on are noise and never count.
  DOWN: names that ran fewer lines in `--new` than in `--base` (exit 1).
  UP:   names that ran more lines (new tests may explain them; each is listed in the ledger with its test).
Refusals (exit 2): a run without its lines file or its proof; shards on different trees; a lines file naming a path the
engine root does not hold; a run that counts no function; two bases on different trees.
Usage (from ai-dnd/):
    python scripts/engine_split/coverage_by_function.py --collect "<runs glob>" --engine-root <dir> --out <file.json>
    python scripts/engine_split/coverage_by_function.py --diff --base A.json --base2 B.json --new C.json
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

# A script run as a file has only its own folder on sys.path: add ai-dnd and ai-dnd/scripts (same as the tests).
if __name__ == "__main__":
    sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]

from api.tests.engine_sources import engine_source_files  # noqa: E402
from engine_split.inventory import top_level_index  # noqa: E402


COUNTED_KINDS = {"function", "class", "assign"}


def function_hits(lines: dict[str, list[int]], index: dict[str, list[dict]]) -> dict[str, int]:
    # Only names whose count survives a move: kind 'other' is named by its line number and 'import' is the
    # re-export a move adds to game.py (or a part's own import), so both are left out. No kind = counted.
    hits: dict[str, int] = {}
    for path, executed in lines.items():
        for entry in index.get(path, []):
            if entry.get("kind", "function") not in COUNTED_KINDS:
                continue
            count = sum(1 for line in executed if entry["def_line"] <= line <= entry["end"])
            if count:
                hits[entry["name"]] = hits.get(entry["name"], 0) + count
    return hits


def unequal(base: dict[str, int], new: dict[str, int], noise_names: set[str]) -> list[str]:
    return sorted(n for n in set(base) | set(new) if base.get(n, 0) != new.get(n, 0) and n not in noise_names)


def _collect(pattern: str, engine_root: Path, out: Path) -> int:
    runs = [Path(d) for d in sorted(glob.glob(pattern))]
    missing = [d for d in runs if not list((d / "engine-probe").glob("lines-*.json"))]
    if not runs or missing:     # a run without its lines file means the probe never wrote: refuse, do not count less
        print(f"NO_LINES runs={len(runs)}", *missing, sep="\n")
        return 2
    no_proof = [d for d in runs if not (d / "proof.json").is_file()]
    if no_proof:
        print(f"NO_PROOF runs={len(runs)}", *no_proof, sep="\n")
        return 2
    proofs = [json.loads((d / "proof.json").read_text(encoding="utf-8")) for d in runs]
    trees = {p["source_identity"]["total_digest_sha256"] for p in proofs}
    if len(trees) != 1:         # shards of one run share one synced tree
        print("TREES_DIFFER", *sorted(trees), sep="\n")
        return 2
    lines: dict[str, set[int]] = {}
    for run in runs:
        for path in sorted((run / "engine-probe").glob("lines-*.json")):
            for name, executed in json.loads(path.read_text(encoding="utf-8")).items():
                lines.setdefault(name, set()).update(executed)
    index = {p.relative_to(engine_root).as_posix(): top_level_index(p) for p in engine_source_files(engine_root)}
    unknown = sorted(set(lines) - set(index))
    if unknown:                 # a path the engine root does not hold would count as nothing: refuse
        print("UNKNOWN_FILE", *unknown, sep="\n")
        return 2
    data = {"functions": function_hits({k: sorted(v) for k, v in lines.items()}, index),
            "seconds": max(p["seconds"] for p in proofs), "tree": trees.pop()}
    if not data["functions"]:
        print("NO_FUNCTIONS")
        return 2
    Path(out).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"COLLECTED runs={len(runs)} files={len(lines)} functions={len(data['functions'])} seconds={data['seconds']}")
    return 0


def _diff(base_path: Path, base2_path: Path, new_path: Path) -> int:
    files = [json.loads(Path(p).read_text(encoding="utf-8")) for p in (base_path, base2_path, new_path)]
    if files[0]["tree"] != files[1]["tree"]:
        print("TREES_DIFFER", files[0]["tree"], files[1]["tree"], sep="\n")
        return 2
    base, base2, new = (f["functions"] for f in files)
    noise_names = set(unequal(base, base2, set()))
    changed = unequal(base, new, noise_names)
    down = [n for n in changed if new.get(n, 0) < base.get(n, 0)]
    up = [n for n in changed if new.get(n, 0) > base.get(n, 0)]
    print(f"NOISE {len(noise_names)}")
    print(f"DOWN {len(down)}", *(f"  {n}" for n in down), sep="\n")
    print(f"UP {len(up)}", *(f"  {n}" for n in up), sep="\n")
    return 1 if down else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--collect")
    parser.add_argument("--engine-root")
    parser.add_argument("--out")
    parser.add_argument("--diff", action="store_true")
    parser.add_argument("--base")
    parser.add_argument("--base2")
    parser.add_argument("--new")
    args = parser.parse_args(argv)
    if args.collect and args.engine_root and args.out:
        return _collect(args.collect, Path(args.engine_root), Path(args.out))
    if args.diff and args.base and args.base2 and args.new:
        return _diff(Path(args.base), Path(args.base2), Path(args.new))
    parser.error("use --collect GLOB --engine-root DIR --out FILE, or --diff --base A --base2 B --new C")


if __name__ == "__main__":
    sys.exit(main())
