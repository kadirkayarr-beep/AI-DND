"""Source, runtime and environment identity for acceptance evidence (B01).

Read-only: inspects git state and config files; never starts the game, a model,
a server, or touches personal campaign data or port 8008.
"""
import hashlib
import json
import ntpath
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tomllib


BASELINE_PATH = Path("docs/acceptance/source-baseline.json")
LOCKFILES = {"pnpm-lock.yaml": "pnpm", "package-lock.json": "npm", "yarn.lock": "yarn"}
ENTRYPOINTS = ("ai-dnd/api/main.py", "artifacts/ai-dnd-experience/src/App.tsx")
BASELINE_LOCKS = ("pnpm-lock.yaml", "uv.lock")
UI_PACKAGE = "artifacts/ai-dnd-experience/package.json"


def _git_context(repo_root):
    """Pin Git to the requested checkout, including linked worktrees."""
    root = Path(repo_root).resolve()
    marker = root / ".git"
    if marker.is_dir():
        return root, marker.resolve()
    if not marker.is_file():
        raise ValueError(f"Repository has no .git entry: {root}")
    content = marker.read_text(encoding="utf-8").strip()
    if not content.startswith("gitdir: "):
        raise ValueError(f"Malformed Git worktree pointer: {marker}")
    git_dir = Path(content.removeprefix("gitdir: ").strip())
    if not git_dir.is_absolute():
        git_dir = root / git_dir
    git_dir = git_dir.resolve(strict=True)
    backlink = git_dir / "gitdir"
    if not backlink.is_file() or Path(backlink.read_text(encoding="utf-8").strip()).resolve() != marker.resolve():
        raise ValueError(f"Git worktree pointer does not match its admin directory: {root}")
    return root, git_dir


def _git_environment(env=None, *, platform_name=None, repo_root=None):
    """Build a read-only Git environment without caller credentials or config."""
    source = os.environ if env is None else env
    platform_name = platform_name or os.name
    trusted_path = []
    if platform_name == "nt":
        program_roots = {
            os.environ.get(name, "")
            for name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")
        }
        git_roots = {
            ntpath.normcase(ntpath.normpath(ntpath.join(root, "Git", subdir)))
            for root in program_roots if root and ntpath.isabs(root)
            for subdir in ("cmd", "bin")
        }
        if not git_roots:
            git_roots = {
                ntpath.normcase(r"c:\program files\git\cmd"),
                ntpath.normcase(r"c:\program files\git\bin"),
                ntpath.normcase(r"c:\program files (x86)\git\cmd"),
                ntpath.normcase(r"c:\program files (x86)\git\bin"),
            }
        entries = source.get("PATH", "").split(";")
        for entry in entries:
            if entry and ntpath.isabs(entry):
                normalized = ntpath.normcase(ntpath.normpath(entry))
                if normalized in git_roots:
                    trusted_path.append(ntpath.normpath(entry))
    else:
        for entry in source.get("PATH", os.defpath).split(os.pathsep):
            if not entry:
                continue
            resolved = Path(entry).resolve()
            if any(resolved == root or root in resolved.parents
                   for root in (Path("/nix/store"), Path("/usr/bin"), Path("/bin"))):
                trusted_path.append(str(resolved))
    path_separator = ";" if platform_name == "nt" else os.pathsep
    clean = {
        "PATH": path_separator.join(trusted_path) or os.defpath,
        "HOME": os.devnull,
        "XDG_CONFIG_HOME": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }
    if repo_root is not None:
        root, git_dir = _git_context(repo_root)
        clean["GIT_DIR"] = str(git_dir)
        clean["GIT_WORK_TREE"] = str(root)
    return clean


def git_root(repo_root, env=None):
    expected = Path(repo_root).resolve()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=expected,
            env=_git_environment(env, repo_root=expected),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        return Path(completed.stdout.decode().strip()).resolve()
    except (OSError, RuntimeError):
        return None


def git(repo_root, *args, env=None):
    expected = Path(repo_root).resolve()
    if git_root(expected, env=env) != expected:
        raise ValueError(f"Git root does not match requested checkout: {expected}")
    return subprocess.check_output(
        ["git", "-c", "core.fsmonitor=false", *args], cwd=expected,
        env=_git_environment(env, repo_root=expected), stderr=subprocess.PIPE).decode()


def ref_sha(repo_root, ref, env=None):
    expected = Path(repo_root).resolve()
    if git_root(expected, env=env) != expected:
        return None
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref], cwd=expected,
        env=_git_environment(env, repo_root=expected),
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return completed.stdout.decode().strip() if completed.returncode == 0 else None


def tree_state(repo_root, env=None):
    """Porcelain -z keeps filenames verbatim; renames report both paths."""
    fields = git(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all",
                 env=env).split("\0")
    changed, index = set(), 0
    while index < len(fields) and fields[index]:
        entry = fields[index]
        changed.add(entry[3:])
        index += 1
        if "R" in entry[:2] or "C" in entry[:2]:
            changed.add(fields[index])
            index += 1
    paths = sorted(changed)
    return {"clean": not paths, "changed_paths": paths}


def requires_python(repo_root):
    data = tomllib.loads((Path(repo_root) / "pyproject.toml").read_text(encoding="utf-8"))
    spec = data.get("project", {}).get("requires-python")
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError("pyproject.toml has no project.requires-python")
    return spec.strip()


def python_supported(repo_root, version):
    spec = requires_python(repo_root)
    match = re.fullmatch(r">=\s*(\d+(?:\.\d+){0,2})", spec)
    if not match:
        raise ValueError(f"Unsupported requires-python specifier: {spec}")
    floor = tuple(int(part) for part in match.group(1).split("."))
    return tuple(version[:len(floor)]) >= floor


def package_manager(repo_root):
    root = Path(repo_root)
    declared = None
    package = root / "package.json"
    if package.is_file():
        declared = json.loads(package.read_text(encoding="utf-8")).get("packageManager")
    for lockfile, name in LOCKFILES.items():
        if (root / lockfile).is_file():
            return {"name": name, "lockfile": lockfile, "declared": declared}
    return {"name": None, "lockfile": None, "declared": declared}


def node_version():
    try:
        completed = subprocess.run(["node", "--version"], stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.decode().strip() if completed.returncode == 0 else None


def runtime_status(source_sha, runtime_identity):
    runtime_sha = (runtime_identity or {}).get("sha")
    if not isinstance(runtime_sha, str) or not runtime_sha:
        return None, "UNKNOWN"
    return runtime_sha, "MATCH" if runtime_sha == source_sha else "MISMATCH"


def inspect_source_identity(repo_root, runtime_identity):
    repo_root = Path(repo_root)
    source_sha = git(repo_root, "rev-parse", "HEAD").strip()
    runtime_sha, status = runtime_status(source_sha, runtime_identity)
    tree = tree_state(repo_root)
    version = sys.version_info[:3]
    supported = python_supported(repo_root, version)
    return {
        "source_sha": source_sha,
        "main_sha": ref_sha(repo_root, "refs/heads/main"),
        "origin_main_sha": ref_sha(repo_root, "refs/remotes/origin/main"),
        "tree_state": tree,
        "runtime_sha": runtime_sha,
        "runtime_sha_status": status,
        "os": {"system": platform.system(), "release": platform.release(),
               "machine": platform.machine()},
        "python": {"version": ".".join(str(part) for part in version),
                   "requires": requires_python(repo_root), "supported": supported},
        "node": node_version(),
        "package_manager": package_manager(repo_root),
        "accepted": status == "MATCH" and tree["clean"] and supported,
    }


def load_baseline(repo_root):
    return json.loads((Path(repo_root) / BASELINE_PATH).read_text(encoding="utf-8"))


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_baseline(repo_root):
    """Record the candidate's entry points, test commands and dependency locks."""
    root = Path(repo_root)
    scripts = json.loads((root / UI_PACKAGE).read_text(encoding="utf-8")).get("scripts", {})
    return {
        "candidate_sha": git(root, "rev-parse", "HEAD").strip(),
        "requires_python": requires_python(root),
        "entrypoints": [name for name in ENTRYPOINTS if (root / name).is_file()],
        "lockfiles": {name: file_sha256(root / name) for name in BASELINE_LOCKS},
        "test_commands": {
            "api": "cd ai-dnd && python -m unittest api.tests.test_roadmap_<id> -v",
            "ui": "node --experimental-strip-types --test "
                  "artifacts/ai-dnd-experience/tests/roadmap-<id>.test.mjs",
            "ui_scripts": {name: scripts[name]
                           for name in ("typecheck", "build", "test:ui") if name in scripts},
        },
        "lint": "UNCONFIGURED",
    }


if __name__ == "__main__":
    print(json.dumps(inspect_source_identity(Path.cwd(), None), indent=2))
