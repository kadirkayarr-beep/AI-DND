"""Failure-triage contract rows for the measured failing test methods (B03).

Validates rows and retained evidence only; it never edits a product file, a test expectation or a
fixture. `plan_cause_class` is the plan's hypothesis; `cause_class` is only the measured conclusion.
"""
import hashlib
from pathlib import Path
import re


PLAN_CAUSE_CLASSES = ("schema_double", "attributed_speech_contract", "fixture_city_metadata",
                      "product_filter")
CAUSE_CLASSES = ("test_fixture_double", "unresolved")
CAUSE_BASES = ("measured_by_double_swap", "not_established")
EVIDENCE_STATUSES = ("CONFIRMED_BY_DIAGNOSTIC", "PREEXISTING_NOT_DOUBLE",
                     "REPRODUCED_CAUSE_NOT_VERIFIED")
PARENT_OUTCOMES = ("pass", "same_signature_fail", "different_signature_fail")
OWNER_TASKS = ("W02", "W03", "W04", "W05")
KNOWN_REFS = ("§16.7", "§18.6", "S12", "S15", "A17", "ANL 01", "ANL 02", "BIL 01", "BIL 02")
REQUIRED_FIELDS = (
    "method_id", "assertion_id", "plan_cause_class", "cause_class", "cause_class_basis",
    "evidence_status", "diagnostic", "approved_behavior", "approved_behavior_refs", "owner_task",
    "parent_outcome", "parent_signature_note", "double_change_sufficient", "assertion_error",
    "assertion_trace_sha256", "expectation_changed", "before_evidence",
)
EVIDENCE_FIELDS = ("source_sha", "command", "run_json", "run_json_sha256", "output_log_sha256",
                   "isolated", "runtime_sha", "diagnostic_artifacts")
SHA1 = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
FRAME = re.compile(r'File "[^"]*[\\/](test_[a-z0-9_]+\.py)", line (\d+), in ')


def text_ok(value):
    return isinstance(value, str) and bool(value.strip())


def event_text(event):
    detail = event["detail"]
    return detail["traceback"] if isinstance(detail, dict) else detail


def derive_assertion(event):
    """(test file, line, last traceback line, sha256 of the full trace) for one failing harness event."""
    text = event_text(event)
    frames = FRAME.findall(text)
    file_name, line = frames[-1] if frames else ("", "0")
    last = [item.strip() for item in text.splitlines() if item.strip()][-1]
    return file_name, line, last, hashlib.sha256(text.encode("utf-8")).hexdigest()


GENERATED_INN_NAME = re.compile(r"\b[^\W\d_]+ Hanı\b")


def failure_signature(row):
    """Last traceback line of every failing event, used to compare two runs of one method.

    The D4 fixture generates a random inn name per run (Nuri, Tamsin and Lidda in three runs), so
    '<Name> Hanı' is masked; every other character must match.
    """
    return [GENERATED_INN_NAME.sub("<INN> Hanı",
                                   [item.strip() for item in event_text(event).splitlines() if item.strip()][-1])[:120]
            for event in row["events"] if event["outcome"] in ("failure", "error")]


def validate_failure_contract(case):
    """Return every reason this row is not an acceptable triage record (empty list = acceptable)."""
    if not isinstance(case, dict):
        return ["row must be a mapping"]
    errors = [f"missing field: {name}" for name in REQUIRED_FIELDS if name not in case]
    if errors:
        return errors
    if case["plan_cause_class"] not in PLAN_CAUSE_CLASSES:
        errors.append(f"plan_cause_class must be one of {PLAN_CAUSE_CLASSES}")
    if case["cause_class"] not in CAUSE_CLASSES:
        errors.append(f"cause_class must be one of {CAUSE_CLASSES}")
    if case["cause_class_basis"] not in CAUSE_BASES:
        errors.append(f"cause_class_basis must be one of {CAUSE_BASES}")
    if case["evidence_status"] not in EVIDENCE_STATUSES:
        errors.append(f"evidence_status must be one of {EVIDENCE_STATUSES}")
    if case["owner_task"] not in OWNER_TASKS:
        errors.append(f"owner_task must be one of {OWNER_TASKS}")
    if case["parent_outcome"] not in PARENT_OUTCOMES:
        errors.append(f"parent_outcome must be one of {PARENT_OUTCOMES}")
    for name in ("method_id", "assertion_id", "diagnostic", "assertion_error"):
        if not text_ok(case[name]):
            errors.append(f"{name} must be a nonempty string")
    if not isinstance(case["parent_signature_note"], str):
        errors.append("parent_signature_note must be a string")
    refs = case["approved_behavior_refs"]
    behavior = case["approved_behavior"]
    if not text_ok(behavior) or "Design Rev2" not in behavior:
        errors.append("approved_behavior must be nonempty and cite Design Rev2")
    if not isinstance(refs, list) or not refs or any(ref not in KNOWN_REFS for ref in refs):
        errors.append(f"approved_behavior_refs must be a nonempty list drawn from {KNOWN_REFS}")
    elif text_ok(behavior) and any(ref not in behavior for ref in refs):
        errors.append("approved_behavior must mention every approved_behavior_refs entry")
    if case["expectation_changed"] is not False:
        errors.append("expectation_changed must be false: a test expectation is never edited to get green")
    if not (isinstance(case["assertion_trace_sha256"], str) and SHA256.fullmatch(case["assertion_trace_sha256"])):
        errors.append("assertion_trace_sha256 must be a sha256 digest")
    evidence = case["before_evidence"]
    if not isinstance(evidence, dict):
        errors.append("before_evidence must be a mapping")
        return errors
    missing = [f"before_evidence is missing {name}" for name in EVIDENCE_FIELDS if name not in evidence]
    if missing:
        return errors + missing
    if not (isinstance(evidence["source_sha"], str) and SHA1.fullmatch(evidence["source_sha"])):
        errors.append("before_evidence.source_sha must be a 40-hex commit")
    for name in ("run_json_sha256", "output_log_sha256"):
        if not (isinstance(evidence[name], str) and SHA256.fullmatch(evidence[name])):
            errors.append(f"before_evidence.{name} must be a sha256 digest")
    if not text_ok(evidence["command"]):
        errors.append("before_evidence.command must be a nonempty string")
    if evidence["isolated"] is not True:
        errors.append("before_evidence.isolated must be true: evidence comes from an isolated run")
    artifacts = evidence["diagnostic_artifacts"]
    if not isinstance(artifacts, list) or not all(text_ok(item) for item in artifacts):
        errors.append("before_evidence.diagnostic_artifacts must be a list of paths")
        return errors
    errors.extend(consistency_errors(case, bool(artifacts)))
    return errors


def consistency_errors(case, has_artifacts):
    """A double cause may only be claimed with a measured swap; an unresolved row may not claim one."""
    errors = []
    status, cause = case["evidence_status"], case["cause_class"]
    claims_double = cause == "test_fixture_double"
    if claims_double:
        if status != "CONFIRMED_BY_DIAGNOSTIC":
            errors.append("a test_fixture_double cause requires evidence_status CONFIRMED_BY_DIAGNOSTIC")
        if case["cause_class_basis"] != "measured_by_double_swap":
            errors.append("a test_fixture_double cause requires cause_class_basis measured_by_double_swap")
        if case["double_change_sufficient"] is not True:
            errors.append("a test_fixture_double cause requires double_change_sufficient true")
        if not has_artifacts:
            errors.append("a test_fixture_double cause requires retained diagnostic_artifacts")
    else:
        if status == "CONFIRMED_BY_DIAGNOSTIC":
            errors.append("CONFIRMED_BY_DIAGNOSTIC requires the test_fixture_double cause")
        if case["cause_class_basis"] != "not_established":
            errors.append("an unresolved cause must have cause_class_basis not_established")
        if case["double_change_sufficient"] is not False:
            errors.append("an unresolved cause must have double_change_sufficient false")
    if status == "PREEXISTING_NOT_DOUBLE":
        if case["parent_outcome"] == "pass":
            errors.append("PREEXISTING_NOT_DOUBLE requires a method that also failed at the parent commit")
        if not has_artifacts:
            errors.append("PREEXISTING_NOT_DOUBLE requires retained diagnostic_artifacts")
    return errors


def triage_summary(rows):
    """Never report a plan classification as confirmed unless every row is confirmed."""
    statuses = {row["evidence_status"] for row in rows}
    if not statuses:
        return "PLAN_CLASS_NOT_CONFIRMED"
    if statuses == {"CONFIRMED_BY_DIAGNOSTIC"}:
        return "PLAN_CLASS_CONFIRMED"
    if "CONFIRMED_BY_DIAGNOSTIC" in statuses:
        return "PLAN_CLASS_PARTIALLY_CONFIRMED"
    return "PLAN_CLASS_NOT_CONFIRMED"


def validate_history(previous, current):
    """Classification history is append-only: the previous entries must stay a prefix, unchanged."""
    if len(current) < len(previous):
        return ["history lost entries"]
    return [f"history entry {index + 1} was rewritten"
            for index, entry in enumerate(previous) if current[index] != entry]


def verify_retained_files(contract, acceptance_dir):
    """Every retained evidence file must exist with the digest the contract recorded."""
    errors = []
    for relative, digest in contract.get("evidence_files", {}).items():
        path = Path(acceptance_dir) / relative
        if not path.is_file():
            errors.append(f"missing retained file: {relative}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(f"digest mismatch: {relative}")
    return errors
