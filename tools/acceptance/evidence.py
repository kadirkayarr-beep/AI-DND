"""Unique-method ledger and evidence records for acceptance (B02).

Normalizes the existing regression-evidence harness output; never runs the game,
a model or a server, and never turns missing or mocked evidence into a real PASS.
"""
import hashlib
import json
from pathlib import Path
import re


STATUSES = ("PASS", "FAIL", "SKIP", "BLOCKED", "NOT_RUN", "UNCONFIGURED")
COLUMNS = ("build", "typecheck", "lint", "unit", "http", "browser", "auth", "model",
           "human_acceptance")
RUNTIME_COLUMNS = ("http", "browser", "auth", "model", "human_acceptance")
# Worst first; a column never reports better than its worst record.
SEVERITY = ("FAIL", "BLOCKED", "NOT_RUN", "UNCONFIGURED", "SKIP", "PASS")
HARNESS_OUTCOMES = {"pass": "PASS", "failure": "FAIL", "error": "FAIL", "skip": "SKIP"}
REQUIRED_FIELDS = (
    "sourceSHA", "treeState", "runtimeSHA", "os", "runtime", "model", "column", "command",
    "cwd", "exitCode", "testID", "status", "fixtureOwner", "mock", "realDependencies",
    "rawDigest", "artifactDigest", "startedAt", "endedAt", "reviewer",
)
DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "docs" / "acceptance" / "evidence-runs"
SHA1 = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")


def check_result(row):
    if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip():
        raise ValueError(f"Result needs a nonempty id: {row!r}")
    if row.get("status") not in STATUSES:
        raise ValueError(f"Unknown status for {row['id']}: {row.get('status')!r}")


def settle(history):
    """Only a later PASS closes an earlier failure; a later FAIL always wins.

    Any other later status (SKIP, BLOCKED, NOT_RUN, UNCONFIGURED) keeps the worse of the two.
    """
    status = history[0]
    for later in history[1:]:
        status = later if later in ("PASS", "FAIL") else min(status, later, key=SEVERITY.index)
    return status


def deduplicate_results(results):
    """One method per qualified ID; disagreement and closed failures stay listed."""
    methods = {}
    for row in results:
        check_result(row)
        methods.setdefault(row["id"], []).append(row["status"])
    final = {key: settle(history) for key, history in methods.items()}
    statuses = {}
    for status in final.values():
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "executions": len(results),
        "unique_methods": len(methods),
        "statuses": {name: statuses[name] for name in STATUSES if name in statuses},
        "conflicts": [key for key, history in methods.items() if len(set(history)) > 1],
        "closed_failures": [key for key, history in methods.items() if final[key] == "PASS"
                            and any(earlier in ("FAIL", "BLOCKED") for earlier in history)],
        "methods": {key: {"status": final[key], "executions": len(history),
                          "statuses": history} for key, history in methods.items()},
    }


def normalize_harness_run(run, log_path):
    """Map run_regression_evidence `run.json` outcomes; keep the exit code and raw log digest."""
    per_test = run.get("per_test")
    if not isinstance(per_test, list) or not per_test:
        raise ValueError("Harness run recorded no per_test results")
    exit_status = run.get("exit_status")
    if type(exit_status) is not int:
        raise ValueError("Harness run has no final exit status (incomplete run)")
    results = []
    # setUpClass/setUpModule failures are suite events, not executed test methods.
    for row in [*per_test, *run.get("suite_events", [])]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise ValueError(f"Malformed harness result: {row!r}")
        status = HARNESS_OUTCOMES.get(row.get("outcome"))
        if status is None:
            raise ValueError(f"Unclassified harness outcome for {row.get('id')}: {row.get('outcome')!r}")
        results.append({"id": row["id"], "status": status})
    failed = any(row["status"] == "FAIL" for row in results)
    if (exit_status == 0) == failed:
        raise ValueError("Harness exit status contradicts the recorded outcomes")
    digest = hashlib.sha256(Path(log_path).read_bytes()).hexdigest() if log_path else None
    return {"results": results, "exit_status": exit_status, "raw_log_sha256": digest}


def provenance(record):
    return "FIXTURE" if record["mock"] or record["fixtureOwner"] is not None else "REAL"


def validate_record(record):
    if not isinstance(record, dict):
        raise ValueError("EvidenceRecord must be a mapping")
    missing = [name for name in REQUIRED_FIELDS if name not in record]
    if missing:
        raise ValueError(f"EvidenceRecord is missing fields: {missing}")
    if not isinstance(record["sourceSHA"], str) or not SHA1.fullmatch(record["sourceSHA"]):
        raise ValueError("sourceSHA must be a 40-hex commit")
    runtime = record["runtimeSHA"]
    if runtime != "UNKNOWN" and not (isinstance(runtime, str) and SHA1.fullmatch(runtime)):
        raise ValueError("runtimeSHA must be a 40-hex commit or UNKNOWN")
    if record["column"] not in COLUMNS:
        raise ValueError(f"Unknown evidence column: {record['column']!r}")
    if record["status"] not in STATUSES:
        raise ValueError(f"Unknown status: {record['status']!r}")
    code = record["exitCode"]
    if code is not None and (type(code) is not int):
        raise ValueError("exitCode must be an integer or null")
    if record["status"] == "PASS" and code != 0:
        raise ValueError("PASS requires a recorded exitCode of 0")
    tree = record["treeState"]
    if not (isinstance(tree, dict) and isinstance(tree.get("clean"), bool)
            and isinstance(tree.get("changed_paths"), list)):
        raise ValueError("treeState needs clean and changed_paths")
    unknown = sorted(set(record) - set(REQUIRED_FIELDS))
    if unknown:
        raise ValueError(f"EvidenceRecord has unknown fields: {unknown}")
    if type(record["mock"]) is not bool:
        raise ValueError("mock must be boolean")
    dependencies = record["realDependencies"]
    if not isinstance(dependencies, list) or not all(
            isinstance(item, str) and item.strip() for item in dependencies):
        raise ValueError("realDependencies must be a list of nonempty strings")
    for name in ("fixtureOwner", "reviewer"):
        if record[name] is not None and not (isinstance(record[name], str) and record[name].strip()):
            raise ValueError(f"{name} must be null or a nonempty string")
    if record["model"] is not None and not isinstance(record["model"], dict):
        raise ValueError("model must be null or an object")
    for name in ("rawDigest", "artifactDigest"):
        if record[name] is not None and not SHA256.fullmatch(str(record[name])):
            raise ValueError(f"{name} must be a sha256 hex digest or null")
    for name in ("command", "cwd", "testID", "os", "runtime", "startedAt", "endedAt"):
        if not isinstance(record[name], str) or not record[name].strip():
            raise ValueError(f"{name} must be a nonempty string")
    if provenance(record) == "REAL":
        if not dependencies and record["status"] in ("PASS", "FAIL"):
            raise ValueError("A real PASS/FAIL must name its real dependencies; "
                             "otherwise record it as BLOCKED or give it a fixtureOwner")
        if runtime not in ("UNKNOWN", record["sourceSHA"]):
            raise ValueError("Real evidence must come from the source it claims (runtimeSHA mismatch)")


def record_evidence(record, root=None):
    validate_record(record)
    directory = Path(root) if root is not None else DEFAULT_ROOT
    directory.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with (directory / "evidence.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(line)


def satisfies_real_acceptance(record):
    """Runtime-column PASS from real dependencies on the exact source; fixtures never qualify."""
    validate_record(record)
    needs = {"human_acceptance": record["reviewer"], "model": record["model"]}
    return (record["column"] in RUNTIME_COLUMNS and record["status"] == "PASS"
            and provenance(record) == "REAL" and record["runtimeSHA"] == record["sourceSHA"]
            and needs.get(record["column"], True) not in (None, "", {}))


def summarize_columns(records):
    for row in records:
        validate_record(row)
    if len({row["sourceSHA"] for row in records}) > 1:
        raise ValueError("Records come from different sources; summarize one source at a time")
    columns = {}
    for name in COLUMNS:
        rows = [row for row in records if row["column"] == name]
        if not rows:
            columns[name] = {"status": "UNCONFIGURED" if name == "lint" else "NOT_RUN",
                             "provenance": None}
            continue
        kinds = {provenance(row) for row in rows}
        columns[name] = {
            "status": min((row["status"] for row in rows), key=SEVERITY.index),
            "provenance": kinds.pop() if len(kinds) == 1 else "MIXED",
        }
    return columns
