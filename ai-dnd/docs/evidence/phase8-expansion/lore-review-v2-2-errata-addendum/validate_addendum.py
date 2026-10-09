# -*- coding: utf-8 -*-
"""Read-only addendum. Closes two false negatives in the V2.2 errata validator.

Does not modify V1, V2, V2.1, V2.2, or the errata package. Does not call Git.
A report is written only when --output is inside this directory.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPANSION = HERE.parent
ERRATA = EXPANSION / "lore-review-v2-2-errata"
V22_JSON = EXPANSION / "lore-review-v2-2" / "lore_extraction_candidates_v2_2.draft.json"
V21_JSON = EXPANSION / "lore-review-v2-1" / "lore_extraction_candidates_v2_1.draft.json"
MAPPING = EXPANSION / "lore-review-v2-2" / "V2_1_to_V2_2_Record_Mapping.md"

ERRATA_SHA256 = {
    "artifact_manifest.json": "fd1f54f41eedd95bff9a82bb5eb8f5e6c9ee8e53e88f052630ee998704f8839d",
    "build_ledger.py": "77e4b78fa41ab98fd6465c25ee7f4e6963e177b5613e462766b1dc1b9bdad564",
    "closure_assessment.md": "55d73399805d9880b438833dcf585cc79b9c3dffbd54e139acb001038b4eeea5",
    "correction_summary.md": "8cf154673aa3107eb69aa33f1b14f722395fde0316df3427b3dd904a658520b0",
    "field_errata.json": "14ef3cdedb439d9f65a52f3d01a3ad6fe4ca75021ccdc5aedd0b93b635fa2859",
    "input_manifest.json": "43845a6811626356b7af987785194b7d69ccecc7402563dc74aa0486037191c6",
    "prepare_errata.py": "ccc872e2dddc4d6ac05de242215991beaac7d77a1942f1a64e04ff50ce6cc66d",
    "semantic_ledger.jsonl": "a4c053a22f9bfa23503779ed521332d53c2c630a516cfc9ab8d5f4e176a68549",
    "validate_errata.py": "b284404c469ccf8027c462170291d522313a1de5f8259ebe2c2cc73c4614f577",
    "validation_results.txt": "a077f10c80e60627e7eb916b104336cfe47b938d2cadf4ac52f3a5307dbff0d4",
}
V22_SHA256 = "2255bc3b1a3b2a907e8b639528c1adb78e1b37e9a41b04934469fd6c33b46ee4"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_prior_checker():
    spec = importlib.util.spec_from_file_location("validate_errata_frozen", ERRATA / "validate_errata.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def title_map(records):
    found = {}
    conflicts = []
    for row in records:
        for cite in row["citations"]:
            digest = cite["source_sha256"]
            title = cite["source_title"]
            previous = found.setdefault(digest, title)
            if previous != title:
                conflicts.append(digest)
    return found, conflicts


def mapping_parents(text):
    forward = {}
    for line in text.splitlines():
        match = re.match(r"- `([^`]+)` (\w+) -> `([^`]+)`", line)
        if match:
            forward[match.group(1)] = match.group(3)
    return forward


def title_errors(rows, titles):
    errors = []
    for row in rows:
        for cite in row["citations"]:
            digest = cite.get("source_sha256")
            title = cite.get("source_title")
            expected = titles.get(digest)
            if expected is None or title != expected:
                errors.append(
                    f"source title mismatch {row['id']}: {title!r} does not match hash {digest}"
                )
    return errors


def lineage_errors(rows, frozen_by, v21_by, forward):
    errors = []
    for row in rows:
        required = frozen_by[row["id"]]
        required_parent = required["v21_id"]
        token_parent = row["id"].replace("22-", "21-", 1)
        if row["v21_id"] != required_parent or required_parent != token_parent or forward.get(required_parent) != row["id"]:
            errors.append(
                f"lineage parent mismatch {row['id']}: v21_id is {row['v21_id']}; required parent is {required_parent}"
            )
            continue
        if row["v2_id"] != required["v2_id"] or row["v1_ids"] != required["v1_ids"]:
            errors.append(f"lineage field mismatch {row['id']}: v2 or v1 ancestors differ from the frozen record")
            continue
        parent = v21_by.get(row["v21_id"])
        if parent is None:
            errors.append(f"lineage parent missing {row['id']}: {row['v21_id']}")
            continue
        if parent["v2_id"] != row["v2_id"] or parent["v1_ids"] != row["v1_ids"]:
            errors.append(
                f"lineage chain mismatch {row['id']}: {parent['id']} carries v2 {parent['v2_id']}, record carries {row['v2_id']}"
            )
    return errors


def prior_inputs(frozen_records, v21_records):
    module_counts = {}
    titles, _ = title_map(frozen_records)
    for digest in titles:
        module_counts[digest] = 10000
    ancestors = {
        "base_ids": {row["id"] for row in frozen_records},
        "v21": {row["id"] for row in v21_records},
        "v2": {row["v2_id"] for row in frozen_records},
        "v1": {vid for row in frozen_records for vid in row["v1_ids"]},
    }
    allowed = {
        "kind": {row["kind"] for row in frozen_records},
        "knowledge": {row["knowledge"] for row in frozen_records},
        "applicability_1501": {row["applicability_1501"] for row in frozen_records},
    }
    return module_counts, ancestors, allowed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        out = args.output.resolve()
        if out.parent != HERE:
            print("output must stay inside the addendum directory")
            return 2
    lines = []
    failures = []
    for name, expected in ERRATA_SHA256.items():
        actual = sha256(ERRATA / name)
        if actual != expected:
            failures.append("errata byte mismatch " + name)
    if sha256(V22_JSON) != V22_SHA256:
        failures.append("v22 json byte mismatch")
    errata = load(ERRATA / "field_errata.json")
    frozen = load(V22_JSON)
    v21 = load(V21_JSON)
    prior = load_prior_checker()
    view, apply_errors = prior.apply_patches(frozen["records"], errata["patches"])
    failures.extend(apply_errors)
    titles, title_conflicts = title_map(frozen["records"])
    if title_conflicts:
        failures.append("frozen titles disagree for one hash")
    frozen_by = {row["id"]: row for row in frozen["records"]}
    v21_by = {row["id"]: row for row in v21["records"]}
    forward = mapping_parents(MAPPING.read_text(encoding="utf-8"))
    if not apply_errors:
        failures.extend(title_errors(view, titles))
        failures.extend(lineage_errors(view, frozen_by, v21_by, forward))
    positive_failures = list(failures)
    counts, ancestors, allowed = prior_inputs(frozen["records"], v21["records"])
    exceptions = errata["direct_source_exceptions"]

    invented = copy.deepcopy(view)
    target = next(row for row in invented if row["id"] == "FR22-F-001")
    target["citations"][0]["source_title"] = "Invented Chronicle"
    old_title = prior.view_errors(invented, exceptions, counts, ancestors, allowed)
    new_title = title_errors(invented, titles)
    title_reason = "source title mismatch FR22-F-001: 'Invented Chronicle' does not match hash "
    title_ok = any(item.startswith(title_reason) for item in new_title) and not any("source title" in item for item in old_title)
    lines.append(("PASS " if title_ok else "FAIL ") + "negative invented source title")
    lines.append("  prior view_errors: " + (str(old_title) if old_title else "[]"))
    lines.append("  addendum: " + str(new_title))
    if not title_ok:
        failures.append("invented title was not rejected for a title-hash mismatch")

    swapped = copy.deepcopy(view)
    swapped_row = next(row for row in swapped if row["id"] == "FR22-F-001")
    swapped_row["v21_id"] = "WD21-F-001"
    old_line = prior.view_errors(swapped, exceptions, counts, ancestors, allowed)
    new_line = lineage_errors(swapped, frozen_by, v21_by, forward)
    expected_line = "lineage parent mismatch FR22-F-001: v21_id is WD21-F-001; required parent is FR21-F-001"
    line_ok = expected_line in new_line and not any("lineage" in item or "WD21-F-001" in item for item in old_line)
    lines.append(("PASS " if line_ok else "FAIL ") + "negative wrong existing V2.1 parent")
    lines.append("  prior view_errors: " + (str(old_line) if old_line else "[]"))
    lines.append("  addendum: " + str(new_line))
    if not line_ok:
        failures.append("wrong V2.1 parent was not rejected as a lineage mismatch")

    ledger_counts = {}
    for raw in (ERRATA / "semantic_ledger.jsonl").read_text(encoding="utf-8").splitlines():
        if raw.strip():
            verdict = json.loads(raw)["verdict"]
            ledger_counts[verdict] = ledger_counts.get(verdict, 0) + 1
    lines.append("positive corrected view errors: " + str(len(positive_failures)))
    lines.append("patches " + str(len(errata["patches"])) + " records " + str(len({p["record_id"] for p in errata["patches"]})))
    lines.append("ledger verdicts " + str(ledger_counts))
    lines.append("ledger corrected_by_erratum is assigned from patch membership before keyword overlap")
    lines.append("keyword overlap is not semantic verification")
    if failures:
        lines.append("FAILS " + str(len(failures)))
        lines.extend("FAIL " + item for item in failures)
    else:
        lines.append("FAILS 0")
        lines.append("PASS addendum")
    report = "\n".join(lines) + "\n"
    print(report)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
