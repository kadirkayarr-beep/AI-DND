"""The Turkish journey report: what passed, what is known broken (by item number), what is new.

It only formats. The caller passes the step results of each scenario, the loaded scenarios, and optional
measurements as plain mappings (so this module does not depend on the runner's model driver or on ``ModelChain``):

- ``real_runs``: scenario id -> one entry per real-chain run, ``1`` when that run passed and ``0`` when it did not
  (``real_run_flags`` makes that list from booleans);
- ``latency``: rows ``{"step", "provider", "seconds"}``, one per provider attempt, skipped ones included because a
  skipped try still cost its seconds (``latency_row`` makes a row from a ``ChainAttempt``);
- ``usage_today``: provider -> ``{"calls", "input", "output", "thought", "seconds"}`` (``UsageLedger.today()``).

The headline counts use the rule of ``runner.summary_line`` (a new break beats a known break, which beats a pass),
with one deliberate difference: a scenario with no results, or only unreached steps, is counted as "koşulmadı"
instead of as passed.

Nothing here reads a key file; any key-like text that reaches a step's narration or failure is scrubbed from the
finished report.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from api.model_chain import ChainAttempt
    from api.tests.journeys.runner import StepResult
    from api.tests.journeys.schema import Scenario

# Known breaks are grouped by kind. A kind is told by the scenario file's number; a scenario not listed here is
# grouped under "Diğer" (a new scenario file shows up there until it is added).
_KINDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Para ve alışveriş", ("01", "01b", "02", "12", "13", "13b", "14", "14b", "14c", "16", "23", "25", "26", "27")),
    # The owner's 19-item test: money paid or earned by the wrong move, and the quest record that goes with it.
    # 36: the messenger chain (3a), money and records through a delivery, a broken seal and the word it sends.
    # 41: a job heard in the street: its trail, taken only from its owner, undo and reload.
    ("Para ve kayıt", ("17", "18", "18b", "18c", "18d", "19", "19b", "19c", "19d", "19e", "29", "36", "41", "45")),
    ("Oda, uyku ve çıkış", ("03", "07", "39")),
    ("Eşya, silah ve tüketim", ("04", "04b", "05", "05b", "05c", "28", "30", "43")),
    ("Savaş eylemleri", ("06", "20", "21", "22", "22b", "42", "44", "46")),
    ("Konuşma kipi", ("08", "08b")),
    ("Kaçış, ölüm ve sonuçları", ("09a", "09b", "09c", "09d", "10", "15", "32", "33")),
    ("Kişisel hafıza", ("24", "24r")),
    ("Geri al ve yenileme", ("11",)),
    # The scene's own happening (joined, undone, run out) and what a new campaign's first minutes show.
    ("Sahne olayları ve açılış", ("31", "31b", "36a", "36b")),
    ("Anlatı biçimi", ("35", "38")),
    # The way to a person someone named: their place, and where the town says they are.
    ("Yol ve hedef", ("37", "40")),
    # A spell the engine does not resolve with dice: a narrative fact, or the "not in the engine yet" line (4C.5).
    ("Büyü anlatısı", ("49",)),
    # An act the dice settle (a steal, a scare) shows its dice card whatever the model's reading says; a look-over is told.
    ("Zar ve beceri kontrolleri", ("50", "50b", "50c", "50d")),
)
_OTHER_KIND = "Diğer"
_NUMBER = re.compile(r"^(\d+[a-z]?)_")
_KEY_LIKE = re.compile(r"AIza\S*|sk-ant-\S*|sk-[A-Za-z0-9_-]{16,}")
_REDACTED = "[gizlendi]"
_RAW_LOG_SCENARIOS = 3
_RUNS_NEEDED = 3


def build_report(
    results: Mapping[str, Sequence[StepResult]],
    scenarios: Mapping[str, Scenario],
    *,
    real_runs: Mapping[str, Sequence[int]] | None = None,
    latency: Sequence[Mapping[str, Any]] | None = None,
    usage_today: Mapping[str, Mapping[str, float]] | None = None,
    date: str,
) -> str:
    unknown = sorted(set(results) - set(scenarios))
    if unknown:
        raise ValueError(f"sonucu olup senaryosu verilmeyen kimlik: {', '.join(unknown)}")
    rows = [_Row(scenario, results.get(key, ())) for key, scenario in sorted(scenarios.items())]
    parts = [
        f"# Adım 2 raporu ({date})",
        _counts(rows),
        _scenario_table(rows),
        _known_breaks(rows),
        _real_chain(rows, real_runs or {}),
        _latency(latency),
        _spend(usage_today),
        _raw_log(rows),
    ]
    return scrub("\n\n".join(parts)) + "\n"


def scrub(text: str) -> str:
    """The text with every key-like run replaced; a caller that adds text after the report runs it through here."""
    return _KEY_LIKE.sub(_REDACTED, text)


def latency_row(step: str, attempt: ChainAttempt) -> dict[str, Any]:
    """The latency row for one provider attempt of one step (skipped attempts count: they cost their seconds)."""
    return {"step": step, "provider": attempt.provider, "seconds": attempt.seconds}


def real_run_flags(passed: Sequence[bool]) -> list[int]:
    """The ``real_runs`` entry for one scenario: ``1`` for a run that passed, ``0`` for one that did not."""
    if any(type(run) is not bool for run in passed):
        raise ValueError(f"gerçek zincir koşusu True ya da False olmalı: {list(passed)}")
    return [int(run) for run in passed]


class _Row:
    """One scenario with its step results and its one outcome."""

    def __init__(self, scenario: Scenario, steps: Sequence[StepResult]):
        self.scenario = scenario
        self.steps = tuple(steps)
        statuses = {step.status for step in self.steps}
        if "new_break" in statuses:
            self.outcome = "new_break"
        elif "known_broken" in statuses:
            self.outcome = "known_broken"
        elif not self.steps or statuses == {"unreached"}:
            self.outcome = "not_run"
        else:
            self.outcome = "pass"
        self.stale = [step for step in self.steps if step.status == "marker_stale"]
        self.known = [step for step in self.steps if step.status == "known_broken"]
        self.passed = sum(step.status in ("pass", "marker_stale") for step in self.steps)

    @property
    def items(self) -> list[int]:
        return sorted({item for step in self.known for item in step.items})

    @property
    def real_chain_pending(self) -> int:
        steps = self.scenario.steps
        return sum(1 for result in self.steps if result.status == "unreached"
                   and 0 < result.index <= len(steps) and steps[result.index - 1].real_chain)


def _counts(rows: Sequence[_Row]) -> str:
    count = {name: sum(row.outcome == name for row in rows) for name in ("pass", "known_broken", "new_break", "not_run")}
    line = f"**{count['pass']} geçti, {count['known_broken']} bilinen kırık, {count['new_break']} yeni kırık**"
    notes = []
    stale = sum(len(row.stale) for row in rows)
    if stale:
        notes.append(f"{stale} adımda işaret kaldırılmalı (adım geçiyor ama bilinen kırık işaretli)")
    if count["not_run"]:
        notes.append(f"{count['not_run']} koşulmadı")
    pending = sum(row.real_chain_pending for row in rows)
    if pending:
        notes.append(f"{pending} adım yalnız gerçek zincirde koşar")
    return line + "".join(f"\n\n- {note}" for note in notes)


def _scenario_table(rows: Sequence[_Row]) -> str:
    lines = ["## Senaryolar", "", "| Senaryo | Başlık | Sonuç | Madde | Adım |", "| --- | --- | --- | --- | --- |"]
    for row in rows:
        scenario = row.scenario
        lines.append("| " + " | ".join([
            _cell(scenario.id), _cell(scenario.title), _outcome(row), _cell(_items(row.items)),
            f"{row.passed}/{len(scenario.steps)}",
        ]) + " |")
    return "\n".join(lines)


def _outcome(row: _Row) -> str:
    if row.outcome == "new_break":
        return "YENİ KIRIK (sıfır tolerans)" if row.scenario.zero_tolerance else "YENİ KIRIK"
    if row.outcome == "known_broken":
        return "bilinen kırık"
    if row.outcome == "not_run":
        return "koşulmadı"
    return "geçti, işaret kaldırılmalı" if row.stale else "geçti"


def _known_breaks(rows: Sequence[_Row]) -> str:
    lines = ["## Bilinen kırıklar", ""]
    groups: dict[str, list[_Row]] = {}
    for row in rows:
        if row.known:
            groups.setdefault(_kind(row.scenario.id), []).append(row)
    if not groups:
        return "\n".join(lines + ["Bilinen kırık yok."])
    order = [name for name, _ in _KINDS] + [_OTHER_KIND]
    for kind in order:
        if kind not in groups:
            continue
        lines += [f"### {kind}", ""]
        for row in groups[kind]:
            for step in row.known:
                reason = "; ".join(step.failures) if step.failures else "neden kaydedilmemiş"
                lines.append(f"- {_items(step.items, 'madde')}: {row.scenario.id}, adım {step.index}: "
                             f"{_oneline(reason)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _real_chain(rows: Sequence[_Row], real_runs: Mapping[str, Sequence[int]]) -> str:
    lines = ["## Gerçek zincir", ""]
    for key, runs in sorted(real_runs.items()):
        if any(run not in (0, 1) for run in runs):
            raise ValueError(f"{key}: gerçek zincir koşusu 1 (geçti) ya da 0 (geçmedi) olmalı: {list(runs)}")
    entries = [f"- {key}: {len(runs)} üzerinden {sum(runs)}"
               + (f" (eksik: {_RUNS_NEEDED} koşu beklenir)" if len(runs) < _RUNS_NEEDED else "")
               for key, runs in sorted(real_runs.items()) if runs]
    waiting = [row.scenario.id for row in rows
               if row.scenario.real_chain_core and not real_runs.get(row.scenario.id)]
    lines += entries
    if waiting:
        lines.append(f"- Çekirdek senaryolar, gerçek zincirde koşulmadı ({_RUNS_NEEDED} koşu beklenir): "
                     + ", ".join(waiting))
    if not entries:
        lines += ["", "Gerçek zincir koşulmadı."] if waiting else ["Gerçek zincir koşulmadı."]
    return "\n".join(lines)


def _latency(latency: Sequence[Mapping[str, Any]] | None) -> str:
    lines = ["## Gecikme", ""]
    if not latency:
        return "\n".join(lines + ["Gecikme kaynağı bulunamadı: gerçek zincirden sağlayıcı süresi kaydı yok."])
    grouped: dict[tuple[str, str], list[float]] = {}
    for row in latency:
        try:
            seconds = row["seconds"]
            key = (str(row["step"]), str(row["provider"]))
        except KeyError as error:
            raise ValueError(f"gecikme satırında {error.args[0]} yok: {dict(row)}") from None
        if type(seconds) not in (int, float) or seconds < 0:
            raise ValueError(f"gecikme satırında saniye sayı olmalı: {dict(row)}")
        grouped.setdefault(key, []).append(float(seconds))
    lines += ["| Adım | Sağlayıcı | Çağrı | Ortanca sn | En kötü sn |", "| --- | --- | --- | --- | --- |"]
    for (step, provider), values in sorted(grouped.items(), key=lambda item: -max(item[1])):
        lines.append(f"| {_cell(step)} | {_cell(provider)} | {len(values)} | "
                     f"{_seconds(statistics.median(values))} | {_seconds(max(values))} |")
    return "\n".join(lines)


def _spend(usage: Mapping[str, Mapping[str, float]] | None) -> str:
    lines = ["## Harcama", ""]
    if not usage:
        return "\n".join(lines + ["Bugünün kullanım dosyasında kayıt yok."])
    lines += ["| Sağlayıcı | Çağrı | Girdi | Çıktı | Düşünme | Saniye |", "| --- | --- | --- | --- | --- | --- |"]
    for provider, row in sorted(usage.items()):
        lines.append("| " + " | ".join([
            _cell(provider), *(_number(row.get(name, 0)) for name in ("calls", "input", "output", "thought")),
            _seconds(row.get("seconds", 0)),
        ]) + " |")
    return "\n".join(lines)


def _raw_log(rows: Sequence[_Row]) -> str:
    lines = ["## Ham adım kaydı", ""]
    sample = _sample(rows)
    # every scenario that breaks the gate is shown, not only the one the three-scenario sample picked
    chosen = sorted({*sample, *(row for row in rows if row.outcome == "new_break")}, key=lambda row: row.scenario.id)
    if not chosen:
        return "\n".join(lines + ["Kaydedilecek adım yok."])
    for row in chosen:
        lines += [f"### {row.scenario.id}", ""]
        for result in row.steps:
            lines.append(f"{result.index}. {_action(row.scenario, result.index)} -> {result.status} "
                         f"({_seconds(result.seconds)} sn)")
            lines += [f"   - hata: {_oneline(failure)}" for failure in result.failures]
            if result.narration:
                lines.append(f"   - anlatı: {_oneline(result.narration)}")
            if result.reading and result.status in ("new_break", "known_broken"):
                lines.append(f"   - ön okuma: {_oneline(result.reading)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _sample(rows: Sequence[_Row]) -> list[_Row]:
    """Three scenarios for the owner to check by hand: a new break first, then a known break, then a passing
    zero-tolerance one, then any passing one, then whatever is left (scenario id order)."""
    ran = [row for row in rows if row.steps]
    picks = (
        lambda row: row.outcome == "new_break",
        lambda row: row.outcome == "known_broken",
        lambda row: row.outcome == "pass" and row.scenario.zero_tolerance,
        lambda row: row.outcome == "pass",
        lambda row: True,
    )
    chosen: list[_Row] = []
    for pick in picks:
        for row in ran:
            if len(chosen) < _RAW_LOG_SCENARIOS and pick(row) and row not in chosen:
                chosen.append(row)
                break
    for row in ran:
        if len(chosen) < _RAW_LOG_SCENARIOS and row not in chosen:
            chosen.append(row)
    return sorted(chosen, key=lambda row: row.scenario.id)


def _action(scenario: Scenario, index: int) -> str:
    if not 0 < index <= len(scenario.steps):
        return "(adım senaryoda yok)"
    step = scenario.steps[index - 1]
    for label in ("say", "command", "economic_action", "combat_action", "ambient"):
        value = getattr(step, label)
        if value:
            return f"{label}: {_oneline(str(value))}"
    return "undo" if step.undo else "reload" if step.reload else "(eylem yok)"


def _kind(scenario_id: str) -> str:
    match = _NUMBER.match(scenario_id)
    number = match.group(1) if match else ""
    for name, numbers in _KINDS:
        if number in numbers:
            return name
    return _OTHER_KIND


def _items(items: Sequence[int], prefix: str = "") -> str:
    if not items:
        return "-"
    return (f"{prefix} " if prefix else "") + ", ".join(str(item) for item in items)


def _cell(text: Any) -> str:
    return _oneline(str(text)).replace("|", "\\|")


def _oneline(text: str) -> str:
    return " ".join(text.split())


def _seconds(value: float) -> str:
    return f"{value:.2f}".replace(".", ",") if value != round(value, 1) else f"{value:.1f}".replace(".", ",")


def _number(value: float) -> str:
    return str(int(value)) if float(value) == int(value) else f"{value:.2f}".replace(".", ",")
