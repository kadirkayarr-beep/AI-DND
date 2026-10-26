"""Source, runtime and environment identity for acceptance evidence (B01).

Read-only: inspects git state and config files; never starts the game, a model,
a server, or touches personal campaign data or port 8008.
"""
import hashlib
import json
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


def git(repo_root, *args):
    return subprocess.check_output(
        ["git", "-c", "core.fsmonitor=false", *args], cwd=repo_root,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}, stderr=subprocess.PIPE).decode()


def ref_sha(repo_root, ref):
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref], cwd=repo_root,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return completed.stdout.decode().strip() if completed.returncode == 0 else None


def tree_state(repo_root):
    """Porcelain -z keeps filenames verbatim; renames report both paths."""
    fields = git(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
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
