"""The real-chain journey command: the same scenario files, played in this process with the real model chain.

It spends money, so it plays only when told to (``--yap``). Without it, it prints the estimate (engine model calls,
an upper bound: two a say step, three a conversation turn) and exits with 2 before anything can reach a model or a
key. With ``--yap`` and a ``--max-calls`` below that estimate it does not start either, and exits with 3. A finished run whose report was written still exits with 4 when any
run broke a zero-tolerance state (4: sıfır tolerans ihlali). Otherwise:

- the campaigns live in the runner's temporary store; the owner's save (``AI_DND_CAMPAIGN_DB``, the local play
  database) is taken out of this process's environment first, and the API's default app is not built;
- every model call the engine makes is counted, and none is made past ``--max-calls``: the run stops at the next
  scenario and the report is still written, the cut steps marked as not run;
- a report that cannot be built or written leaves a raw record of the run (``ADIM2_HAM_<date>.txt`` in ``--out``,
  else in the temporary folder), so a paid run is never lost;
- latency comes from the chain's observer (every cloud attempt, a skipped one with its reason) and from the adapter
  (the local model's answer, written to the usage ledger, and the whole engine call), one row per attempt and step
  call, so the report shows the median and the worst of the runs;
- the report is ``report.build_report``'s, written as ``ADIM2_RAPOR_<date>.md`` into ``--out`` (never over an
  earlier one), with the run's own notes and the skipped attempts after it.

No key is read before ``--yap``, and none is printed: the report, its run notes and every printed line are scrubbed of
key-like text, and a skip reason is printed only when it is a plain code.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
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

import front_proposal
from api.tests.journeys.report import scrub
from api.tests.journeys.schema import Scenario, ScenarioError, Step, load_scenario

if TYPE_CHECKING:
    from api.model_chain import ChainAttempt
    from api.ollama_adapter import AuthenticatedOllamaAdapter
    from api.tests.journeys.runner import StepResult

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"
DEFAULT_RUNS = 3
# Ruling R20: above the core set's estimate (87 engine calls for three runs); Gemini is free, Haiku only answers when
# Gemini cannot, so the cost stays small.
DEFAULT_MAX_CALLS = 100
EXIT_NOT_ASKED = 2
EXIT_OVER_CAP = 3  # asked, but --max-calls is below the estimate: nothing started
EXIT_ZERO_TOLERANCE = 4  # the run finished and the report is written, but a zero-tolerance state broke in some run
# Engine model calls a say step makes at most: the reading (intent or front) and the narration, and in a conversation
# turn the person's reply as well. A command, a card or combat button, an undo or a reload is the engine's alone.
_SAY_CALLS = 2
_CONVERSATION_CALLS = 3

# What start_local.ps1 -LocalPlay sets for the owner's play; set here only under --yap, only when unset. The front
# reading is on in local play; its flag is set here directly, because front_proposal's local-play helper would also
# point the route log at the owner's own file.
_PLAY_DEFAULTS = {"OLLAMA_HOST": "http://127.0.0.1:11434", "AI_DND_MODEL_CHAIN": "gemini,haiku,gemma",
                  front_proposal.FLAG: "1"}
_LOOPBACK_HOST = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:|/|$)")
_PLAIN_REASON = re.compile(r"[A-Za-z0-9_]{1,40}")
_LOCAL = "yerel"
_WHOLE_CALL = "toplam"
_CUT = "--max-calls sınırı: bu adımdan itibaren model çağrısı yapılmadı; koşulmadı sayıldı"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="journey_real.py",
        description="Yolculuk senaryolarını gerçek model zinciriyle koşar (para harcar; yalnız --yap ile).",
    )
    parser.add_argument("--scenarios", default="core",
                        help="core (real_chain_core işaretliler), all ya da virgülle kimlikler")
    parser.add_argument("--runs", type=_positive, default=DEFAULT_RUNS, help="her senaryo kaç kez koşar")
    parser.add_argument("--max-calls", type=_positive, default=DEFAULT_MAX_CALLS,
                        help="motorun en çok kaç model çağrısı yapacağı (aşılmaz; tahminden küçükse koşu başlamaz); "
                             "bir motor çağrısı zincirde birden çok sağlayıcı denemesi olabilir, sağlayıcı isteği "
                             "sayısı bundan fazla olabilir")
    parser.add_argument("--yap", action="store_true", help="gerçekten koş (para harcar)")
    parser.add_argument("--out", type=Path, default=None,
                        help="raporun yazılacağı klasör (--yap ile zorunlu)")
    return parser


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    return build_parser().parse_args(list(argv))


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
    """Engine model calls for every run, an upper bound (Ruling R20): see ``_step_calls``."""
    return sum(_step_calls(step) for scenario in scenarios.values() for step in scenario.steps) * runs


def _step_calls(step: Step) -> int:
    """A say step makes two engine calls, three when it is a conversation turn (the step expects an open talk or
    scripts the person's reply); every other step is played by the engine alone."""
    if step.say is None:
        return 0
    mode = step.expect.get("kip")
    talking = (isinstance(mode, Mapping) and mode.get("active") is True) or "spoken" in (step.script or {})
    return _CONVERSATION_CALLS if talking else _SAY_CALLS


def main(
    argv: Sequence[str] | None = None,
    *,
    out: IO[str] | None = None,
    scenario_dir: Path = SCENARIO_DIR,
    today: Date | None = None,
    make_adapter: Callable[[], AuthenticatedOllamaAdapter | None] | None = None,
) -> int:
    out = out if out is not None else sys.stdout

    def say(text: str) -> None:
        print(scrub(text), file=out)

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        selection = select_scenarios(args.scenarios, scenario_dir)
    except ScenarioError as error:
        say(f"Senaryo seçilemedi: {error}")
        return 1
    steps = sum(len(scenario.steps) for scenario in selection.values())
    estimate = estimate_calls(selection, args.runs)
    say(f"Seçilen senaryolar: {', '.join(selection) or 'yok'}")
    say(f"Tahmini motor çağrısı: {len(selection)} senaryo, {steps} adım, {args.runs} koşu: {estimate} "
        f"(üst sınır: say adımı başına {_SAY_CALLS}, konuşma turunda {_CONVERSATION_CALLS}; öteki adımları motor "
        f"kendisi oynar; sınır --max-calls {args.max_calls})")
    if estimate > args.max_calls:
        say(f"--max-calls {args.max_calls} tahminden ({estimate}) küçük: --yap ile de koşmaz (çıkış {EXIT_OVER_CAP}).")
    if not args.yap:
        say("Gerçek zincir koşulmadı: para harcar, yalnız --yap ile koşar.")
        return EXIT_NOT_ASKED
    if not selection:
        say("Koşulacak senaryo yok.")
        return 1
    if estimate > args.max_calls:
        say(f"Koşulmadı: --max-calls {args.max_calls}, tahmini {estimate} motor çağrısından küçük; "
            f"en az --max-calls {estimate} ver.")
        return EXIT_OVER_CAP
    if args.out is None:
        say("Koşulmadı: raporun klasörü yok; --out <klasör> ver.")
        return 1
    try:
        Path(args.out).mkdir(parents=True, exist_ok=True)
    except OSError as error:
        say(f"Koşulmadı: rapor klasörü açılamadı ({type(error).__name__}).")
        return 1
    _keep_the_owners_save_out()
    driver = build_driver(args.max_calls, make_adapter)
    if driver is None:
        say("Koşulmadı: gerçek zincir kurulamadı (anahtar dosyası ya da AI_DND_MODEL_CHAIN yok).")
        return 1
    played = play(selection, args.runs, driver)
    if played.error:
        say(f"Koşu bozuldu: {played.error}")
        return 1
    day = today or datetime.now().astimezone().date()
    say(f"Model çağrısı: {driver.calls} (sınır {args.max_calls})")
    if played.cut is not None:
        say(f"--max-calls sınırına ulaşıldı; koşu erken durdu ({played.cut}).")
    try:
        text = assemble_report(selection, played, driver, args, day)
        path = _free_path(Path(args.out), f"ADIM2_RAPOR_{day.strftime('%Y%m%d')}", ".md")
        path.write_text(text, encoding="utf-8")
    except Exception as error:  # noqa: BLE001 - the run is paid for: its raw record must survive a report bug
        say(f"Rapor yazılamadı ({type(error).__name__}); koşunun ham kaydı bırakılıyor.")
        backup = _raw_backup(played, driver, args, day)
        say(f"Ham kayıt: {backup}" if backup is not None else "Ham kayıt da yazılamadı.")
        return 1
    say(f"Rapor: {path}")
    breaks = zero_tolerance_breaks(played)
    if breaks:
        say(f"Sıfır tolerans ihlali var ({len(breaks)}); çıkış {EXIT_ZERO_TOLERANCE}.")
        return EXIT_ZERO_TOLERANCE
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
    elif result.skipped or result.testsRun != 1:
        played.error = "koşu atlandı"
    return played


def zero_tolerance_breaks(played: Played) -> list[str]:
    """Every zero-tolerance failure of every step of every run (complete and cut): one break closes the gate, so a
    run that only "mostly" held is still listed (tasarım karar 63)."""
    runs = [(key, number, steps) for key, all_runs in played.complete.items()
            for number, steps in enumerate(all_runs, start=1)]
    runs += [(key, len(played.complete.get(key, ())) + 1, steps) for key, steps in played.partial.items()]
    return [f"{key} koşu {number} adım {step.index}: {failure}"
            for key, number, steps in runs for step in steps for failure in step.failures
            if failure.startswith("sıfır tolerans: ")]


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
    # The notes name scenarios and the cut too, so the whole text is scrubbed, not the report part alone.
    breaks = zero_tolerance_breaks(played)
    section = "## Sıfır tolerans ihlalleri\n" + ("\n".join(f"- {line}" for line in breaks) if breaks else "yok")
    return scrub(text + "\n" + section + "\n\n" + _run_notes(selection, played, driver, args) + "\n")


def _run_notes(selection: Mapping[str, Scenario], played: Played, driver: RealChain,
               args: argparse.Namespace) -> str:
    done = {key: len(runs) for key, runs in played.complete.items()}
    lines = ["## Gerçek zincir koşusu", "",
             f"- İstenen koşu: {args.runs}; senaryo başına tamamlanan: "
             + (", ".join(f"{key} {count}" for key, count in done.items()) or "yok"),
             f"- Model çağrısı: {driver.calls} (sınır {args.max_calls})",
             "- Senaryo tablosu ve ham kayıt, her senaryonun en kötü koşusunu gösterir."]
    if played.cut is not None:
        lines.append(f"- --max-calls sınırına ({args.max_calls}) ulaşıldı; koşu erken durdu: {played.cut}. "
                     "Kesilen koşu, geçen koşu oranına girmez.")
    marked = [key for key, scenario in selection.items() if any(step.known_broken for step in scenario.steps)]
    if marked:
        lines.append("- Bir koşu, bilinen kırık bir adımı kırıldığında da geçmemiş sayılır. Oranı yalnız zinciri "
                     "değil motorun bilinen kırığını da gösteren, bilinen kırık işaretli adımı olan senaryolar: "
                     f"{', '.join(marked)}.")
    lines += ["", "### Atlanan denemeler", ""]
    if not driver.skips:
        return "\n".join(lines + ["Atlanan deneme yok."])
    lines += ["| Sağlayıcı | Neden | Kez |", "| --- | --- | --- |"]
    lines += [f"| {provider} | {reason} | {count} |" for (provider, reason), count in sorted(driver.skips.items())]
    return "\n".join(lines)


def _raw_backup(played: Played, driver: RealChain, args: argparse.Namespace, day: Date) -> Path | None:
    """The run's step results as plain lines, in ``--out`` or else in the temporary folder; None if neither takes it."""
    lines = ["# Adım 2 ham koşu kaydı (rapor yazılamadı)", "",
             f"Model çağrısı: {driver.calls} (sınır {args.max_calls})"]
    if played.cut is not None:
        lines.append(f"Koşu erken durdu: {played.cut}")
    runs = [(f"{key}, {number}. koşu", steps) for key, all_runs in played.complete.items()
            for number, steps in enumerate(all_runs, start=1)]
    runs += [(f"{key}, kesilen koşu", steps) for key, steps in played.partial.items()]
    for title, steps in runs:
        lines += ["", f"{title}:"]
        lines += [f"- adım {step.index}: {step.status}" + (f": {'; '.join(step.failures)}" if step.failures else "")
                  for step in steps]
    text = scrub("\n".join(lines)) + "\n"
    name = f"ADIM2_HAM_{day.strftime('%Y%m%d')}"
    for folder in (Path(args.out), Path(tempfile.gettempdir())):
        try:
            path = _free_path(folder, name, ".txt")
            path.write_text(text, encoding="utf-8")
            return path
        except OSError:
            continue
    return None


def _free_path(folder: Path, stem: str, suffix: str) -> Path:
    """``<stem><suffix>`` in the folder, or the first ``<stem>_<n><suffix>`` free: never over an earlier file."""
    path = folder / f"{stem}{suffix}"
    number = 2
    while path.exists():
        path = folder / f"{stem}_{number}{suffix}"
        number += 1
    return path
