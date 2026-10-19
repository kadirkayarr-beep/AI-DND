"""Bounded development checks; never decide gameplay or contact a live model."""
import argparse
import fnmatch
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

import run_regression_evidence as evidence
from development_archive import Archive, DEFAULT_ARCHIVE
import development_ownership as ownership


REPO = evidence.ROOT.parent
DEFAULT_CONFIG = Path(__file__).with_name("development_checks.json")
STATUSES = {"PASS", "FAIL", "NOT RUN", "UNVERIFIED"}


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    keys = {"schema_version", "required_paths", "regression_selectors",
            "regression_group_sizes",
            "frontend_package", "frontend_commands", "command_timeout_seconds"}
    if (not isinstance(config, dict) or set(config) != keys
            or type(config["schema_version"]) is not int or config["schema_version"] != 1):
        raise ValueError("Configuration must contain exactly the supported schema_version=1 fields")
    for key in ("required_paths", "regression_selectors"):
        values = config[key]
        if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"{key} must be a nonempty list of nonempty strings")
    if len(config["regression_selectors"]) != len(set(config["regression_selectors"])):
        raise ValueError("regression_selectors must not contain duplicate selectors")
    sizes = config["regression_group_sizes"]
    if (not isinstance(sizes, list) or not sizes
            or any(type(size) is not int or size < 1 for size in sizes)
            or sum(sizes) != len(config["regression_selectors"])):
        raise ValueError("regression_group_sizes must partition every selector exactly once")
    for path in [*config["required_paths"], config["frontend_package"]]:
        if not isinstance(path, str) or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("Project paths must be repository-relative without '..'")
    timeout = config["command_timeout_seconds"]
    if type(timeout) is not int or not 1 <= timeout <= 900:
        raise ValueError("command_timeout_seconds must be an integer in 1..900")
    commands = config["frontend_commands"]
    if not isinstance(commands, list) or not commands:
        raise ValueError("frontend_commands must be a nonempty list")
    names = []
    for command in commands:
        if not isinstance(command, dict) or set(command) != {"name", "argv"}:
            raise ValueError("Each frontend command must contain name and argv")
        if not isinstance(command["name"], str) or not command["name"].strip():
            raise ValueError("Command name must be nonempty")
        argv = command["argv"]
        if not isinstance(argv, list) or not argv or any(
                not isinstance(item, str) or not item.strip() for item in argv):
            raise ValueError("Command argv must be a nonempty string array; no shell commands")
        names.append(command["name"])
    if set(names) != {"frontend_libraries", "frontend_typecheck", "frontend_test",
                      "frontend_browser_ui_mocked_auth", "frontend_build"}:
        raise ValueError("All five established frontend commands are required")
    if len(names) != len(set(names)):
        raise ValueError("Duplicate command names")
    return config


def git(repo, *args):
    return subprocess.check_output(
        ["git", "-c", "core.fsmonitor=false", *args], cwd=repo,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}, stderr=subprocess.PIPE).decode()


def repository_state(repo):
    """Porcelain -z retains filenames verbatim, including staged renames."""
    raw = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries, fields, index = [], raw.split("\0"), 0
    while index < len(fields) and fields[index]:
        entry = fields[index]
        row = {"index": entry[0], "worktree": entry[1], "path": entry[3:]}
        index += 1
        if "R" in entry[:2] or "C" in entry[:2]:
            row["original_path"] = fields[index]
            index += 1
        entries.append(row)
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD") if (
        subprocess.run(["git", "symbolic-ref", "--quiet", "HEAD"], cwd=repo,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0) else None
    return {
        "revision": git(repo, "rev-parse", "HEAD").strip(),
        "branch": branch.strip() if branch else None,
        "detached": branch is None, "clean": not entries, "entries": entries,
        "staged": [row for row in entries if row["index"] not in {" ", "?"}],
        "unstaged": [row for row in entries if row["worktree"] not in {" ", "?"}],
        "untracked": [row for row in entries if row["index"] == "?"],
    }


def check(name, status, detail, required=True, **extra):
    if status not in STATUSES:
        raise ValueError(f"Unknown check status: {status}")
    return {"name": name, "status": status, "required": required, "detail": detail, **extra}


def exit_code(checks):
    # NOT RUN/UNVERIFIED on a required gate is blocking, never implicit PASS.
    return int(any(row["required"] and row["status"] != "PASS" for row in checks))


def protected_path(path):
    if path.startswith("artifacts/ai-dnd-experience/src/") or path.startswith("artifacts/ai-dnd-web/src/"):
        return True
    if not path.startswith("ai-dnd/") or not path.endswith(".py"):
        return False
    return not (path.startswith(("ai-dnd/scripts/", "ai-dnd/api/tests/"))
                or fnmatch.fnmatch(Path(path).name, "test_*.py")
                or path == "ai-dnd/run_tests.py")


def structural_checks(config, state, repo, baseline=None, ci=None):
    ci = ci or {}
    detached_ci = bool(ci.get("GITHUB_RUN_ID") and ci.get("GITHUB_SHA") == state["revision"])
    rows = [
        check("Configuration", "PASS", "Strict schema_version=1 configuration validated"),
        check("HEAD", "PASS", state["revision"]),
        check("Branch", "FAIL" if state["detached"] and not detached_ci else "PASS",
              state["branch"] or ("Detached CI checkout; exact event SHA checked" if detached_ci
                                 else "Detached HEAD outside verified event checkout")),
        check("Evidence ownership", "FAIL" if state.get("ownership_errors") else "PASS",
              {"errors": state.get("ownership_errors", []),
               "exempt_entries": state.get("owned_evidence_entries", []),
               "receipts": state.get("ownership_receipts", [])}),
        check("Working tree", "PASS" if state.get("source_clean", state["clean"]) else "FAIL",
              "Clean source checkout; raw Git status retained; only verified tool-owned evidence exempted"
              if state.get("source_clean", state["clean"]) else
              f"Dirty: {len(state['staged'])} staged, {len(state['unstaged'])} unstaged, "
              f"{len(state['untracked'])} untracked; see repository_state.entries"),
    ]
    if ci:
        rows.append(check("CI event SHA", "PASS" if ci.get("GITHUB_SHA") == state["revision"] else "FAIL",
                          {"event_sha": ci.get("GITHUB_SHA"), "checkout_sha": state["revision"]}))
    missing = [path for path in config["required_paths"] if not (repo / path).exists()]
    rows.append(check("Project structure", "FAIL" if missing else "PASS",
                      {"missing": missing}))
    # Reuse, rather than approximate, the existing source-identity function.
    evidence_paths = ["ai-dnd/scripts/run_regression_evidence.py",
                      "ai-dnd/docs/regression-evidence.md", "ai-dnd/docs/evidence"]
    rows.append(check("Evidence infrastructure", "PASS" if callable(evidence.source_snapshot)
                      and all((repo / path).exists() for path in evidence_paths) else "FAIL",
                      "Existing regression runner, source_snapshot and timestamp/UUID archives"))
    owners = ["ai-dnd/game.py", "ai-dnd/api/ollama_adapter.py",
              "ai-dnd/api/tests/test_model_isolation.py", "artifacts/ai-dnd-experience/src"]
    rows.append(check("Architecture structure", "PASS" if all((repo / p).exists() for p in owners) else "FAIL",
                      "Structural presence only: Python backend, presentation client, offline model guards; "
                      "not a semantic proof of gameplay authority"))
    changed = {row["path"] for row in state["entries"]}
    changed.update(row["original_path"] for row in state["entries"] if "original_path" in row)
    if baseline is not None:
        # Name-only review includes committed changes as well as working-tree changes.
        changed.update(filter(None, git(repo, "diff", "--name-only", "-z", baseline, "--").split("\0")))
    forbidden = sorted(path for path in changed if protected_path(path))
    rows.append(check("Infrastructure scope", "FAIL" if forbidden else "PASS",
                      {"protected_changes": forbidden, "baseline": baseline or "HEAD + untracked",
                       "scope": "Only infrastructure work is approved for this package"}))
    package = json.loads((repo / config["frontend_package"]).read_text(encoding="utf-8"))
    scripts = package.get("scripts", {})
    absent = [name for name in ("typecheck", "test", "build") if not scripts.get(name)]
    missing_tools = [tool for tool in ("git", "pnpm") if not shutil.which(tool)]
    rows.append(check("Verification commands", "FAIL" if absent or missing_tools else "PASS",
                      {"missing_frontend_scripts": absent, "missing_tools": missing_tools,
                       "regression_selectors": config["regression_selectors"]}))
    return rows


def run_command(name, argv, repo, timeout, log):
    row = check(name, "UNVERIFIED", "Command not completed", argv=argv, cwd=str(repo),
                started_at=evidence.now(), ended_at=None, exit_status=None)
    print(f"\n$ {evidence.shlex.join(argv)}", flush=True)
    log.flush()
    # Child tools emit their logs into the same retained combined output.log.
    # Vite's existing config requires PORT/BASE_PATH even for an offline build.
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "NODE_ENV": "production",
           "PORT": "5099", "BASE_PATH": "/"}
    try:
        process = subprocess.Popen(argv, cwd=repo, env=env, stdout=log, stderr=log,
                                   start_new_session=True)
        try:
            result = process.wait(timeout=timeout)
        except BaseException:
            # Stop descendants too: an orphaned test/build must not keep changing
            # logs or source after this command's evidence has been finalized.
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False,
                )
                if process.poll() is None:
                    process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()
            raise
        row.update(status="PASS" if result == 0 else "FAIL",
                   exit_status=result, detail="See output.log")
    except subprocess.TimeoutExpired:
        row.update(status="FAIL", detail=f"Command exceeded {timeout} seconds", timed_out=True)
    except OSError as exc:
        row.update(status="FAIL", detail=str(exc))
    row["ended_at"] = evidence.now()
    return row


def validate_suite(row, log, offset, archive_root):
    """A zero child exit alone does not certify execution or retained evidence."""
    log.flush()
    with Path(log.name).open(encoding="utf-8") as stream:
        stream.seek(offset)
        paths = [line.removeprefix("NEW suite evidence: ").strip()
                 for line in stream if line.startswith("NEW suite evidence: ")]
    if len(paths) != 1:
        raise ValueError("Regression command did not report exactly one retained suite record")
    path = Path(paths[0]).resolve()
    if not path.is_relative_to(archive_root.resolve()) or path.name != "run.json":
        raise ValueError("Regression evidence must be in this run's approved archive root")
    record = json.loads(path.read_text(encoding="utf-8"))
    aggregate = record.get("aggregate", {})
    passed = (
        record.get("evidence_kind") == "suite_run" and record.get("status") == "completed"
        and record.get("exit_status") == 0 and record.get("selected_test_ids")
        and record.get("selected_test_ids") == record.get("executed_test_ids")
        and record.get("unexecuted_test_ids") == []
        and record.get("source_changed_during_run") is False
        and all(aggregate.get(key) == 0 for key in
                ("failures", "errors", "skips", "expected_failures", "unexpected_successes"))
        and aggregate.get("per_test_outcomes") == {"pass": len(record["selected_test_ids"])}
        and aggregate.get("tests_run") == len(record["selected_test_ids"])
        and record.get("output_log_sha256") == evidence.hashlib.sha256(
            path.with_name("output.log").read_bytes()).hexdigest()
    )
    row.update(status="PASS" if row["status"] == "PASS" and passed else "FAIL",
               suite_evidence=str(path),
               suite_evidence_relative=str(path.relative_to(archive_root.resolve())),
               detail="Executed IDs/counts, outcomes, stable source and retained log hash checked"
               if passed else "Retained regression evidence is incomplete or non-passing")


def main(kind, argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--baseline", help="Optional reviewed Git revision for committed scope comparison")
    parser.add_argument("--static-only", action="store_true",
                        help="Do not execute tests/build; required Final Gate commands remain NOT RUN")
    args = parser.parse_args(argv)
    command = [sys.executable, *sys.argv] if argv is None else [
        sys.executable, str(Path(__file__).with_name(f"{kind}.py")), *argv]
    # Only explicitly named non-secret GitHub provenance fields are retained.
    ci = {key: os.environ[key] for key in (
        "GITHUB_SHA", "GITHUB_WORKFLOW", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
        "GITHUB_EVENT_NAME", "GITHUB_JOB") if os.environ.get(key)}
    # Retain raw Git state; exempt only locally receipted, byte-unchanged outputs.
    preflight_error = None
    try:
        state = ownership.classify(REPO, repository_state(REPO))
        source_start = evidence.source_snapshot(args.archive_root)
    except Exception as exc:
        preflight_error = str(exc)
    archive = Archive(args.archive_root, kind, command)
    archive.data["ci_identity"] = ci
    archive.data["policy"] = {"static_only": args.static_only, "baseline": args.baseline,
                              "clean_tree_required": True, "live_acceptance_required": False}
    code = 2
    terminal_out, terminal_err = sys.stdout, sys.stderr
    try:
        with (archive.directory / "output.log").open("w", encoding="utf-8") as log:
            sys.stdout = evidence.Tee(terminal_out, log)
            sys.stderr = evidence.Tee(terminal_err, log)
            try:
                config = load_config(args.config)
                if preflight_error is not None:
                    raise ValueError(f"Repository/source preflight failed: {preflight_error}")
                archive.data["source_start"] = source_start
                archive.data["repository_state"] = state
                rows = structural_checks(config, state, REPO, args.baseline, ci)
                archive.data["checks"] = rows
                archive.persist()
                commands = []
                start = 0
                for index, size in enumerate(config["regression_group_sizes"], 1):
                    selectors = config["regression_selectors"][start:start + size]
                    start += size
                    commands.append((("Python regression" if index == 1
                                      else f"Python regression group {index}"), [
                        sys.executable, str(evidence.ROOT / "scripts/run_regression_evidence.py"),
                        "--archive-root", str(args.archive_root.resolve()), *selectors]))
                commands += [(item["name"], item["argv"]) for item in config["frontend_commands"]]
                execute = kind == "final_gate" and not args.static_only
                for name, child_argv in commands:
                    if execute:
                        # Retain each started command before it runs: abrupt termination
                        # leaves an identifiable incomplete attempt, never fabricated PASS.
                        rows.append(check(name, "UNVERIFIED", "Command starting",
                                          argv=child_argv, started_at=evidence.now(),
                                          ended_at=None, exit_status=None))
                        archive.persist()
                        log.flush()
                        offset = log.tell()
                        rows[-1] = run_command(name, child_argv, REPO,
                                               config["command_timeout_seconds"], log)
                        if name.startswith("Python regression"):
                            try:
                                validate_suite(rows[-1], log, offset, args.archive_root)
                            except (OSError, ValueError, KeyError) as exc:
                                rows[-1].update(status="FAIL", detail=str(exc))
                    else:
                        rows.append(check(name, "NOT RUN", "Explicit bounded/static mode",
                                          required=kind == "final_gate", argv=child_argv))
                    archive.persist()
                for name in ("Live HTTP", "Live Qwen"):
                    rows.append(check(name, "NOT RUN", "Not performed by local tooling", required=False))
                rows.append(check("GitHub Actions completion", "UNVERIFIED" if ci else "NOT RUN",
                                  "Running job identity recorded; remote final status is not certified"
                                  if ci else "No actual remote workflow run performed", required=False))
                archive.data["source_end"] = evidence.source_snapshot(args.archive_root)
                end_state = ownership.classify(
                    REPO, repository_state(REPO), ownership.generated_files(archive))
                archive.data["repository_state_end"] = end_state
                rows.append(check("Working tree after execution",
                                  "PASS" if end_state["source_clean"] else "FAIL",
                                  {"source_entries": end_state["source_entries"],
                                   "ownership_errors": end_state["ownership_errors"]}))
                first, last = archive.data["source_start"], archive.data["source_end"]
                changed = (first["revision"] != last["revision"] or
                           first["working_tree_sha256"] != last["working_tree_sha256"])
                archive.data["source_changed_during_run"] = changed
                rows.append(check("Stable verifier source", "FAIL" if changed else "PASS",
                                  "Generated evidence excluded using existing source_snapshot"))
                code = exit_code(rows)
            except KeyboardInterrupt:
                code = 130
                archive.data["checks"].append(check("Interruption", "FAIL", "Interrupted; incomplete checks"))
            except Exception as exc:
                code = 2
                archive.data["checks"].append(check("Configuration/tooling error", "FAIL", str(exc)))
            title = "AI-DND FINAL GATE" if kind == "final_gate" else "AI-DND HEALTH CHECK"
            result = ("GO" if code == 0 else "NO-GO") if kind == "final_gate" else (
                "HEALTHY" if code == 0 else "UNHEALTHY")
            archive.data["result"] = result
            print(f"\n{title}", file=log)
            for row in archive.data["checks"]:
                print(f"{row['name']:28} {row['status']:10} {row['detail']}", file=log)
            print(f"RESULT: {result}", file=log)
    finally:
        sys.stdout, sys.stderr = terminal_out, terminal_err
        archive.finish(code)
        try:
            ownership.seal(archive)
        except (OSError, ValueError) as exc:
            code = 2
            archive.data["checks"].append(check("Evidence ownership finalization", "FAIL", str(exc)))
            archive.data["result"] = "NO-GO" if kind == "final_gate" else "UNHEALTHY"
            with (archive.directory / "output.log").open("a", encoding="utf-8") as log:
                print(f"Evidence ownership finalization FAIL: {exc}", file=log)
                print(f"RESULT: {archive.data['result']}", file=log)
            archive.finish(code)
    print(f"\n{title}")
    for row in archive.data["checks"]:
        print(f"{row['name']:28} {row['status']:10} {row['detail']}")
    print(f"RESULT: {archive.data['result']}")
    print(f"NEW development evidence: {archive.path}")
    return code