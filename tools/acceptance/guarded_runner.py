"""Fail-closed Python unittest launcher with a per-child B06 guard proof."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

import platform_runner


REPO = Path(__file__).resolve().parents[2]
GUARD_FILE = Path(__file__).resolve().parent / "linux_guard" / "sitecustomize.py"
GUARD_ID = "ai-dnd-b06-linux-guard-v1"
# Updated with the guard file; mismatch means no target test import is allowed.
EXPECTED_GUARD_SHA256 = "d0803047bca67beec76a27d7825cef6f655bafee81d290d5c940d530ec0a51c5"
SELECTOR = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\Z")
SCRATCH_BASE = Path("/tmp").resolve()
ISOLATED_PYTHON_ARGS = ("-I", "-S", "-B")


def _blocked(reason, guard=None):
    return {"status": "BLOCKED", "reason": reason, "guard": guard, "target": None,
            "testMethodsRun": None}


def _clean_env(run_root):
    found_git = shutil.which("git")
    if not found_git:
        raise OSError("trusted Git executable not found")
    git = Path(found_git).resolve()
    if not any(_within(git, Path(root)) for root in ("/nix/store", "/usr/bin", "/bin")):
        raise OSError("Git executable is outside trusted system paths")
    path = os.pathsep.join([str(git.parent), os.defpath])
    for name in ("home", "tmp", "db"):
        (run_root / name).mkdir(parents=True, exist_ok=True)
    denied = run_root / "denied" / "synthetic.txt"
    denied.parent.mkdir(parents=True, exist_ok=True)
    denied.write_text("synthetic forbidden probe", encoding="utf-8")
    roots = [str(REPO), sys.prefix, sys.base_prefix, str(run_root), str(GUARD_FILE.parent.resolve())]
    return {
        "PATH": path,
        "HOME": str(run_root / "home"),
        "TMP": str(run_root / "tmp"),
        "TMPDIR": str(run_root / "tmp"),
        "PYTHONPATH": str(GUARD_FILE.parent),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0",
        "AI_DND_CAMPAIGN_DB": str(run_root / "db" / "campaigns.sqlite3"),
        "AI_DND_DISABLE_DEFAULT_APP": "1",
        "AI_DND_GUARD_EXPECTED_SHA256": EXPECTED_GUARD_SHA256,
        "AI_DND_GUARD_ALLOWED_ROOTS": json.dumps(roots),
        "AI_DND_GUARD_RUN_ROOT": str(run_root),
        "AI_DND_GUARD_DENIED_PATH": str(denied),
    }


def _child_identity_code(role):
    return (
        "import hashlib,sys\n"
        f"guard_path={str(GUARD_FILE.resolve())!r}\n"
        f"expected={EXPECTED_GUARD_SHA256!r}\n"
        "with open(guard_path,'rb') as source_file: guard_source=source_file.read()\n"
        "digest=hashlib.sha256(guard_source).hexdigest()\n"
        "if digest != expected: raise SystemExit(97)\n"
        "guard_module=type(sys)('sitecustomize')\n"
        "guard_module.__file__=guard_path\n"
        "sys.modules['sitecustomize']=guard_module\n"
        "exec(compile(guard_source,guard_path,'exec',dont_inherit=True),guard_module.__dict__)\n"
        "import json,os,socket,subprocess\n"
        "from pathlib import Path\n"
        f"if guard_module.GUARD_ID != {GUARD_ID!r}: raise SystemExit(97)\n"
        "if digest != os.environ['AI_DND_GUARD_EXPECTED_SHA256']: raise SystemExit(97)\n"
        "if Path(guard_module.__file__).resolve() != Path(guard_path).resolve(): raise SystemExit(97)\n"
        f"role={role!r}\n"
        "denied=Path(os.environ['AI_DND_GUARD_DENIED_PATH'])\n"
        "try: denied.read_text(encoding='utf-8')\n"
        "except PermissionError: pass\n"
        "else: raise SystemExit(96)\n"
        "try: sock=socket.socket()\n"
        "except PermissionError: pass\n"
        "else: sock.close(); raise SystemExit(96)\n"
        "try: sys.audit('subprocess.Popen',[sys.executable,'-c','pass'],None,None)\n"
        "except PermissionError: pass\n"
        "else: raise SystemExit(96)\n"
        "proof={'guard_id':guard_module.GUARD_ID,'sha256':digest,'denied_path_blocked':True}\n"
        "sys.stdout.write('B06_GUARD_PROOF:'+json.dumps(proof,sort_keys=True)+'\\n')\n"
    )


def _target_code(selectors, summary_path):
    return (
        _child_identity_code("target")
        + f"sys.path.extend({_target_import_paths()!r})\n"
        + "import json,sys,unittest\n"
        + "from pathlib import Path\n"
        + f"selectors={selectors!r}\n"
        + "suite=unittest.defaultTestLoader.loadTestsFromNames(selectors)\n"
        + "result=unittest.TextTestRunner(verbosity=2).run(suite)\n"
        + f"Path({str(summary_path)!r}).write_text(json.dumps({{'testsRun':result.testsRun}}),"
          "encoding='utf-8')\n"
        + "raise SystemExit(0 if result.wasSuccessful() else 1)\n"
    )


def _target_import_paths():
    paths = [str(REPO / "ai-dnd")]
    for root in {Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()}:
        for pattern in ("lib/python*/site-packages", "lib/python*/dist-packages",
                        "Lib/site-packages"):
            paths.extend(str(path.resolve()) for path in root.glob(pattern) if path.is_dir())
    return list(dict.fromkeys(paths))


def run_unittest_gate(selectors, *, timeout_s, run_root):
    """Run named unittest selectors only after both guard proofs pass.

    The environment is constructed from scratch; no caller environment is copied.
    """
    if not isinstance(selectors, list) or not selectors or any(
            not isinstance(item, str) or not SELECTOR.fullmatch(item) for item in selectors):
        return _blocked("invalid unittest selector")
    if type(timeout_s) not in (int, float) or timeout_s <= 0:
        return _blocked("timeout must be positive")
    try:
        run_root = Path(run_root).resolve()
    except (TypeError, OSError):
        return _blocked("invalid synthetic run root")
    if _within_repo(run_root):
        return _blocked("synthetic run root must be outside the candidate")
    try:
        run_root.relative_to(SCRATCH_BASE)
    except ValueError:
        return _blocked("synthetic run root must be under /tmp")
    if run_root == SCRATCH_BASE:
        return _blocked("run root cannot be the shared /tmp directory")
    try:
        if run_root.exists() and any(run_root.iterdir()):
            return _blocked("synthetic run root must be empty")
        run_root.mkdir(parents=True, exist_ok=True)
        if not GUARD_FILE.is_file():
            return _blocked("guard file missing")
        digest = hashlib.sha256(GUARD_FILE.read_bytes()).hexdigest()
        if digest != EXPECTED_GUARD_SHA256:
            return _blocked("guard digest differs from pinned identity")
        env = _clean_env(run_root)
    except (OSError, ValueError) as exc:
        return _blocked(f"guard setup failed: {type(exc).__name__}")

    probe = _child_identity_code("probe")
    try:
        guard_record = platform_runner.run_gate(
            [sys.executable, *ISOLATED_PYTHON_ARGS, "-c", probe],
            REPO / "ai-dnd", timeout_s, env,
            test_id="B06 guarded child preflight")
    except Exception as exc:
        return _blocked(f"guard runner failed: {type(exc).__name__}")
    if guard_record["status"] != "PASS":
        return _blocked("guard preflight did not pass", guard_record)
    proof = json.dumps({"guard_id": GUARD_ID, "sha256": EXPECTED_GUARD_SHA256,
                        "denied_path_blocked": True}, sort_keys=True)
    expected_digest = hashlib.sha256(f"B06_GUARD_PROOF:{proof}\n".encode()).hexdigest()
    if guard_record["rawDigest"] != expected_digest:
        return _blocked("guard identity or synthetic denial proof mismatch", guard_record)

    summary_path = run_root / "unittest-summary.json"
    try:
        target = platform_runner.run_gate(
            [sys.executable, *ISOLATED_PYTHON_ARGS, "-c",
             _target_code(selectors, summary_path)],
            REPO / "ai-dnd", timeout_s, env, test_id="B06 guarded unittest target")
    except Exception as exc:
        return {"status": "BLOCKED", "reason": f"target runner failed: {type(exc).__name__}",
                "guard": guard_record, "target": None, "testMethodsRun": None}
    if target["exitCode"] in (96, 97):
        return {"status": "BLOCKED", "reason": "target child guard proof failed",
                "guard": guard_record, "target": target, "testMethodsRun": None}
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(summary, dict):
            raise ValueError("invalid unittest summary")
        count = summary.get("testsRun")
        if type(count) is not int or count < 0:
            raise ValueError("invalid test count")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        count = None

    status, reason = target["status"], None
    if status == "PASS" and (count is None or count == 0):
        status = "FAIL"
        reason = ("unittest summary missing or invalid" if count is None
                  else "unittest summary reports zero tests")
    return {"status": status, "reason": reason, "guard": guard_record,
            "target": target, "testMethodsRun": count}


def _within_repo(path):
    try:
        path.relative_to(REPO)
        return True
    except ValueError:
        return False


def _within(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False
