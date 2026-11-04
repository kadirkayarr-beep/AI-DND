"""The real-chain journey command: the same scenario files, played in this process with the real model chain.

It spends money, so it plays only when told to (``--yap``). Without it, it prints the estimate (scenarios x steps x
runs) and exits with 2 before anything can reach a model or a key. With it:

- the campaigns live in the runner's temporary store; the owner's save (``AI_DND_CAMPAIGN_DB``, the local play
  database) is taken out of this process's environment first, and the API's default app is not built;
- every model call the engine makes is counted, and none is made past ``--max-calls``: the run stops at the next
  scenario and the report is still written, the cut steps marked as not run;
- latency comes from the chain's observer (every cloud attempt, a skipped one with its reason) and from the adapter
  (the local model's answer, written to the usage ledger, and the whole engine call), one row per attempt and step
  call, so the report shows the median and the worst of the runs;
- the report is ``report.build_report``'s, written as ``ADIM2_RAPOR_<date>.md`` into ``--out`` (never over an
  earlier one), with the run's own notes and the skipped attempts after it.

No key is read before ``--yap``, and none is printed: the report scrubs key-like text, and a skip reason is printed
only when it is a plain code.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import unittest
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import date as Date
from datetime import datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any
from unittest.mock import patch

from api.tests.journeys.schema import Scenario, ScenarioError, Step, load_scenario

if TYPE_CHECKING:
    from api.model_chain import ChainAttempt
    from api.ollama_adapter import AuthenticatedOllamaAdapter
    from api.tests.journeys.runner import StepResult

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"
DEFAULT_RUNS = 3
DEFAULT_MAX_CALLS = 60
EXIT_NOT_ASKED = 2

# What start_local.ps1 -LocalPlay sets for the owner's play; set here only under --yap, only when unset.
_PLAY_DEFAULTS = {"OLLAMA_HOST": "http://127.0.0.1:11434", "AI_DND_MODEL_CHAIN": "gemini,haiku,gemma"}
_LOOPBACK_HOST = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:|/|$)")
_PLAIN_REASON = re.compile(r"[A-Za-z0-9_]{1,40}")
_LOCAL = "yerel"
_WHOLE_CALL = "toplam"
_CUT = "--max-calls sınırı: bu adımdan itibaren model çağrısı yapılmadı; koşulmadı sayıldı"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="journey_real.py",
        description="Yolculuk senaryolarını gerçek model zinciriyle koşar (para harcar; yalnız --yap ile).",
    )
    parser.add_argument("--scenarios", default="core",
                        help="core (real_chain_core işaretliler), all ya da virgülle kimlikler")
    parser.add_argument("--runs", type=_positive, default=DEFAULT_RUNS, help="her senaryo kaç kez koşar")
    parser.add_argument("--max-calls", type=_positive, default=DEFAULT_MAX_CALLS,
                        help="en çok kaç model çağrısı yapılır; aşılmaz")
    parser.add_argument("--yap", action="store_true", help="gerçekten koş (para harcar)")
    parser.add_argument("--out", type=Path, default=Path.cwd(), help="raporun yazılacağı klasör")
    return parser.parse_args(list(argv))


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("1 ya da daha büyük olmalı")
    return value


def select_scenarios(choice: str, directory: Path = SCENARIO_DIR) -> dict[str, Scenario]:
    """``core``: the scenarios flagged ``real_chain_core``; ``all``: every file; else comma-separated ids."""
    loaded = {scenario.id: scenario for scenario in map(load_scenario, sorted(Path(directory).glob("*.json")))}
    if choice == "all":
        return loaded
    if choice == "core":
        return {key: scenario for key, scenario in loaded.items() if scenario.real_chain_core}
    wanted = [name.strip() for name in choice.split(",") if name.strip()]
    missing = [name for name in wanted if name not in loaded]
    if missing or not wanted:
        raise ScenarioError(f"bilinmeyen senaryo: {', '.join(missing) or choice!r}")
    return {name: loaded[name] for name in wanted}


def estimate_calls(scenarios: Mapping[str, Scenario], runs: int) -> int:
    """Scenarios x steps x runs: one turn per step and run (a turn may make more than one model call)."""
    return sum(len(scenario.steps) for scenario in scenarios.values()) * runs


def main(
    argv: Sequence[str] | None = None,
    *,
    out: IO[str] | None = None,
    scenario_dir: Path = SCENARIO_DIR,
    today: Date | None = None,
    make_adapter: Callable[[], AuthenticatedOllamaAdapter | None] | None = None,
) -> int:
    out = out if out is not None else sys.stdout
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        selection = select_scenarios(args.scenarios, scenario_dir)
    except ScenarioError as error:
        print(f"Senaryo seçilemedi: {error}", file=out)
        return 1
    steps = sum(len(scenario.steps) for scenario in selection.values())
    print(f"Seçilen senaryolar: {', '.join(selection) or 'yok'}", file=out)
    print(f"Tahmini tur: {len(selection)} senaryo × {steps} adım × {args.runs} koşu = "
          f"{estimate_calls(selection, args.runs)} (bir tur birden çok model çağrısı yapabilir; "
          f"en çok {args.max_calls} çağrı)", file=out)
    if not args.yap:
        print("Gerçek zincir koşulmadı: para harcar, yalnız --yap ile koşar.", file=out)
        return EXIT_NOT_ASKED
    if not selection:
        print("Koşulacak senaryo yok.", file=out)
        return 1
    _keep_the_owners_save_out()
    driver = build_driver(args.max_calls, make_adapter)
    if driver is None:
        print("Koşulmadı: gerçek zincir kurulamadı (anahtar dosyası ya da AI_DND_MODEL_CHAIN yok).", file=out)
        return 1
    played = play(selection, args.runs, driver)
    if played.error:
        print(f"Koşu bozuldu: {played.error}", file=out)
        return 1
    day = today or datetime.now().astimezone().date()
    text = assemble_report(selection, played, driver, args, day)
    path = _free_path(Path(args.out), day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"Model çağrısı: {driver.calls} (sınır {args.max_calls})", file=out)
    if played.cut is not None:
        print(f"--max-calls sınırına ulaşıldı; koşu erken durdu ({played.cut}).", file=out)
    print(f"Rapor: {path}", file=out)
    return 0


def _keep_the_owners_save_out() -> None:
    """Before the API is imported: no default app (it would open the configured store) and no configured store at
    all; then the owner's local play settings, where they are not set."""
    os.environ["AI_DND_DISABLE_DEFAULT_APP"] = "1"
    os.environ.pop("AI_DND_CAMPAIGN_DB", None)
    for name, value in _PLAY_DEFAULTS.items():
        os.environ.setdefault(name, value)
    if "OLLAMA_PROXY_TOKEN" not in os.environ and _LOOPBACK_HOST.match(os.environ["OLLAMA_HOST"]):
        os.environ["OLLAMA_PROXY_TOKEN"] = "loopback"


class _CallCapReached(RuntimeError):
    pass


class RealChain:
    """The model driver for the real chain: the adapter answers every engine call of a step, in front of a counter
    that lets no call past the cap and a clock for the whole call. Its ``observe`` hears every attempt."""

    real_chain = True

    def __init__(self, max_calls: int):
        self.max_calls = max_calls
        self.adapter: AuthenticatedOllamaAdapter | None = None
        self.calls = 0
        self.refused = 0
        self.latency: list[dict[str, Any]] = []
        self.skips: Counter[tuple[str, str]] = Counter()
        self._scenario: Scenario | None = None
        self._where: str | None = None
        self.cut_at: int | None = None  # the step of the current scenario run where a call was first refused

    @property
    def capped(self) -> bool:
        return self.calls >= self.max_calls

    def begin(self, scenario: Scenario) -> None:
        self._scenario = scenario
        self.cut_at = None

    def observe(self, attempt: ChainAttempt) -> None:
        """One provider attempt (cloud from the chain's observer, local from the adapter's ledger)."""
        from api.tests.journeys.report import latency_row

        if self._where is None:
            return
        self.latency.append(latency_row(self._where, attempt))
        if attempt.outcome == "skipped":
            reason = attempt.reason or ""
            self.skips[(attempt.provider, reason if _PLAIN_REASON.fullmatch(reason) else "diğer")] += 1

    @contextmanager
    def bind(self, case: Any, step: Step) -> Iterator[None]:
        import game

        assert self.adapter is not None and self._scenario is not None
        index = next(number for number, known in enumerate(self._scenario.steps, start=1) if known is step)
        with patch.object(case.app.state, "ollama_adapter", self.adapter), self.adapter.engine_binding():
            with patch.object(game.ollama, "chat", self._counted(game.ollama.chat, index)):
                yield None

    def _counted(self, chat: Callable[..., Any], index: int) -> Callable[..., Any]:
        from api.model_chain import ChainAttempt
        from api.tests.journeys.report import latency_row
        from api.tests.journeys.runner import call_kind

        assert self._scenario is not None
        scenario_id = self._scenario.id

        def counted(*args: Any, **kwargs: Any) -> Any:
            if self.capped:
                self.refused += 1
                self.cut_at = index if self.cut_at is None else self.cut_at
                raise _CallCapReached("journey call cap reached")
            self.calls += 1
            where = f"{scenario_id} adım {index} ({call_kind(kwargs.get('format')) or 'diğer'})"
            self._where = where
            started = time.monotonic()
            outcome, reason = "answered", None
            try:
                return chat(*args, **kwargs)
            except Exception as error:
                outcome, reason = "skipped", type(error).__name__
                raise
            finally:
                self.latency.append(latency_row(where, ChainAttempt(
                    _WHOLE_CALL, outcome, reason, time.monotonic() - started, 0, 0, 0)))
                self._where = None

        return counted


class _LocalTimes:
    """The adapter's usage ledger, unchanged, with the local model's answers also told to the driver."""

    def __init__(self, ledger: Any, observe: Callable[[ChainAttempt], None]):
        self._ledger = ledger
        self._observe = observe

    def record(self, provider: str, *, input_tokens: int, output_tokens: int, thought_tokens: int = 0,
               seconds: float | None = None, outcome: str = "answered") -> None:
        from api.model_chain import ChainAttempt

        self._ledger.record(provider, input_tokens=input_tokens, output_tokens=output_tokens,
                            thought_tokens=thought_tokens, seconds=seconds, outcome=outcome)
        try:
            self._observe(ChainAttempt(_LOCAL, "answered" if outcome == "answered" else "skipped", None,
                                       float(seconds or 0.0), input_tokens, output_tokens, thought_tokens))
        except Exception:  # noqa: BLE001 - a measuring aid never reaches the turn
            pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ledger, name)


def build_driver(
    max_calls: int, make_adapter: Callable[[], AuthenticatedOllamaAdapter | None] | None = None,
) -> RealChain | None:
    """The real chain's adapter, built while the chain's ledger observer also tells the driver; None when no
    cloud chain can be built (the run would be the local model alone)."""
    from api import model_chain
    from api.ollama_adapter import AuthenticatedOllamaAdapter

    driver = RealChain(max_calls)
    writes = model_chain.ledger_observer

    def both(ledger: Any) -> Callable[[ChainAttempt], None]:
        write = writes(ledger)

        def observe(attempt: ChainAttempt) -> None:
            write(attempt)
            driver.observe(attempt)
        return observe

    with patch.object(model_chain, "ledger_observer", both):
        adapter = (make_adapter or (lambda: AuthenticatedOllamaAdapter.from_environment(use_cloud=True)))()
    if adapter is None or adapter.cloud_chain is None:
        return None
    if adapter.usage_ledger is not None:
        adapter.usage_ledger = _LocalTimes(adapter.usage_ledger, driver.observe)
    driver.adapter = adapter
    return driver


class Played:
    """Every run's step results per scenario; the one run the cap cut, if any."""

    def __init__(self) -> None:
        self.complete: dict[str, list[list[StepResult]]] = {}
        self.partial: dict[str, list[StepResult]] = {}
        self.cut: str | None = None
        self.error: str | None = None


def play(selection: Mapping[str, Scenario], runs: int, driver: RealChain) -> Played:
    """All runs, in one journey case (its temporary store and app), stopping at the first scenario after the cap."""
    from api.tests.journeys.runner import JourneyCase

    played = Played()

    class RealJourney(JourneyCase):
        async def test_real_chain(self) -> None:
            for run in range(1, runs + 1):
                for key, scenario in selection.items():
                    if driver.capped:
                        played.cut = played.cut or f"{run}. koşu, {key} başlamadan"
                        return
                    driver.begin(scenario)
                    steps = await self.run_scenario(scenario, model=driver)
                    if driver.cut_at is None:
                        played.complete.setdefault(key, []).append(list(steps))
                        continue
                    played.cut = f"{run}. koşu, {key}, adım {driver.cut_at}"
                    played.partial[key] = _cut(steps, driver.cut_at)
                    return

    result = unittest.TestResult()
    RealJourney("test_real_chain").run(result)
    problems = result.errors + result.failures
    if problems:
        # The error's type only: its message could carry anything the failing call held.
        played.error = problems[0][1].strip().splitlines()[-1].split(":", 1)[0]
    return played


def _cut(steps: Sequence[StepResult], cut_at: int) -> list[StepResult]:
    from api.tests.journeys.runner import StepResult

    return [step if step.index < cut_at else StepResult(step.index, "unreached", (_CUT,), step.items, "", 0.0)
            for step in steps]


def _passed(steps: Sequence[StepResult]) -> bool:
    statuses = {step.status for step in steps}
    return bool(steps) and not statuses & {"new_break", "known_broken", "unreached"}


def _worst(runs: Sequence[Sequence[StepResult]]) -> Sequence[StepResult]:
    """The run the report shows: the first with a new break, else the first with a known break, else the last."""
    def badness(steps: Sequence[StepResult]) -> int:
        statuses = {step.status for step in steps}
        return 2 if "new_break" in statuses else 1 if "known_broken" in statuses else 0
    worst = max(badness(steps) for steps in runs)
    return runs[-1] if worst == 0 else next(steps for steps in runs if badness(steps) == worst)


def assemble_report(selection: Mapping[str, Scenario], played: Played, driver: RealChain,
                    args: argparse.Namespace, day: Date) -> str:
    from api.tests.journeys.report import build_report, real_run_flags

    results: dict[str, Sequence[StepResult]] = {key: _worst(runs) for key, runs in played.complete.items()}
    for key, steps in played.partial.items():
        results.setdefault(key, steps)
    real_runs = {key: real_run_flags([_passed(steps) for steps in runs]) for key, runs in played.complete.items()}
    usage = None
    if driver.adapter is not None and driver.adapter.usage_ledger is not None:
        try:
            usage = driver.adapter.usage_ledger.today()
        except Exception:  # noqa: BLE001 - the report goes out without the spend table
            usage = None
    text = build_report(results, dict(selection), real_runs=real_runs, latency=driver.latency,
                        usage_today=usage, date=day.isoformat())
    return text + "\n" + _run_notes(played, driver, args) + "\n"


def _run_notes(played: Played, driver: RealChain, args: argparse.Namespace) -> str:
    done = {key: len(runs) for key, runs in played.complete.items()}
    lines = ["## Gerçek zincir koşusu", "",
             f"- İstenen koşu: {args.runs}; senaryo başına tamamlanan: "
             + (", ".join(f"{key} {count}" for key, count in done.items()) or "yok"),
             f"- Model çağrısı: {driver.calls} (sınır {args.max_calls})",
             "- Senaryo tablosu ve ham kayıt, her senaryonun en kötü koşusunu gösterir."]
    if played.cut is not None:
        lines.append(f"- --max-calls sınırına ({args.max_calls}) ulaşıldı; koşu erken durdu: {played.cut}. "
                     "Kesilen koşu, geçen koşu oranına girmez.")
    lines += ["", "### Atlanan denemeler", ""]
    if not driver.skips:
        return "\n".join(lines + ["Atlanan deneme yok."])
    lines += ["| Sağlayıcı | Neden | Kez |", "| --- | --- | --- |"]
    lines += [f"| {provider} | {reason} | {count} |" for (provider, reason), count in sorted(driver.skips.items())]
    return "\n".join(lines)


def _free_path(folder: Path, day: Date) -> Path:
    stem = f"ADIM2_RAPOR_{day.strftime('%Y%m%d')}"
    path = folder / f"{stem}.md"
    number = 2
    while path.exists():
        path = folder / f"{stem}_{number}.md"
        number += 1
    return path
