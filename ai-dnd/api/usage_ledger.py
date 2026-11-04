"""A write-only daily usage log of model calls: one JSON line a call, beside the Haiku count.

It only measures. It never gates a call (HaikuSpend stays the gate), a write that fails
only warns, and a line it cannot read is skipped. The file is append-only with one write per
line, so the played API and a separate run command can share it without losing a line (on Windows a
side lock file makes the writers take turns).
Nothing but names and counts is written: no prompt, no reply, no key.
"""

from __future__ import annotations

import json
import logging
import math
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    import msvcrt
else:  # POSIX appends one whole write at the end atomically (O_APPEND); no extra lock is needed.
    msvcrt = None

USAGE_FILE_NAME = "model-usage.jsonl"
_logger = logging.getLogger("ai_dnd.api.ollama")

# USD per million tokens as (input, output). Haiku's pair is the old code constant and has NOT
# been checked against the current price list. Gemini is on the free tier (owner said free tier
# 2026-11-04), so its price is known and zero; its calls and tokens are still counted. A provider with
# None (or no entry) has an unknown price and never enters a total. Gemma is local and costs nothing.
PRICES_USD_PER_MILLION: Mapping[str, tuple[float, float] | None] = {
    "haiku": (0.10, 0.50),
    "gemini": (0.0, 0.0),
    "gemma": (0.0, 0.0),
}

_COUNT_FIELDS = ("input", "output", "thought")
_LOCK_WAIT_SECONDS = 2.0


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _count(value: object) -> int:
    """A token count as the reader accepts it: a whole number of zero or more, else 0."""
    return value if type(value) is int and value >= 0 else 0


def _duration(value: object) -> float | None:
    """Seconds as the reader accepts them: a finite number of zero or more, else None."""
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        return None
    return value


class UsageLedger:
    """Today's model usage per provider, read back from a JSONL file. The day is the local date."""

    def __init__(
        self,
        path: Path,
        now: Callable[[], datetime] = _local_now,
        prices: Mapping[str, tuple[float, float] | None] = PRICES_USD_PER_MILLION,
        warn_usd: float = 3.0,
    ):
        self._path = path
        self._now = now
        self._prices = prices
        self._warn_usd = warn_usd
        self._lock = threading.Lock()

    @contextmanager
    def _appending(self) -> Iterator[None]:
        """Hold the one-writer-at-a-time lock around an append.

        Windows does not append atomically: each writer seeks to the end and then writes, so two
        processes (or two ledgers) can write over each other. A byte lock on a small side file makes
        them take turns. The wait is bounded; past it the append fails and only warns.
        """
        if msvcrt is None:
            yield
            return
        side_file = self._path.with_name(self._path.name + ".lock")
        with open(side_file, "a+b") as handle:
            deadline = time.monotonic() + _LOCK_WAIT_SECONDS
            while True:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.002)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    def day(self) -> str:
        """The ledger's day: the clock's local date."""
        return self._now().strftime("%Y-%m-%d")

    def record(
        self,
        provider: str,
        *,
        input_tokens: int,
        output_tokens: int,
        thought_tokens: int = 0,
        seconds: float | None = None,
        outcome: str = "answered",
    ) -> None:
        """Append one line. Never raises: a call must not wait on, or fail from, its own log.

        A token count that is not a whole number of zero or more is written as 0, and a seconds value that is not
        a real duration (NaN, infinity, negative, not a number) as None: the line stays readable and the call counts.
        """
        try:
            line = json.dumps(
                {"day": self.day(), "provider": provider, "input": _count(input_tokens),
                 "output": _count(output_tokens), "thought": _count(thought_tokens),
                 "seconds": _duration(seconds), "outcome": outcome},
                separators=(",", ":"),
            ) + "\n"
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                # One open and one write of one whole line, one writer at a time across processes.
                with self._appending(), open(self._path, "a", encoding="utf-8", newline="\n") as handle:
                    handle.write(line)
        except Exception as error:  # noqa: BLE001 - fail-open by design; only the error type is logged
            _logger.warning("Usage ledger could not record a call (%s).", type(error).__name__)

    def today(self) -> dict[str, dict[str, float]]:
        """Per provider: calls, input, output, thought, seconds for today. Unreadable lines are skipped."""
        day = self.day()
        totals: dict[str, dict[str, float]] = {}
        try:
            with self._lock, open(self._path, encoding="utf-8", errors="replace") as handle:
                for raw in handle:
                    entry = self._read_line(raw, day)
                    if entry is None:
                        continue
                    provider, counts, seconds = entry
                    row = totals.setdefault(
                        provider, {"calls": 0, "input": 0, "output": 0, "thought": 0, "seconds": 0})
                    row["calls"] += 1
                    for name, count in zip(_COUNT_FIELDS, counts):
                        row[name] += count
                    row["seconds"] += seconds
        except FileNotFoundError:
            return {}
        except Exception as error:  # noqa: BLE001 - an unreadable file reads as an empty day
            _logger.warning("Usage ledger could not read the day (%s).", type(error).__name__)
            return {}
        return totals

    @staticmethod
    def _read_line(raw: str, day: str) -> tuple[str, tuple[int, int, int], float] | None:
        try:
            entry = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(entry, dict) or entry.get("day") != day:
            return None
        provider = entry.get("provider")
        counts = tuple(entry.get(name) for name in _COUNT_FIELDS)
        seconds = entry.get("seconds")
        if not isinstance(provider, str) or not provider:
            return None
        if not all(type(count) is int and count >= 0 for count in counts):
            return None
        if seconds is None:
            seconds = 0
        elif type(seconds) not in (int, float) or seconds < 0:
            return None
        return provider, counts, seconds

    def known_usd_today(self) -> float:
        """Today's cost over providers with a known price. An unknown price adds nothing."""
        total = 0.0
        for provider, row in self.today().items():
            price = self._prices.get(provider)
            if price is None:
                continue
            per_input, per_output = price
            # A thinking token is billed as an output token.
            total += (row["input"] * per_input + (row["output"] + row["thought"]) * per_output) / 1_000_000
        return total

    def warning(self) -> str | None:
        """A line once today's known cost reaches the limit; it never stops anything."""
        spent = self.known_usd_today()
        if round(spent, 6) < self._warn_usd:
            return None
        return (f"Model usage today has reached {spent:.2f} USD on providers with a known price "
                f"(warning at {self._warn_usd:.2f}). Providers without a known price are not counted.")
