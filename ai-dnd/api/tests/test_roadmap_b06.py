"""B06 platform runner contract; spawns only tiny python children, no game/model/server calls."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools" / "acceptance"))
import evidence as evidence_owner
import platform_runner as owner
from api.tests.guard_bound import CHILD_PROCESS, guard_bound

PY = sys.executable
# Leader starts a grandchild, records its pid, then both sleep far longer than any timeout.
TREE = (
    "import subprocess,sys,time\n"
    "kid=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'])\n"
    "open(sys.argv[1],'w').write(str(kid.pid))\n"
    "time.sleep(120)\n"
)


def pid_alive(pid):
    if os.name == "nt":
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
        kernel.CloseHandle(ctypes.c_void_p(handle))
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill(0); read its state when /proc is available.
    stat = Path(f"/proc/{pid}/stat")
    return not (stat.exists() and stat.read_text().rsplit(")", 1)[1].split()[0] == "Z")


def wait_dead(pid, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.1)
    return not pid_alive(pid)


class RoadmapB06Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cwd = Path(self.tmp.name)
        self.cleanup_pids = []
        self.addCleanup(self.reap)

    def reap(self):
        for pid in self.cleanup_pids:
            if pid_alive(pid):
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                else:
                    os.kill(pid, 9)

    def run_gate(self, command, timeout_s=20, env=None, **kwargs):
        return owner.run_gate(command, self.cwd, timeout_s, dict(os.environ) if env is None else env, **kwargs)

    @guard_bound(CHILD_PROCESS)
    def test_runner_timeout_cleans_owned_children(self):
        pid_file = self.cwd / "kid.pid"
        started = time.monotonic()
        record = self.run_gate([PY, "-c", TREE, str(pid_file)], timeout_s=3)
        self.assertLess(time.monotonic() - started, 30)
        kid = int(pid_file.read_text())
        self.cleanup_pids.append(kid)
        self.assertTrue(wait_dead(kid), "grandchild of the timed-out gate is still alive")
        self.assertEqual(record["status"], "FAIL")
        self.assertIsNone(record["exitCode"])
        evidence_owner.validate_record(record)

    @guard_bound(CHILD_PROCESS)
    def test_timeout_leaves_unowned_processes_alone(self):
        bystander = subprocess.Popen([PY, "-c", "import time;time.sleep(120)"])
        self.cleanup_pids.append(bystander.pid)
        self.addCleanup(bystander.wait)
        self.addCleanup(bystander.kill)
        self.run_gate([PY, "-c", "import time;time.sleep(120)"], timeout_s=2)
        time.sleep(0.5)
        self.assertTrue(pid_alive(bystander.pid))

    @guard_bound(CHILD_PROCESS)
    def test_descendants_are_cleaned_even_after_the_leader_exited(self):
        pid_file = self.cwd / "kid.pid"
        code = ("import subprocess,sys\n"
                "kid=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'])\n"
                "open(sys.argv[1],'w').write(str(kid.pid))\n")
        record = self.run_gate([PY, "-c", code, str(pid_file)], timeout_s=20)
        kid = int(pid_file.read_text())
        self.cleanup_pids.append(kid)
        self.assertEqual(record["exitCode"], 0)
        self.assertTrue(wait_dead(kid), "orphaned descendant of a finished gate is still alive")

    @guard_bound(CHILD_PROCESS)
    def test_exit_code_and_status_are_recorded(self):
        passed = self.run_gate([PY, "-c", "print('ok')"])
        failed = self.run_gate([PY, "-c", "import sys;sys.exit(3)"])
        self.assertEqual((passed["status"], passed["exitCode"]), ("PASS", 0))
        self.assertEqual((failed["status"], failed["exitCode"]), ("FAIL", 3))
        for record in (passed, failed):
            evidence_owner.validate_record(record)
            self.assertEqual(record["cwd"], str(self.cwd))
            self.assertEqual(record["column"], "unit")
            self.assertRegex(record["rawDigest"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(passed["rawDigest"], failed["rawDigest"])

    @guard_bound(CHILD_PROCESS)
    def test_shell_strings_are_never_executed(self):
        marker = self.cwd / "marker.txt"
        for bad in (f"echo hi > {marker}", "python -c pass", (PY, "-c", "pass"), [PY, 3]):
            with self.assertRaises(TypeError):
                self.run_gate(bad)
        with self.assertRaises(ValueError):
            self.run_gate([])
        self.assertFalse(marker.exists())
        record = self.run_gate([PY, "-c", "import sys;print(sys.argv[1])", "a && b; c | d"])
        self.assertEqual(record["exitCode"], 0)

    @guard_bound(CHILD_PROCESS)
    def test_missing_executable_is_blocked_not_silent(self):
        record = self.run_gate(["definitely-not-a-real-binary-b06"])
        self.assertEqual(record["status"], "BLOCKED")
        self.assertIsNone(record["exitCode"])
        evidence_owner.validate_record(record)

    @guard_bound(CHILD_PROCESS)
    def test_environment_is_exactly_what_the_caller_passed(self):
        env = {**os.environ, "B06_PROBE": "only-here"}
        code = ("import os,sys;sys.exit(0 if os.environ.get('B06_PROBE')=='only-here' "
                "and 'AI_DND_SECRET_PROBE' not in os.environ else 7)")
        os.environ["AI_DND_SECRET_PROBE"] = "leak"
        self.addCleanup(os.environ.pop, "AI_DND_SECRET_PROBE", None)
        self.assertEqual(self.run_gate([PY, "-c", code], env=env)["exitCode"], 0)

    def test_unsupported_platform_is_a_loud_blocked_record(self):
        record = self.run_gate([PY, "-c", "pass"], platform_name="plan9")
        self.assertEqual(record["status"], "BLOCKED")
        self.assertIsNone(record["exitCode"])
        self.assertIn("plan9", record["runtime"])

    def test_missing_source_identity_blocks_before_spawn(self):
        with mock.patch.object(owner.source_identity, "ref_sha", return_value=None):
            with mock.patch.object(owner.source_identity, "tree_state",
                                   return_value={"clean": True, "changed_paths": []}):
                with mock.patch.object(owner, "spawn") as spawn:
                    record = self.run_gate([PY, "-c", "pass"])
        self.assertEqual(record["status"], "BLOCKED")
        self.assertIsNone(record["exitCode"])
        spawn.assert_not_called()

    def test_mismatched_git_root_blocks_before_spawn(self):
        child = mock.Mock()
        child.wait.return_value = 0
        tree = mock.Mock()
        with mock.patch.object(owner.source_identity, "git_root",
                               return_value=self.cwd / "wrong-copy"):
            with mock.patch.object(owner.source_identity, "ref_sha",
                                   return_value="a" * 40):
                with mock.patch.object(owner.source_identity, "tree_state",
                                       return_value={"clean": True, "changed_paths": []}):
                    with mock.patch.object(owner, "spawn", return_value=(child, tree)) as spawn:
                        record = self.run_gate([PY, "-c", "pass"])
        self.assertEqual(record["status"], "BLOCKED")
        self.assertIsNone(record["exitCode"])
        spawn.assert_not_called()

    @guard_bound(CHILD_PROCESS)
    def test_non_utf8_output_does_not_break_the_runner(self):
        record = self.run_gate([PY, "-c", "import sys;sys.stdout.buffer.write(b'\\xff\\xfe caf\\xe9')"])
        self.assertEqual(record["exitCode"], 0)
        self.assertRegex(record["rawDigest"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
