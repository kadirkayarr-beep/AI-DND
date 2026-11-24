"""Ratchet core: tool output -> line-free finding keys -> counts -> compare to a shrink-only baseline.

CLI (run from ai-dnd/): python -m scripts.quality_gate.ratchet check|update <tool> <report-file>
       python -m scripts.quality_gate.ratchet check-shrink <baseline-file> <base-ref>
Exit codes: 0 ok, 1 new findings (check) or baseline grew (check-shrink), 2 tool output or baseline unusable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

Counts = dict[str, int]

BASELINE_DIR = Path(__file__).resolve().parent / "baselines"


class ToolOutputError(ValueError):
    """A tool printed nothing or something that is not its JSON report."""


def finding_key(tool: str, path: str, rule: str, name: str) -> str:
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return f"{tool}|{p}|{rule}|{name}"


def _relativize(path: str, root: str) -> str:
    p = path.replace("\\", "/")
    r = root.replace("\\", "/").rstrip("/")
    fold = re.match(r"^[A-Za-z]:", r) is not None
    a, b = (p.lower(), r.lower()) if fold else (p, r)
    return p[len(r) + 1:] if a.startswith(b + "/") else p


def count_findings(keys: list[str]) -> Counts:
    counts: Counts = {}
    for k in keys:
        counts[k] = counts.get(k, 0) + 1
    return counts


def compare(baseline: Counts, current: Counts) -> list[str]:
    out = []
    for key in sorted(current):
        have, allowed = current[key], baseline.get(key, 0)
        if have > allowed:
            out.append(f"{key}: {have} found, baseline allows {allowed}")
    return out


def load_baseline(path: Path) -> Counts:
    return {k: int(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def write_baseline(path: Path, counts: Counts) -> None:
    text = json.dumps(counts, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_bytes(text.encode("utf-8"))


def baseline_growth(old: Counts, new: Counts) -> list[str]:
    return [
        f"{k}: baseline grew from {old.get(k, 0)} to {v}"
        for k, v in sorted(new.items())
        if v > old.get(k, 0)
    ]


def _base_counts(path: Path, ref: str) -> Counts | None:
    """Counts of `path` at `ref`; None = file absent there (first introduction). Raises OSError/ValueError otherwise."""
    rel = os.path.relpath(path)
    res = subprocess.run(
        ["git", "show", f"{ref}:./{Path(rel).as_posix()}"],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if res.returncode != 0:
        if "does not exist in" in res.stderr or "exists on disk, but not in" in res.stderr:
            return None
        raise OSError(f"git show failed: {res.stderr.strip()}")
    data = json.loads(res.stdout)
    if not isinstance(data, dict):
        raise ValueError("base baseline is not a JSON object")
    for k, v in data.items():
        if type(v) is not int or v < 0:
            raise ValueError(f"base baseline count for {k!r} is not a non-negative integer")
    return dict(data)


def _check_shrink(path: Path, ref: str) -> int:
    try:
        new = load_baseline(path)
        old = _base_counts(path, ref)
    except (OSError, ValueError) as exc:
        print(f"BASELINE ERROR: {exc}", file=sys.stderr)
        return 2
    if old is None:
        return 0
    grown = baseline_growth(old, new)
    for g in grown:
        print(f"GREW: {g}")
    return 1 if grown else 0


def _load_json(text: str, tool: str):
    if not text or not text.strip():
        raise ToolOutputError(f"{tool}: empty output (a crashed tool is not a clean run)")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolOutputError(f"{tool}: output is not JSON ({exc.msg})") from exc


def _symbol(message: str) -> str:
    m = re.search(r"[`'\"]([^`'\"]+)[`'\"]", message)
    return m.group(1) if m else re.sub(r"\d+", "#", message.strip())


def parse_ruff(text: str, root: str | None = None) -> list[str]:
    """root: absolute checkout dir the report paths are relative to (default: the ai-dnd dir of this checkout)."""
    root = root if root is not None else str(BASELINE_DIR.parents[2])
    data = _load_json(text, "ruff")
    if not isinstance(data, list):
        raise ToolOutputError("ruff: expected a JSON list")
    if not all(isinstance(i, dict) for i in data):
        raise ToolOutputError("ruff: list items must be objects")
    return [
        finding_key(
            "ruff",
            _relativize(str(i.get("filename", "")), root),
            str(i.get("code", "")),
            _symbol(str(i.get("message", ""))),
        )
        for i in data
    ]


def _name_of(item) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or item.get("symbol") or item.get("path") or item.get("file") or "")
    return str(item)


def _walk_issue(tool: str, file: str, issue: dict, keys: list[str]) -> None:
    for rule, items in issue.items():
        if rule in ("file", "path"):
            continue
        if isinstance(items, dict):  # e.g. enumMembers: {"Color": [..]}
            for sub, sub_items in items.items():
                if isinstance(sub_items, list):
                    for it in sub_items:
                        keys.append(finding_key(tool, file, f"{rule}.{sub}", _name_of(it)))
            continue
        if not isinstance(items, list):
            continue
        for it in items:
            if isinstance(it, list):  # e.g. duplicates: [[{name}, {name}]]
                name = "+".join(sorted(_name_of(x) for x in it))
            else:
                name = _name_of(it)
            keys.append(finding_key(tool, file, rule, name))


def _parse_generic(tool: str, text: str) -> list[str]:
    """Shape unverified until Task 4 sees real output; tolerant of the documented knip/fallow layouts."""
    data = _load_json(text, tool)
    keys: list[str] = []
    if isinstance(data, dict):
        for f in data.get("files", []) or []:
            keys.append(finding_key(tool, _name_of(f), "files", ""))
        issues = data.get("issues", [])
    elif isinstance(data, list):
        issues = data
    else:
        raise ToolOutputError(f"{tool}: unexpected JSON shape")
    for issue in issues or []:
        if not isinstance(issue, dict):
            raise ToolOutputError(f"{tool}: unexpected issue shape")
        file = str(issue.get("file") or issue.get("path") or "")
        if "type" in issue or "rule" in issue:
            keys.append(finding_key(tool, file, str(issue.get("type") or issue.get("rule")), _name_of(issue)))
        else:
            _walk_issue(tool, file, issue, keys)
    return keys


def parse_knip(text: str) -> list[str]:
    """Real shape (knip 6, --reporter json): {"issues": [{"file", "files": [{"name"}], "exports": [{"name",...}], ...}]}."""
    data = _load_json(text, "knip")
    if not isinstance(data, dict) or not isinstance(data.get("issues"), list):
        raise ToolOutputError("knip: expected an object with an 'issues' list")
    return _parse_generic("knip", text)


_FALLOW_NOT_FINDINGS = {"next_steps", "workspace_diagnostics", "gate_outcomes"}


def _fallow_name(item: dict) -> str:
    for key in ("export_name", "package_name", "specifier", "raw_key", "name"):
        if item.get(key):
            return str(item[key])
    parts = [str(item[k]) for k in ("component_name", "parent_name", "prop_name", "member_name") if item.get(k)]
    return ".".join(parts)


def parse_fallow(text: str) -> list[str]:
    """Real shape (fallow 3.45, `dead-code --format json`): top-level lists such as unused_files,
    unused_exports, unused_dependencies; every list-of-objects key except the non-finding ones is a rule."""
    data = _load_json(text, "fallow")
    if not isinstance(data, dict) or data.get("kind") != "dead-code":
        raise ToolOutputError("fallow: expected a dead-code report object")
    keys: list[str] = []
    for rule, items in data.items():
        if rule in _FALLOW_NOT_FINDINGS or not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                raise ToolOutputError("fallow: unexpected finding shape")
            keys.append(finding_key("fallow", str(item.get("path", "")), rule, _fallow_name(item)))
    return keys


PARSERS = {"ruff": parse_ruff, "knip": parse_knip, "fallow": parse_fallow}


def _whitelist_names(text: str) -> set[str]:
    names = set()
    for line in text.splitlines():
        code = line.split("#", 1)[0].strip()
        if code:
            names.add(code)
    return names


def _check_names_shrink(path: Path, ref: str) -> int:
    """Vulture whitelist: entry names may only shrink versus `ref` (a new name hides future findings)."""
    try:
        new = _whitelist_names(path.read_text(encoding="utf-8"))
        rel = os.path.relpath(path)
        res = subprocess.run(
            ["git", "show", f"{ref}:./{Path(rel).as_posix()}"],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
    except OSError as exc:
        print(f"BASELINE ERROR: {exc}", file=sys.stderr)
        return 2
    if res.returncode != 0:
        if "does not exist in" in res.stderr or "exists on disk, but not in" in res.stderr:
            return 0
        print(f"BASELINE ERROR: git show failed: {res.stderr.strip()}", file=sys.stderr)
        return 2
    grown = sorted(new - _whitelist_names(res.stdout))
    for g in grown:
        print(f"GREW: whitelist name {g!r} is new")
    return 1 if grown else 0


def _fingerprints(text: str) -> set[str]:
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("gitleaks baseline is not a JSON list")
    out = set()
    for f in data:
        fp = f.get("Fingerprint") if isinstance(f, dict) else None
        if not isinstance(fp, str) or not fp:
            raise ValueError("gitleaks baseline entry has no Fingerprint")
        out.add(fp)
    return out


def _check_fingerprints_shrink(path: Path, ref: str) -> int:
    """Gitleaks baseline: the Fingerprint set may only shrink versus `ref`."""
    try:
        new = _fingerprints(path.read_text(encoding="utf-8"))
        rel = os.path.relpath(path)
        res = subprocess.run(
            ["git", "show", f"{ref}:./{Path(rel).as_posix()}"],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        if res.returncode != 0:
            if "does not exist in" in res.stderr or "exists on disk, but not in" in res.stderr:
                return 0
            print(f"BASELINE ERROR: git show failed: {res.stderr.strip()}", file=sys.stderr)
            return 2
        old = _fingerprints(res.stdout)
    except (OSError, ValueError) as exc:
        print(f"BASELINE ERROR: {exc}", file=sys.stderr)
        return 2
    grown = sorted(new - old)
    for g in grown:
        print(f"GREW: gitleaks fingerprint {g} is new")
    return 1 if grown else 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["check-shrink"]:
        sp = argparse.ArgumentParser(prog="ratchet check-shrink")
        sp.add_argument("mode")
        sp.add_argument("baseline", type=Path)
        sp.add_argument("base_ref")
        a = sp.parse_args(argv)
        return _check_shrink(a.baseline, a.base_ref)
    if argv[:1] == ["check-fingerprints-shrink"]:
        sp = argparse.ArgumentParser(prog="ratchet check-fingerprints-shrink")
        sp.add_argument("mode")
        sp.add_argument("baseline", type=Path)
        sp.add_argument("base_ref")
        a = sp.parse_args(argv)
        return _check_fingerprints_shrink(a.baseline, a.base_ref)
    if argv[:1] == ["check-names-shrink"]:
        sp = argparse.ArgumentParser(prog="ratchet check-names-shrink")
        sp.add_argument("mode")
        sp.add_argument("whitelist", type=Path)
        sp.add_argument("base_ref")
        a = sp.parse_args(argv)
        return _check_names_shrink(a.whitelist, a.base_ref)
    ap = argparse.ArgumentParser(prog="ratchet")
    ap.add_argument("mode", choices=["check", "update"])
    ap.add_argument("tool", choices=sorted(PARSERS))
    ap.add_argument("report", type=Path)
    ap.add_argument("--baseline-dir", type=Path, default=BASELINE_DIR)
    args = ap.parse_args(argv)
    try:
        current = count_findings(PARSERS[args.tool](args.report.read_text(encoding="utf-8")))
    except OSError as exc:
        print(f"TOOL OUTPUT ERROR: cannot read report ({exc})", file=sys.stderr)
        return 2
    except ToolOutputError as exc:
        print(f"TOOL OUTPUT ERROR: {exc}", file=sys.stderr)
        return 2
    target = args.baseline_dir / f"{args.tool}.json"
    try:
        base = load_baseline(target) if target.exists() else None
    except (OSError, ValueError) as exc:
        print(f"BASELINE ERROR: cannot load {target} ({exc})", file=sys.stderr)
        return 2
    if args.mode == "check":
        problems = compare(base or {}, current)
        for p in problems:
            print(f"NEW: {p}")
        return 1 if problems else 0
    if base is not None:
        grown = compare(base, current)
        if grown:
            for p in grown:
                print(f"GREW: {p}", file=sys.stderr)
            print("baseline may only shrink", file=sys.stderr)
            return 3
    args.baseline_dir.mkdir(parents=True, exist_ok=True)
    write_baseline(target, current)
    return 0


if __name__ == "__main__":
    sys.exit(main())
