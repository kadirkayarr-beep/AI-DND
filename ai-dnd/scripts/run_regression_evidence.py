"""Archive NEW unittest/function regression runs; never certify historical runs."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import shlex
import subprocess
import sys
import traceback
import unittest
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = ROOT / "docs/evidence/suite-runs"


def now():
    return datetime.now(timezone.utc).isoformat()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def source_snapshot(archive):
    """Fingerprint tracked + nonignored untracked content, not just git status.

    Generated suite evidence is excluded to avoid self-referential hashes.
    Only hashes/paths are retained, never file contents or environment values.
    """
    repo = Path(git("rev-parse", "--show-toplevel").decode().strip())
    def repo_git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args])

    excluded = {DEFAULT_ARCHIVE.resolve(), Path(archive).resolve()}
    paths = sorted(set(repo_git("ls-files", "-z", "--cached", "--others",
                           "--exclude-standard").decode().split("\0")) - {""})
    files = []
    for relative in paths:
        path = repo / relative
        if any(path == directory or directory in path.parents for directory in excluded):
            continue
        if path.is_symlink():
            content = str(path.readlink()).encode()
            kind = "symlink"
        elif path.is_file():
            content = path.read_bytes()
            kind = "file"
        else:
            content = b""
            kind = "missing"
        files.append({"path": relative, "kind": kind,
                      "mode": oct(path.lstat().st_mode) if path.exists() or path.is_symlink() else None,
                      "sha256": hashlib.sha256(content).hexdigest()})
    status = repo_git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    index_diff = repo_git("diff", "--cached", "--binary", "--", ":(top)**",
                     *(f":(top,exclude){p.relative_to(repo)}" for p in excluded if p.is_relative_to(repo)))
    index_sha = hashlib.sha256(index_diff).hexdigest()
    return {
        "revision": repo_git("rev-parse", "HEAD").decode().strip(),
        "dirty": bool(status),
        "git_status_sha256": hashlib.sha256(status).hexdigest(),
        "working_tree_sha256": hashlib.sha256(
            json.dumps({"files": files, "index_diff_sha256": index_sha},
                       sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "index_diff_sha256": index_sha,
        "files": files,
        "excluded_evidence_directories": sorted(str(p.relative_to(repo)) if p.is_relative_to(repo)
                                                else str(p) for p in excluded),
        "scope": "All tracked and nonignored untracked files; ignored files/environment excluded.",
    }


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


class FunctionTest(unittest.FunctionTestCase):
    def id(self):
        return f"{self._testFunc.__module__}.{self._testFunc.__qualname__}"


def select_tests(selectors, discoveries, pattern):
    loader = unittest.TestLoader()
    tests = []
    # Python 3.13 unittest discovery rejects namespace-only start directories.
    # Import from the project root so api/tests keeps canonical qualified IDs.
    expanded = list(selectors)
    for directory in discoveries:
        start = Path(directory).resolve()
        start.relative_to(ROOT)
        if not start.is_dir():
            raise ValueError(f"Discovery directory does not exist: {start}")
        expanded.extend(".".join(path.relative_to(ROOT).with_suffix("").parts)
                        for path in sorted(start.rglob(pattern)) if path.is_file() and path.suffix == ".py")
    for selector in expanded:
        # Existing test_regression.py uses plain functions, not TestCase.
        try:
            module = importlib.import_module(selector)
        except ModuleNotFoundError as exc:
            if exc.name != selector and not selector.startswith(exc.name + "."):
                raise
            module = None
        function = None
        if module is None and "." in selector:
            module_name, name = selector.rsplit(".", 1)
            try:
                candidate = getattr(importlib.import_module(module_name), name, None)
                if inspect.isfunction(candidate):
                    function = candidate
            except ModuleNotFoundError as exc:
                if exc.name != module_name and not module_name.startswith(exc.name + "."):
                    raise
        suite = (unittest.TestSuite([FunctionTest(function)]) if function is not None else
                 loader.loadTestsFromName(selector) if module is None else loader.loadTestsFromModule(module))
        tests.extend(flatten(suite))
        if module is not None:
            tests.extend(FunctionTest(function) for name, function in inspect.getmembers(module, inspect.isfunction)
                         if name.startswith("test_") and function.__module__ == module.__name__)
    if loader.errors:
        raise ValueError("Test selection failed:\n" + "\n".join(loader.errors))
    counts = Counter(test.id() for test in tests)
    unique = {}
    for test in tests:
        unique.setdefault(test.id(), test)
    if not unique:
        raise ValueError("Selection contains no tests")
    return list(unique.values()), {
        "selected_occurrences": len(tests), "unique_selected": len(unique),
        "duplicates_removed": len(tests) - len(unique),
        "duplicate_ids": {key: count for key, count in counts.items() if count > 1},
    }


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, evidence, persist, **kwargs):
        super().__init__(*args, **kwargs)
        self.evidence, self.persist = evidence, persist
        self.records = {}

    def startTest(self, test):
        super().startTest(test)
        record = {"id": test.id(), "started_at": now(), "ended_at": None,
                  "outcome": "running", "events": []}
        self.records[test.id()] = record
        self.evidence["executed_test_ids"].append(test.id())
        self.evidence["per_test"].append(record)
        self.persist()

    def record(self, test, outcome, detail=None):
        event = {"id": test.id(), "outcome": outcome, "detail": detail}
        record = self.records.get(getattr(test, "test_case", test).id())
        if record is None:
            # setUpClass/setUpModule failures are not executed test methods.
            self.evidence["suite_events"].append(event)
        else:
            record["events"].append(event)
            if record["outcome"] not in {"failure", "error"}:
                record["outcome"] = outcome
        self.persist()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, "pass")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, "failure", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, "error", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.record(test, "skip", reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.record(test, "expected_failure", self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.record(test, "unexpected_success")

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.record(test, "failure" if issubclass(err[0], test.failureException) else "error",
                        {"subtest": subtest.id(), "traceback": self._exc_info_to_string(err, test)})

    def stopTest(self, test):
        self.records[test.id()]["ended_at"] = now()
        self.persist()
        super().stopTest(test)


class Tee:
    def __init__(self, terminal, log):
        self.terminal, self.log = terminal, log

    def write(self, text):
        self.terminal.write(text)
        self.log.write(text)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selectors", nargs="*", help="Importable unittest modules/classes/methods or function modules")
    parser.add_argument("--discover", action="append", default=[], help="Directory (relative to cwd)")
    parser.add_argument("--pattern", default="test_*.py")
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args(argv)
    selectors = args.selectors or ([] if args.discover else ["api.tests.test_bounded_encounter", "test_regression"])
    directory = args.archive_root.resolve() / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, *sys.argv] if argv is None else [sys.executable, str(Path(__file__).resolve()), *argv]
    evidence = {
        "schema_version": 1, "evidence_kind": "suite_run", "run_label": "NEW RUN",
        "historical_certification": False, "started_at": now(), "ended_at": None,
        "status": "running", "exit_status": None,
        "command": {"argv": command, "shell": shlex.join(command), "cwd": str(Path.cwd())},
        "selection": {"selectors": selectors, "discover": args.discover, "pattern": args.pattern},
        "selected_test_ids": [], "executed_test_ids": [], "per_test": [], "suite_events": [],
        "python_version": sys.version,
    }
    path = directory / "run.json"

    def persist():
        temporary = path.with_suffix(".json.pending")
        temporary.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    persist()
    result = None
    code = 2
    original_stdout, original_stderr = sys.stdout, sys.stderr
    try:
        with (directory / "output.log").open("w", encoding="utf-8") as log:
            sys.stdout, sys.stderr = Tee(original_stdout, log), Tee(original_stderr, log)
            try:
                evidence["source_start"] = source_snapshot(args.archive_root)
                tests, evidence["deduplication"] = select_tests(selectors, args.discover, args.pattern)
                evidence["selected_test_ids"] = [test.id() for test in tests]
                persist()
                def make_result(*a, **kw):
                    nonlocal result
                    result = EvidenceResult(*a, evidence=evidence, persist=persist, **kw)
                    return result

                runner = unittest.TextTestRunner(
                    verbosity=2, stream=sys.stderr,
                    resultclass=make_result)
                result = runner.run(unittest.TestSuite(tests))
                code = 0 if result.wasSuccessful() else 1
                evidence["status"] = "completed"
            except BaseException as exc:
                code = 130 if isinstance(exc, KeyboardInterrupt) else 2
                evidence["status"] = "interrupted" if code == 130 else "runner_error"
                evidence["runner_error"] = traceback.format_exc()
                traceback.print_exc()
            finally:
                try:
                    evidence["source_end"] = source_snapshot(args.archive_root)
                    evidence["source_changed_during_run"] = (
                        evidence.get("source_start", {}).get("working_tree_sha256") !=
                        evidence["source_end"]["working_tree_sha256"] or
                        evidence.get("source_start", {}).get("revision") != evidence["source_end"]["revision"])
                except Exception:
                    evidence["source_end_error"] = traceback.format_exc()
                    code = 2
                    evidence["status"] = "runner_error"
    finally:
        sys.stdout, sys.stderr = original_stdout, original_stderr
        evidence["ended_at"], evidence["exit_status"] = now(), code
        for record in evidence["per_test"]:
            if record["outcome"] == "running":
                record["outcome"] = "interrupted" if code == 130 else "incomplete"
        evidence["unexecuted_test_ids"] = sorted(set(evidence["selected_test_ids"]) - set(evidence["executed_test_ids"]))
        evidence["aggregate"] = {
            "tests_run": result.testsRun if result is not None else len(evidence["executed_test_ids"]),
            "per_test_outcomes": dict(Counter(record["outcome"] for record in evidence["per_test"])),
            "failures": len(result.failures) if result is not None else None,
            "errors": len(result.errors) if result is not None else None,
            "skips": len(result.skipped) if result is not None else None,
            "expected_failures": len(result.expectedFailures) if result is not None else None,
            "unexpected_successes": len(result.unexpectedSuccesses) if result is not None else None,
        }
        evidence["output_log_sha256"] = hashlib.sha256((directory / "output.log").read_bytes()).hexdigest()
        persist()
    print(f"NEW suite evidence: {path}")
    return code


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())