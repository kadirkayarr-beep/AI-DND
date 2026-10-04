"""Inspect project structure and Git state without automatically running tests."""
from development_checks import main


if __name__ == "__main__":
    raise SystemExit(main("project_health_check"))