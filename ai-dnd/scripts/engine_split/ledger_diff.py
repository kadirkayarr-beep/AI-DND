"""N4 ledger diff: merge the probe's JSON lines (api/tests/engine_probe.py) and compare a run with two bases.

A base is two equal runs (`--base`, `--base2`); what they disagree on is noise and never counts.
  DROPS: `<test>|<target>` patches that fired (called) in `--base` and not in `--new`.
  LOST:  tests `ok` in `--base` and not `ok` in `--new` (a test not `ok` in `--base2` is noise).
  SUBLOST: subtests failed or errored in `--new` and in neither base (a test already red hides them from LOST).
           A test named under SUBNOISE is no excuse: its new red subtests still count here.
  SUBNOISE: tests whose red-subtest lists differ between the two bases (printed, never counts, exit code unchanged).
  SUBGONE: tests with the same non-empty red-subtest list in both bases that are not `ok` in `--new` and lost one of
           those red subtests there (crashed before or inside their subtest loop; exit 1, like LOST).
  SUBCRASH: tests with red subtests in either base that fail or error whole in `--new` with no red-subtest record
           (crashed before their subtest loop; unlike SUBGONE it also sees a SUBNOISE test; exit 1).
Outcomes: an id run again inside another TestCase run (depth > 0) keeps the worst of its depth-0 records; an id with
no depth-0 record keeps the worst of all its records.
MIXED TREE (exit 1): the shards of one `--collect` run do not share one tree.
Refusals (exit 2): a run without its ledger, its proof or any outcome record; two bases on
different trees or with different tests (a dead shard in one base would turn every test after the cut into noise).
Blind spots (N3 is their only guard): tests that patch without calling, plain `game.X = ...` assignments, kind "other".
Usage (from ai-dnd/):
    python scripts/engine_split/ledger_diff.py --collect "<runs glob>" --out <file.json>
    python scripts/engine_split/ledger_diff.py --diff --base A.json --base2 B.json --new C.json   # exit 1 on DROPS/LOST/SUBLOST/SUBGONE/SUBCRASH
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path


def _records(dirs: list[Path]) -> list[dict]:
    lines = []
    for lines_dir in dirs:
        for path in sorted(Path(lines_dir).glob("ledger-*.jsonl")):
            lines += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return lines


def _hits(records: list[dict]) -> dict[str, bool | None]:
    hits = {}
    for r in records:
        if "target" in r:
            key = f"{r['test']}|{r['target']}"
            if hits.get(key) is not True and r["called"] is not None:   # True over False over None
                hits[key] = r["called"]
            hits.setdefault(key, None)
    return hits


def _outcomes(records: list[dict]) -> dict[str, str]:
    outcomes, outer = {}, {}            # outer: depth-0 records only (a run not inside another TestCase run)
    for r in records:
        if "outcome" not in r:
            continue
        for kept in (outcomes, outer) if r.get("depth", 0) == 0 else (outcomes,):
            if kept.get(r["test"], "ok") == "ok":                    # a test seen twice keeps its worst
                kept[r["test"]] = r["outcome"]
    return {**outcomes, **outer}        # D-372: inner re-runs of an id never override its outermost outcome


def _subtests(records: list[dict]) -> dict[str, list[str]]:
    subtests: dict[str, set[str]] = {}
    for r in records:
        if r.get("subtests"):
            subtests.setdefault(r["test"], set()).update(r["subtests"])
    return {test: sorted(ids) for test, ids in subtests.items()}


def merge_ledger(lines_dir: Path) -> dict[str, bool | None]:
    return _hits(_records([lines_dir]))


def merge_outcomes(lines_dir: Path) -> dict[str, str]:
    return _outcomes(_records([lines_dir]))


def noise(a: dict, b: dict) -> list[str]:
    missing = object()
    return sorted(k for k in set(a) | set(b) if a.get(k, missing) != b.get(k, missing))


def drops(base: dict, new: dict, noise_keys: set[str]) -> list[str]:
    return sorted(k for k, v in base.items() if v is True and new.get(k) is not True and k not in noise_keys)


def lost_tests(base: dict[str, str], new: dict[str, str], noise_keys: set[str]) -> list[str]:
    return sorted(k for k, v in base.items() if v == "ok" and new.get(k) != "ok" and k not in noise_keys)


def sublost(base: dict[str, list[str]], base2: dict[str, list[str]], new: dict[str, list[str]]) -> list[str]:
    seen = {s for subtests in (*base.values(), *base2.values()) for s in subtests}
    return sorted(s for subtests in new.values() for s in subtests if s not in seen)


def subgone(base: dict[str, list[str]], base2: dict[str, list[str]], new_outcomes: dict[str, str],
            new: dict[str, list[str]]) -> list[str]:
    return sorted(t for t, reds in base.items() if reds and base2.get(t) == reds and new_outcomes.get(t) != "ok"
                  and not set(reds) <= set(new.get(t, [])))


def subcrash(base: dict[str, list[str]], base2: dict[str, list[str]], new_outcomes: dict[str, str],
             new: dict[str, list[str]]) -> list[str]:
    return sorted(t for t in set(base) | set(base2) if (base.get(t) or base2.get(t))
                  and new_outcomes.get(t) in ("fail", "error") and not new.get(t))


def _collect(pattern: str, out: Path) -> int:
    runs = [Path(d) for d in sorted(glob.glob(pattern))]
    missing = [d for d in runs if not (d / "engine-probe").is_dir()]
    if not runs or missing:     # a run without its ledger means the probe never started: refuse, do not merge less
        print(f"NO_LEDGER runs={len(runs)}", *missing, sep="\n")
        return 2
    no_proof = [d for d in runs if not (d / "proof.json").is_file()]
    if no_proof:
        print(f"NO_PROOF runs={len(runs)}", *no_proof, sep="\n")
        return 2
    no_outcome = [d for d in runs if not _outcomes(_records([d / "engine-probe"]))]
    if no_outcome:              # an n7-only run, or a shard that died before its first test ended
        print(f"NO_OUTCOMES runs={len(runs)}", *no_outcome, sep="\n")
        return 2
    proofs = [json.loads((d / "proof.json").read_text(encoding="utf-8")) for d in runs]
    trees = {p["source_identity"]["total_digest_sha256"] for p in proofs}
    if len(trees) != 1:         # shards of one run share one synced tree (D-361 item 2)
        print("MIXED TREE", *sorted(trees), sep="\n")
        return 1
    records = _records([d / "engine-probe" for d in runs])
    data = {"hits": _hits(records), "outcomes": _outcomes(records), "subtests": _subtests(records),
            "seconds": max(p["seconds"] for p in proofs), "tree": trees.pop()}
    Path(out).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"COLLECTED runs={len(runs)} hits={len(data['hits'])} outcomes={len(data['outcomes'])} seconds={data['seconds']}")
    return 0


def _diff(base_path: Path, base2_path: Path, new_path: Path) -> int:
    base, base2, new = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (base_path, base2_path, new_path))
    if base["tree"] != base2["tree"]:
        print("TREES_DIFFER", base["tree"], base2["tree"], sep="\n")
        return 2
    keys = sorted(set(base["outcomes"]) ^ set(base2["outcomes"]))
    if keys:
        print(f"KEYS_DIFFER {len(keys)}", *(f"  {k}" for k in keys[:20]), sep="\n")
        if len(keys) > 20:
            print(f"  ... {len(keys) - 20} more")
        return 2
    hit_noise = set(noise(base["hits"], base2["hits"]))
    outcome_noise = set(noise(base["outcomes"], base2["outcomes"]))
    dropped = drops(base["hits"], new["hits"], hit_noise)
    lost = lost_tests(base["outcomes"], new["outcomes"], outcome_noise)
    sub = sublost(base["subtests"], base2["subtests"], new["subtests"])
    sub_noise = noise(base["subtests"], base2["subtests"])
    gone = subgone(base["subtests"], base2["subtests"], new["outcomes"], new["subtests"])
    crash = subcrash(base["subtests"], base2["subtests"], new["outcomes"], new["subtests"])
    print(f"NOISE {len(hit_noise | outcome_noise)}")
    print(f"SUBNOISE {len(sub_noise)}", *(f"  {k}" for k in sub_noise[:20]), sep="\n")
    if len(sub_noise) > 20:
        print(f"  ... {len(sub_noise) - 20} more")
    print(f"DROPS {len(dropped)}", *(f"  {k}" for k in dropped), sep="\n")
    print(f"LOST {len(lost)}", *(f"  {k}" for k in lost), sep="\n")
    print(f"SUBLOST {len(sub)}", *(f"  {k}" for k in sub), sep="\n")
    print(f"SUBGONE {len(gone)}", *(f"  {k}" for k in gone), sep="\n")
    print(f"SUBCRASH {len(crash)}", *(f"  {k}" for k in crash), sep="\n")
    return 1 if dropped or lost or sub or gone or crash else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--collect")
    parser.add_argument("--out")
    parser.add_argument("--diff", action="store_true")
    parser.add_argument("--base")
    parser.add_argument("--base2")
    parser.add_argument("--new")
    args = parser.parse_args(argv)
    if args.collect and args.out:
        return _collect(args.collect, Path(args.out))
    if args.diff and args.base and args.base2 and args.new:
        return _diff(Path(args.base), Path(args.base2), Path(args.new))
    parser.error("use --collect GLOB --out FILE, or --diff --base A --base2 B --new C")


if __name__ == "__main__":
    sys.exit(main())
