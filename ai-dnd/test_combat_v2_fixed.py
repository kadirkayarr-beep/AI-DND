#!/usr/bin/env python3
"""Compatibility entry point for the superseded second V2 test iteration.

The scenarios now live in test_combat_v2.py, using authoritative round/initiative
rules and deterministic session dice. Keep this command for existing callers,
without maintaining a second copy of the same mechanical expectations.
"""
from test_combat_v2 import run_all_tests


if __name__ == "__main__":
    raise SystemExit(0 if run_all_tests() else 1)