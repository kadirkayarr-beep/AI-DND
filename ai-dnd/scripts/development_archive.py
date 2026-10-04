"""Command-check records using the existing evidence provenance conventions."""
import json
from pathlib import Path
import shlex
import sys

import run_regression_evidence as evidence


DEFAULT_ARCHIVE = evidence.ROOT / "docs/evidence/development-runs"


class Archive:
    def __init__(self, root, kind, argv):
        root = Path(root).resolve()
        repo = evidence.ROOT.parent.resolve()
        approved = (evidence.ROOT / "docs/evidence/development-runs").resolve()
        if root.is_relative_to(repo) and not root.is_relative_to(approved):
            raise ValueError("Within the checkout, use only docs/evidence/development-runs")
        # Never write into historical records or source/config directories.
        if root.is_relative_to(evidence.DEFAULT_ARCHIVE.resolve()):
            raise ValueError("Development records cannot use the historical suite archive")
        if (root.is_relative_to((evidence.ROOT / "scripts").resolve()) or
                any(path.resolve().is_relative_to(root) for path in (
                    evidence.ROOT / "scripts", evidence.ROOT / "game.py",
                    evidence.ROOT / "docs/regression-evidence.md",
                    evidence.ROOT / "docs/development-infrastructure.md"))):
            raise ValueError("Archive cannot contain verifier source")
        self.directory = root / (
            evidence.datetime.now(evidence.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-" + evidence.uuid4().hex)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.path = self.directory / "run.json"
        self.data = {
            "schema_version": 1, "evidence_kind": kind, "run_label": "NEW RUN",
            "historical_certification": False, "started_at": evidence.now(),
            "ended_at": None, "status": "running", "exit_status": None,
            "command": {"argv": argv, "shell": shlex.join(argv),
                        "cwd": str(Path.cwd())},
            "python_version": sys.version, "checks": [],
            "server_source_identity": {"status": "UNVERIFIED",
                                       "reason": "Local verifier identity is not server identity"}
        }
        self.persist()

    def persist(self):
        temporary = self.path.with_suffix(".json.pending")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        temporary.replace(self.path)

    def finish(self, code):
        status = "interrupted" if code == 130 else "runner_error" if code == 2 else "completed"
        self.data.update(ended_at=evidence.now(), exit_status=code, status=status)
        self.data["output_log_sha256"] = evidence.hashlib.sha256(
            (self.directory / "output.log").read_bytes()).hexdigest()
        self.persist()