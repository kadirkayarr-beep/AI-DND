"""Local evidence ownership bookkeeping, not test or server certification."""
import json
from pathlib import Path
import re

import run_regression_evidence as evidence


PRODUCER = "ai-dnd-development-checks/v1"
RUN_NAME = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{32}")


def receipt_root():
    # Worktree-specific Git metadata survives separate CLI processes without
    # changing tracked files, ignore rules, the index, or Git history.
    return Path(evidence.git(
        "rev-parse", "--path-format=absolute", "--git-path",
        "ai-dnd-development-ownership").decode().strip())


def digest(path):
    if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"Evidence must be a regular nonsymlink file: {path}")
    return evidence.hashlib.sha256(path.read_bytes()).hexdigest()


def generated_files(archive):
    """Only this exclusively created parent and its new linked suite."""
    files = [archive.path, archive.path.with_name("output.log")]
    for row in archive.data["checks"]:
        if row.get("suite_evidence"):
            path = Path(row["suite_evidence"])
            if (path.name != "run.json" or path.parent.parent != archive.directory.parent
                    or not RUN_NAME.fullmatch(path.parent.name)
                    or path.parent in archive.preexisting_directories):
                raise ValueError("Cannot claim ownership of pre-existing or foreign suite evidence")
            files.extend((path, path.with_name("output.log")))
    return files


def seal(archive):
    repo = evidence.ROOT.parent.resolve()
    if not archive.directory.is_relative_to(repo):
        return  # CI's external archive does not appear in checkout status.
    revision = archive.data.get("source_start", {}).get("revision")
    if not revision:
        return  # No source identity: leave this attempt unexempted, fail closed.
    files = generated_files(archive)
    receipt = {
        "schema_version": 1, "producer": PRODUCER, "repository": str(repo),
        "revision": revision, "parent_record": str(archive.path.relative_to(repo)),
        "files": {str(p.relative_to(repo)): digest(p) for p in files},
    }
    directory = receipt_root()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (archive.directory.name + ".json")
    # Exclusive creation; never replace a historical ownership receipt.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, sort_keys=True)
        stream.write("\n")


def verified_files(repo):
    """Verify the entire receipt before exempting any of its paths."""
    repo = repo.resolve()
    approved = repo / "ai-dnd/docs/evidence/development-runs"
    owned, errors, receipts = set(), [], []
    for receipt_path in sorted(receipt_root().glob("*.json")):
        try:
            digest(receipt_path)  # Reject receipt symlinks too.
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if (receipt.get("schema_version") != 1 or receipt.get("producer") != PRODUCER
                    or receipt.get("repository") != str(repo)):
                raise ValueError("Foreign or unsupported ownership receipt")
            parent = repo / receipt["parent_record"]
            if (parent.name != "run.json" or not RUN_NAME.fullmatch(parent.parent.name)
                    or receipt_path.stem != parent.parent.name
                    or ".." in Path(receipt["parent_record"]).parts
                    or Path(receipt["parent_record"]).is_absolute()
                    or not parent.is_relative_to(approved)):
                raise ValueError("Ownership receipt/run identity mismatch")
            digest(parent)
            expected = {parent, parent.with_name("output.log")}
            record = json.loads(parent.read_text(encoding="utf-8"))
            if (record.get("evidence_kind") not in {"project_health_check", "final_gate"}
                    or record.get("status") not in {"completed", "runner_error", "interrupted"}
                    or record.get("run_label") != "NEW RUN"
                    or record.get("historical_certification") is not False
                    or record.get("source_start", {}).get("revision") != receipt["revision"]):
                raise ValueError("Invalid parent provenance")
            for row in record["checks"]:
                if row.get("suite_evidence"):
                    child = Path(row["suite_evidence"])
                    if (child.parent.parent != parent.parent.parent or child.name != "run.json"
                            or not RUN_NAME.fullmatch(child.parent.name)):
                        raise ValueError("Foreign linked suite")
                    expected.update((child, child.with_name("output.log")))
            actual = {repo / p for p in receipt["files"]}
            if actual != expected:
                raise ValueError("Receipt must cover exactly the parent and linked suite pairs")
            for relative, sha in receipt["files"].items():
                path = repo / relative
                if (".." in Path(relative).parts or Path(relative).is_absolute()
                        or not path.is_relative_to(approved) or digest(path) != sha):
                    raise ValueError(f"Missing, modified or out-of-scope evidence: {relative}")
            owned.update(Path(relative).as_posix() for relative in receipt["files"])
            receipts.append(str(receipt_path))
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append({"receipt": str(receipt_path), "error": str(exc)})
    return owned, errors, receipts


def classify(repo, state, current_files=()):
    owned, errors, receipts = verified_files(repo)
    # The current run has not been sealed yet. Its exclusively created outputs
    # are allowed only for its own end-state check, never for a later invocation.
    owned.update(p.relative_to(repo).as_posix() for p in current_files if p.is_relative_to(repo))
    exempt = [r for r in state["entries"]
              if r["index"] == r["worktree"] == "?" and r["path"] in owned]
    blocking = [r for r in state["entries"] if r not in exempt]
    return {
        **state, "source_clean": not blocking and not errors,
        "source_entries": blocking, "owned_evidence_entries": exempt,
        "ownership_errors": errors, "ownership_receipts": receipts,
    }