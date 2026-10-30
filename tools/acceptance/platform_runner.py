"""Platform-aware gate runner (B06): runs one argv as its own process tree and records an EvidenceRecord.

Never runs a shell string. A timeout, or the end of the gate, closes only the tree this runner started
(a Windows job object, or a POSIX process group); processes it did not start are never touched. It never
runs the game, a model or a server on its own: the caller chooses the command.
"""
import ctypes
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import tempfile

import source_identity


REPO = Path(__file__).resolve().parents[2]
SUPPORTED = ("nt", "posix")
KILL_WAIT_S = 10.0


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class WindowsJob:
    """Job object with kill-on-close: every descendant started inside it dies with it."""

    KILL_ON_JOB_CLOSE = 0x2000
    EXTENDED_LIMIT_INFO = 9
    SET_QUOTA_TERMINATE = 0x0100 | 0x0001

    def __init__(self, pid):
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel = kernel
        for name, args, result in (
                ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], ctypes.c_void_p),
                ("SetInformationJobObject", [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
                ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], ctypes.c_void_p),
                ("AssignProcessToJobObject", [ctypes.c_void_p, ctypes.c_void_p], wintypes.BOOL),
                ("TerminateJobObject", [ctypes.c_void_p, wintypes.UINT], wintypes.BOOL),
                ("CloseHandle", [ctypes.c_void_p], wintypes.BOOL)):
            function = getattr(kernel, name)
            function.argtypes, function.restype = args, result

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        self.job = kernel.CreateJobObjectW(None, None)
        if not self.job:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        info = Extended()
        info.BasicLimitInformation.LimitFlags = self.KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self.job, self.EXTENDED_LIMIT_INFO, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
        process = kernel.OpenProcess(self.SET_QUOTA_TERMINATE, False, pid)
        if not process:
            self.close()
            raise OSError(ctypes.get_last_error(), "OpenProcess failed")
        try:
            if not kernel.AssignProcessToJobObject(self.job, process):
                raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        except OSError:
            self.close()
            raise
        finally:
            kernel.CloseHandle(process)

    def terminate(self):
        self.kernel.TerminateJobObject(self.job, 1)

    def close(self):
        if self.job:
            self.kernel.CloseHandle(self.job)
            self.job = None


class PosixGroup:
    """The child leads its own session, so its process group holds exactly the tree it started."""

    def __init__(self, pid):
        self.pid = pid

    def terminate(self):
        # Kill even if the leader has already exited: descendants may still live.
        try:
            os.killpg(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def close(self):
        self.terminate()


def spawn(command, cwd, env, output):
    options = {"cwd": str(cwd), "env": env, "stdin": subprocess.DEVNULL, "stdout": output,
               "stderr": subprocess.STDOUT, "shell": False}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        options["start_new_session"] = True
    child = subprocess.Popen(command, **options)
    try:
        tree = WindowsJob(child.pid) if os.name == "nt" else PosixGroup(child.pid)
    except OSError:
        child.kill()
        child.wait()
        raise
    return child, tree


def check_command(command):
    if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
        raise TypeError("command must be a list of strings; shell strings are never executed")
    if not command or not command[0].strip():
        raise ValueError("command needs an executable")


def run_gate(command, cwd, timeout_s, env, *, column="unit", test_id=None, platform_name=None):
    """Run one argv in `cwd` with exactly `env`; return an EvidenceRecord (see evidence.validate_record)."""
    check_command(command)
    cwd = Path(cwd)
    platform_name = platform_name or os.name
    name = Path(command[0]).name
    expected_root = REPO.resolve()
    actual_root = source_identity.git_root(REPO, env=env)
    if actual_root == expected_root:
        source_sha = source_identity.ref_sha(REPO, "HEAD", env=env)
        tree_state = source_identity.tree_state(REPO, env=env)
    else:
        source_sha = None
        tree_state = None
    record = {
        "sourceSHA": source_sha,
        "treeState": tree_state,
        "runtimeSHA": "UNKNOWN", "os": platform.platform(),
        "runtime": f"python {platform.python_version()} on {platform_name}",
        "model": None, "column": column, "command": subprocess.list2cmdline(command), "cwd": str(cwd),
        "exitCode": None, "testID": test_id or f"gate:{name}", "status": "BLOCKED",
        "fixtureOwner": None, "mock": False, "realDependencies": [], "rawDigest": None,
        "artifactDigest": None, "startedAt": timestamp(), "endedAt": None, "reviewer": None,
    }
    if platform_name not in SUPPORTED:
        record["endedAt"] = timestamp()
        return record
    if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        record["endedAt"] = timestamp()
        return record
    if not (isinstance(tree_state, dict) and isinstance(tree_state.get("clean"), bool)
            and isinstance(tree_state.get("changed_paths"), list)):
        record["endedAt"] = timestamp()
        return record
    with tempfile.TemporaryFile() as output:
        try:
            child, tree = spawn(command, cwd, env, output)
        except OSError:
            record["endedAt"] = timestamp()
            return record
        timed_out = False
        try:
            try:
                record["exitCode"] = child.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                tree.terminate()
                try:
                    child.wait(timeout=KILL_WAIT_S)
                except subprocess.TimeoutExpired:
                    timed_out = None
        finally:
            tree.close()
        output.seek(0)
        record["rawDigest"] = hashlib.sha256(output.read()).hexdigest()
    record["endedAt"] = timestamp()
    record["realDependencies"] = [f"process:{name}"]
    if timed_out is None:  # the leader survived the kill: say so instead of passing quietly
        record["status"], record["realDependencies"] = "BLOCKED", []
    elif timed_out:
        record["status"], record["exitCode"] = "FAIL", None
    else:
        record["status"] = "PASS" if record["exitCode"] == 0 else "FAIL"
    return record
