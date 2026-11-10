"""The journey scenario file: one strict loader and one expectation checker.

A typo in a scenario file must never turn into a quietly green journey, so the
loader rejects every key it does not know (scenario, step and expect level, and
duplicate JSON keys). What lives inside ``setup`` is the runner's business and is
validated there, when the setup is applied.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EXPECT_KEYS = frozenset(
    {
        "kese",
        "envanter",
        "oda",
        "kip",
        "savas",
        "konum",
        "hp",
        "kart",
        "tezgah",
        "kisi_kese",
        "olu",
        "yasak_metin",
        "gerekli_metin",
        "anlaticiya_giden",
        "cephane",
        "hareket",
        "xp",
        "saat",
        "gorev",
        "karsi_saldiri",
        "yuva",
        "esya_sayisi",
        "anlatilan",
        "konusmaya_giden",
        "inkar",
        "gunluk",
        "elinde",
        "olay",
        "zirh",
        "varis",
    }
)

# ``undo`` takes back the last turn through the product's undo route; ``reload`` reads the campaign back from
# its save in a fresh session manager (a restart). Both take only ``true``. ``ambient`` clicks the scene's current
# ambient event through the product's route: ``{"action": "interact" | "observe"}``.
ACTION_KEYS = ("say", "command", "economic_action", "combat_action", "undo", "reload", "ambient")
_SCENARIO_KEYS = frozenset(
    {"id", "title", "source_items", "zero_tolerance", "real_chain_core", "setup", "steps"}
)
_SCENARIO_REQUIRED = ("id", "title", "steps")
_STEP_KEYS = frozenset(
    {*ACTION_KEYS, "konus", "script", "expect", "sifir_tolerans", "known_broken", "broken_because", "real_chain", "independent"}
)
_TEXT_ACTIONS = ("say", "command")
_DICT_ACTIONS = ("economic_action", "combat_action", "ambient")
_AMBIENT_ACTIONS = ("interact", "observe")
_TRUE_ACTIONS = ("undo", "reload")

# Expectations compared as a subset when both sides are mappings: the step names
# only the fields it cares about (the observed card, counter offer, mode or purse
# list carries more; ``gorev`` may name only ``aktif`` when a row's title is drawn at random).
_SUBSET_KEYS = frozenset({"kip", "kart", "tezgah", "kisi_kese", "gorev", "olay", "varis"})
_TEXT_CHECKS = frozenset({"yasak_metin", "gerekli_metin"})


class ScenarioError(ValueError):
    """A scenario file (or an expectation) the journey tests cannot trust."""


def _integer(value: Any) -> bool:
    return type(value) is int


def _count_map(value: Any) -> bool:
    """Name to a count: the inventory needs at least one of each name it lists, a counter may say 0."""
    return isinstance(value, dict) and all(isinstance(name, str) and name and type(count) is int and count >= 0
                                           for name, count in value.items())


def _needles(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value)
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item for item in value)


def _or_none(rule):
    return lambda value: value is None or rule(value)


def _filled_mapping(value: Any) -> bool:
    """A subset match: an empty mapping would match anything, so it says nothing."""
    return isinstance(value, dict) and bool(value)


# What each expect key's value may be, so a wrong type fails when the file loads (in Turkish), never at check time.
EXPECT_VALUE_RULES = {
    "kese": (_integer, "tam sayı (bakır)"),
    "hp": (_integer, "tam sayı"),
    "xp": (_integer, "tam sayı"),
    "saat": (_integer, "tam sayı"),
    "karsi_saldiri": (_integer, "tam sayı"),
    "esya_sayisi": (_integer, "tam sayı"),
    "hareket": (_or_none(_integer), "tam sayı ya da null"),
    "oda": (lambda value: isinstance(value, bool), "true ya da false"),
    "savas": (lambda value: isinstance(value, bool), "true ya da false"),
    "envanter": (lambda value: _count_map(value) and all(count > 0 for count in value.values()),
                 "ad -> 1 ya da daha büyük adet nesnesi"),
    "cephane": (_count_map, "tür -> 0 ya da daha büyük sayı nesnesi"),
    "kisi_kese": (lambda value: _filled_mapping(value) and all(type(cp) is int for cp in value.values()),
                  "boş olmayan kişi -> bakır nesnesi"),
    "gorev": (_filled_mapping, "boş olmayan nesne"),
    "kip": (_or_none(_filled_mapping), "boş olmayan nesne ya da null"),
    "kart": (_or_none(_filled_mapping), "boş olmayan nesne ya da null"),
    "tezgah": (_or_none(_filled_mapping), "boş olmayan nesne ya da null"),
    "yuva": (_or_none(lambda value: isinstance(value, dict)), "nesne ya da null"),
    "konum": (_or_none(lambda value: isinstance(value, str) and bool(value)), "boş olmayan metin ya da null"),
    "olu": (_or_none(lambda value: isinstance(value, str) and bool(value)), "boş olmayan metin ya da null"),
    "yasak_metin": (_needles, "boş olmayan metin ya da boş olmayan metin listesi"),
    "gerekli_metin": (_needles, "boş olmayan metin ya da boş olmayan metin listesi"),
    "anlaticiya_giden": (_needles, "boş olmayan metin ya da boş olmayan metin listesi"),
    "konusmaya_giden": (_needles, "boş olmayan metin ya da boş olmayan metin listesi"),
    "inkar": (lambda value: isinstance(value, bool), "true ya da false"),
    "gunluk": (lambda value: _journal_rule(value),
               "sayac/suren/biten/iz/iz_sayisi alanlarından yalnız bilinenleri taşıyan, boş olmayan nesne"),
    "elinde": (_or_none(lambda value: isinstance(value, str) and bool(value)), "boş olmayan metin ya da null"),
    "olay": (lambda value: _event_rule(value),
             "var/tiklanabilir (true ya da false) ve neden (boş olmayan metin) alanlarından yalnız bilinenleri taşıyan, boş olmayan nesne"),
    "zirh": (_integer, "tam sayı"),
    "varis": (lambda value: _varis_rule(value),
              "cagri (tam sayı) ve kaynak (model, python ya da null) alanlarından yalnız bilinenleri taşıyan, boş olmayan nesne"),
    "anlatilan": (lambda value: _filled_mapping(value) and all(isinstance(npc, str) and npc and _needles(needles)
                                                               for npc, needles in value.items()),
                  "boş olmayan kişi -> boş olmayan metin (listesi) nesnesi"),
}


_VARIS_KEYS = frozenset({"cagri", "kaynak"})


def _varis_rule(value: Any) -> bool:
    """``varis``: the step's arrival narration: how many model calls it made and whose text won (null: none was said)."""
    return (_filled_mapping(value) and not set(value) - _VARIS_KEYS
            and ("cagri" not in value or _integer(value["cagri"]))
            and ("kaynak" not in value or value["kaynak"] in ("model", "python", None)))


_EVENT_KEYS = frozenset({"var", "tiklanabilir", "neden"})


def _event_rule(value: Any) -> bool:
    """``olay``: the scene's ambient event as the API shows it: is there one, may it be clicked, and why not."""
    if not _filled_mapping(value) or set(value) - _EVENT_KEYS:
        return False
    if not all(isinstance(value[key], bool) for key in ("var", "tiklanabilir") if key in value):
        return False
    return not ("neden" in value and not (isinstance(value["neden"], str) and value["neden"]))


_JOURNAL_KEYS = frozenset({"sayac", "suren", "biten", "iz", "iz_sayisi"})
_TRAIL_KEYS = frozenset({"ne", "nerede", "kaynak", "izlendi"})


def _journal_rule(value: Any) -> bool:
    """``gunluk``: a filled mapping of the journal fields; counts are plain non-negative numbers, ``suren``/``biten``
    lists of non-empty needles, ``iz`` a list of filled trail rows (``izlendi`` true or false)."""
    if not _filled_mapping(value) or set(value) - _JOURNAL_KEYS:
        return False
    for key in ("sayac", "iz_sayisi"):
        if key in value and not (_integer(value[key]) and value[key] >= 0):
            return False
    for key in ("suren", "biten"):
        if key in value and not (isinstance(value[key], list)
                                 and all(isinstance(item, str) and item for item in value[key])):
            return False
    if "iz" in value:
        trails = value["iz"]
        if not isinstance(trails, list):
            return False
        for row in trails:
            if not _filled_mapping(row) or set(row) - _TRAIL_KEYS:
                return False
            if not all(isinstance(row[key], str) and row[key] for key in ("ne", "nerede", "kaynak") if key in row):
                return False
            if "izlendi" in row and not isinstance(row["izlendi"], bool):
                return False
    return True


@dataclass(frozen=True)
class Step:
    say: str | None
    command: str | None
    economic_action: dict | None
    combat_action: dict | None
    script: dict | None
    expect: dict
    known_broken: tuple[int, ...]
    real_chain: bool
    independent: bool
    undo: bool = False
    reload: bool = False
    # The ambient click: ``{"action": "interact" | "observe"}`` against the scene's current event.
    ambient: dict | None = None
    # Ruling R19: substrings, one of which every failure of a marked step must hold; empty means not named.
    broken_because: tuple[str, ...] = ()
    # The person a ``say`` line is spoken to in say mode (the turn's ``interaction_mode: say`` and ``target_id``).
    konus: str | None = None
    # Allowed states, any one of which the step's end state must match (zero tolerance, tasarım karar 63).
    sifir_tolerans: list = field(default_factory=list)


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    source_items: tuple[int, ...]
    zero_tolerance: bool
    real_chain_core: bool
    setup: dict
    steps: tuple[Step, ...]


def load_scenario(path: Path) -> Scenario:
    path = Path(path)
    where = path.name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ScenarioError(f"{where}: dosya okunamadı ({type(error).__name__})") from error
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except ValueError as error:
        raise ScenarioError(f"{where}: geçerli JSON değil ({error})") from error
    if not isinstance(data, dict):
        raise ScenarioError(f"{where}: en üst düzey bir nesne olmalı")

    _reject_unknown(data, _SCENARIO_KEYS, where, "senaryo")
    for key in _SCENARIO_REQUIRED:
        if key not in data:
            raise ScenarioError(f"{where}: '{key}' anahtarı zorunlu")

    zero_tolerance = _boolean(data, "zero_tolerance", where)
    raw_steps = data["steps"]
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ScenarioError(f"{where}: 'steps' boş olmayan bir liste olmalı")
    steps = tuple(
        _load_step(raw, f"{where}, adım {number}", zero_tolerance)
        for number, raw in enumerate(raw_steps, start=1)
    )
    setup = data.get("setup", {})
    if not isinstance(setup, dict):
        raise ScenarioError(f"{where}: 'setup' bir nesne olmalı")
    scenario_id = _text(data, "id", where)
    if scenario_id != path.stem:
        raise ScenarioError(f"{where}: 'id' dosya adıyla aynı olmalı: id {scenario_id}, dosya {path.stem}")
    return Scenario(
        id=scenario_id,
        title=_text(data, "title", where),
        source_items=_integers(data, "source_items", where),
        zero_tolerance=zero_tolerance,
        real_chain_core=_boolean(data, "real_chain_core", where),
        setup=setup,
        steps=steps,
    )


def check_expect(expected: Mapping, observed: Mapping) -> list[str]:
    """Turkish mismatch messages, one per failed expectation; empty means it passed.

    Only keys present in ``expected`` are checked. A key the schema does not know
    is an error, not a pass.
    """
    unknown = sorted(set(expected) - EXPECT_KEYS)
    if unknown:
        raise ScenarioError(f"bilinmeyen expect anahtarı: {', '.join(unknown)}")
    problems: list[str] = []
    for key in expected:
        want = expected[key]
        if key in _TEXT_CHECKS:
            problems.extend(_check_text(key, want, observed.get("narration")))
        elif key == "anlaticiya_giden":
            problems.extend(_check_told(want, observed.get(key)))
        elif key == "konusmaya_giden":
            problems.extend(_check_spoken_to(want, observed.get(key)))
        elif key == "anlatilan":
            problems.extend(_check_kept(want, observed.get(key)))
        elif key == "gunluk":
            problems.extend(_check_journal(want, observed.get(key)))
        elif key in _SUBSET_KEYS and isinstance(want, Mapping) and isinstance(
            observed.get(key), Mapping
        ):
            problems.extend(_check_subset(key, want, observed[key]))
        elif key not in observed or observed[key] != want:
            problems.append(_mismatch(key, want, observed.get(key)))
    return problems


def check_invariant(alternatives: Sequence[Mapping], seen: Mapping) -> list[str]:
    """Zero tolerance: the state must match at least one allowed state; otherwise one error naming each state's misses."""
    if any(not check_expect(alternative, seen) for alternative in alternatives):
        return []
    return ["sıfır tolerans: izinli durumların hiçbiri tutmadı ("
            + " | ".join("; ".join(check_expect(alt, seen)) for alt in alternatives) + ")"]


def _check_journal(want: Mapping, seen: Any) -> list[str]:
    """``gunluk``: partial match on the one quest-log view. ``suren``/``biten`` have the same length as expected and each
    wanted text sits (casefold) in the observed text at that place; ``iz`` is an in-order subsequence of trail rows, but an
    expected empty list means no trail at all (an empty subsequence is in every list)."""
    if not isinstance(seen, Mapping):
        return ["gunluk: gözlenemedi (API yanıtında quest_log yok)"]
    problems = []
    if "sayac" in want and seen.get("sayac") != want["sayac"]:
        problems.append(_mismatch("gunluk.sayac", want["sayac"], seen.get("sayac")))
    for key in ("suren", "biten"):
        if key not in want:
            continue
        observed = [str(text) for text in seen.get(key) or []]
        if len(observed) != len(want[key]) or any(
                needle.casefold() not in text.casefold() for needle, text in zip(want[key], observed)):
            problems.append(_mismatch(f"gunluk.{key}", want[key], observed))
    trails = [row for row in seen.get("iz") or [] if isinstance(row, Mapping)]
    if "iz" in want:
        if not want["iz"]:
            if trails:
                problems.append(f"gunluk.iz: boş bekleniyordu, {len(trails)} iz var")
        else:
            position = 0
            for row in want["iz"]:
                found = next((index for index in range(position, len(trails)) if _trail_matches(row, trails[index])), None)
                if found is None:
                    problems.append(f"gunluk.iz: beklenen iz bulunamadı (sırayla aranır): {_show(row)}")
                else:
                    position = found + 1
    if "iz_sayisi" in want and len(trails) != want["iz_sayisi"]:
        problems.append(f"gunluk.iz_sayisi: {want['iz_sayisi']} bekleniyordu, {len(trails)} var")
    return problems


def _trail_matches(want: Mapping, seen: Mapping) -> bool:
    for key in ("ne", "nerede"):
        if key in want and want[key].casefold() not in str(seen.get(key, "")).casefold():
            return False
    return all(seen.get(key) == want[key] for key in ("kaynak", "izlendi") if key in want)


def _check_subset(key: str, want: Mapping, seen: Mapping) -> list[str]:
    problems = []
    for name in want:
        if name not in seen or seen[name] != want[name]:
            problems.append(_mismatch(f"{key}.{name}", want[name], seen.get(name)))
    return problems


def _check_text(key: str, want: Any, narration: Any) -> list[str]:
    needles = [want] if isinstance(want, str) else list(want)
    haystack = narration.casefold() if isinstance(narration, str) else None
    problems = []
    for needle in needles:
        found = haystack is not None and str(needle).casefold() in haystack
        if key == "yasak_metin" and found:
            problems.append(f"yasak_metin: yasak metin bulundu: {needle}")
        elif key == "gerekli_metin" and not found:
            problems.append(f"gerekli_metin: gerekli metin bulunamadı: {needle}")
    return problems


def _check_told(want: Any, told: Any) -> list[str]:
    """``anlaticiya_giden``: every needle is in what the narrator was sent this step (its input, not the
    narration the player reads; spec §4.3, decision (f)). A step without a narrator call fails once, plainly."""
    if not isinstance(told, str):
        return ["anlaticiya_giden: bu adımda anlatıcı çağrılmadı"]
    needles = [want] if isinstance(want, str) else list(want)
    haystack = told.casefold()
    return [f"anlaticiya_giden: anlatıcıya giden metinde bulunamadı: {needle}"
            for needle in needles if str(needle).casefold() not in haystack]


def _check_spoken_to(want: Any, sent: Any) -> list[str]:
    """``konusmaya_giden``: every needle is in what the step's last speech call was sent (all its messages). A step
    without a speech call fails once, plainly."""
    if not isinstance(sent, str):
        return ["konusmaya_giden: bu adımda konuşma çağrılmadı"]
    haystack = sent.casefold()
    return [f"konusmaya_giden: konuşmaya giden metinde bulunamadı: {needle}"
            for needle in _as_list(want) if needle.casefold() not in haystack]


def _check_kept(want: Mapping, kept: Any) -> list[str]:
    """``anlatilan``: for each person named, every needle is in what that person keeps of the player's own words
    (``npc_told_v1``); a person with nothing kept holds no needle."""
    kept = kept if isinstance(kept, Mapping) else {}
    problems = []
    for npc, needles in want.items():
        rows = kept.get(npc)
        haystack = "\n".join(str(row) for row in rows).casefold() if isinstance(rows, list) else ""
        problems.extend(f"anlatilan.{npc}: anlatılan sözlerde bulunamadı: {needle}"
                        for needle in _as_list(needles) if needle.casefold() not in haystack)
    return problems


def _as_list(needles: Any) -> list[str]:
    return [needles] if isinstance(needles, str) else [str(needle) for needle in needles]


def _mismatch(label: str, want: Any, seen: Any) -> str:
    return f"{label}: beklenen {_show(want)}, gözlenen {_show(seen)}"


def _show(value: Any) -> str:
    return "yok" if value is None else str(value)


def _load_step(raw: Any, where: str, zero_tolerance: bool) -> Step:
    if not isinstance(raw, dict):
        raise ScenarioError(f"{where}: adım bir nesne olmalı")
    _reject_unknown(raw, _STEP_KEYS, where, "adım")
    given = [key for key in ACTION_KEYS if key in raw]
    if len(given) != 1:
        raise ScenarioError(
            f"{where}: tam olarak bir eylem alanı gerekir ({'|'.join(ACTION_KEYS)}), "
            f"bulunan: {', '.join(given) if given else 'hiçbiri'}"
        )
    for key in _TEXT_ACTIONS:
        if key in raw:
            _text(raw, key, where)
    for key in _DICT_ACTIONS:
        if key in raw and not isinstance(raw[key], dict):
            raise ScenarioError(f"{where}: '{key}' bir nesne olmalı")
    for key in _TRUE_ACTIONS:
        if key in raw and raw[key] is not True:
            raise ScenarioError(f"{where}: '{key}' yalnız true olabilir")
    if "ambient" in raw and not (set(raw["ambient"]) == {"action"} and raw["ambient"]["action"] in _AMBIENT_ACTIONS):
        raise ScenarioError(f"{where}: 'ambient' yalnız {{\"action\": {' | '.join(_AMBIENT_ACTIONS)}}} olabilir")
    if "konus" in raw:
        if "say" not in raw:
            raise ScenarioError(f"{where}: 'konus' yalnız 'say' ile birlikte kullanılır")
        _text(raw, "konus", where)
    if "script" in raw and not isinstance(raw["script"], dict):
        raise ScenarioError(f"{where}: 'script' bir nesne olmalı")
    expect = raw.get("expect", {})
    if not isinstance(expect, dict):
        raise ScenarioError(f"{where}: 'expect' bir nesne olmalı")
    _check_expect_values(expect, where, "expect")
    allowed = raw.get("sifir_tolerans", [])
    if "sifir_tolerans" in raw and not (isinstance(allowed, list) and allowed and all(
            isinstance(alternative, dict) and alternative for alternative in allowed)):
        raise ScenarioError(f"{where}: 'sifir_tolerans' boş olmayan beklenti nesneleri listesi olmalı")
    for number, alternative in enumerate(allowed, start=1):
        _check_expect_values(alternative, where, f"sifir_tolerans[{number}]")
    known_broken = _integers(raw, "known_broken", where)
    if zero_tolerance and known_broken:
        raise ScenarioError(
            f"{where}: sıfır tolerans senaryosunda 'known_broken' kullanılamaz"
        )
    broken_because = raw.get("broken_because")
    if broken_because is not None:
        if not known_broken:
            raise ScenarioError(f"{where}: 'broken_because' yalnız 'known_broken' işaretli adımda kullanılır")
        if not (isinstance(broken_because, list) and _needles(broken_because)):
            raise ScenarioError(f"{where}: 'broken_because' boş olmayan metinlerin boş olmayan listesi olmalı")
    real_chain = _boolean(raw, "real_chain", where)
    if real_chain and known_broken:
        raise ScenarioError(f"{where}: 'real_chain' adımı 'known_broken' taşıyamaz (oranı yalnız zincirin olmalı)")
    if real_chain and zero_tolerance:
        raise ScenarioError(f"{where}: sıfır tolerans senaryosunda 'real_chain' adımı olamaz (sahte modelde koşmaz)")
    return Step(
        say=raw.get("say"),
        command=raw.get("command"),
        economic_action=raw.get("economic_action"),
        combat_action=raw.get("combat_action"),
        script=raw.get("script"),
        expect=expect,
        known_broken=known_broken,
        real_chain=real_chain,
        independent=_boolean(raw, "independent", where),
        undo="undo" in raw,
        reload="reload" in raw,
        ambient=copy.deepcopy(raw.get("ambient")),
        broken_because=tuple(broken_because or ()),
        konus=raw.get("konus"),
        sifir_tolerans=copy.deepcopy(allowed),
    )


def _check_expect_values(expect: Mapping, where: str, kind: str) -> None:
    _reject_unknown(expect, EXPECT_KEYS, where, kind)
    for key, value in expect.items():
        rule, wanted = EXPECT_VALUE_RULES[key]
        if not rule(value):
            raise ScenarioError(f"{where}: {kind} '{key}' {wanted} olmalı, bulunan: {value!r}")


def _reject_unknown(data: Mapping, allowed: frozenset[str], where: str, kind: str) -> None:
    unknown = sorted(str(key) for key in data if key not in allowed)
    if unknown:
        raise ScenarioError(
            f"{where}: bilinmeyen {kind} anahtarı: {', '.join(unknown)} "
            f"(izinli: {', '.join(sorted(allowed))})"
        )


def _text(data: Mapping, key: str, where: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value:
        raise ScenarioError(f"{where}: '{key}' boş olmayan bir metin olmalı")
    return value


def _boolean(data: Mapping, key: str, where: str) -> bool:
    value = data.get(key, False)
    if not isinstance(value, bool):
        raise ScenarioError(f"{where}: '{key}' true ya da false olmalı")
    return value


def _integers(data: Mapping, key: str, where: str) -> tuple[int, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in value
    ):
        raise ScenarioError(f"{where}: '{key}' tam sayı listesi olmalı")
    return tuple(value)


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"yinelenen anahtar: {key}")
        result[key] = value
    return result
