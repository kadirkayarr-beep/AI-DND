"""Server-owned Harptos clock. No wall clock, timers, or independent receipts."""

from __future__ import annotations

import copy
import hashlib
import re
import unicodedata

DAY = 86400
MONTHS = (
    "Hammer", "Alturiak", "Ches", "Tarsakh", "Mirtul", "Kythorn",
    "Flamerule", "Eleasis", "Eleint", "Marpenoth", "Uktar", "Nightal",
)
DEFAULT_DATE = {"year": 1501, "month": "Mirtul", "day": 1}


def year_days(year):
    """Harptos: 12x30 days, five festivals, Shieldmeet every fourth year."""
    days = []
    festivals = {0: "Midwinter", 3: "Greengrass", 6: "Midsummer",
                 8: "Highharvestide", 10: "Feast of the Moon"}
    for index, month in enumerate(MONTHS):
        days.extend((month, day) for day in range(1, 31))
        if index in festivals:
            days.append((festivals[index], 1))
            if index == 6 and year % 4 == 0:
                days.append(("Shieldmeet", 1))
    return days


def validate_clock(clock):
    if not isinstance(clock, dict) or set(clock) != {
        "calendar", "local_convention", "start_date", "start_second", "elapsed_seconds"
    }:
        raise ValueError("Campaign clock fields are invalid.")
    if clock["calendar"] != "Harptos" or clock["local_convention"] != "Neverwinter local":
        raise ValueError("Campaign calendar convention is invalid.")
    date = clock["start_date"]
    if not isinstance(date, dict) or set(date) != {"year", "month", "day"}:
        raise ValueError("Campaign start date is invalid.")
    if type(date["year"]) is not int or not 1 <= date["year"] <= 9999:
        raise ValueError("Campaign year is invalid.")
    if type(date["day"]) is not int or (date["month"], date["day"]) not in year_days(date["year"]):
        raise ValueError("Campaign date is invalid.")
    for field, maximum in (("start_second", DAY - 1), ("elapsed_seconds", DAY * 365 * 100)):
        if type(clock[field]) is not int or not 0 <= clock[field] <= maximum:
            raise ValueError("Campaign clock duration is invalid.")
    return clock


def initialize(world, canonical_start=None):
    """Called when the first scene is resolved; never re-anchor an existing clock."""
    if "campaign_time" in world:
        return validate_clock(world["campaign_time"])
    start = canonical_start or world.get("canonical_start_time")
    date = copy.deepcopy(DEFAULT_DATE)
    second = 9 * 3600
    if start is not None:
        if not isinstance(start, dict) or set(start) != {"year", "month", "day", "hour", "minute"}:
            raise ValueError("Canonical campaign start time is invalid.")
        if any(type(start[key]) is not int for key in ("hour", "minute")) or not (
            0 <= start["hour"] <= 23 and 0 <= start["minute"] <= 59
        ):
            raise ValueError("Canonical campaign start hour is invalid.")
        date = {key: start[key] for key in ("year", "month", "day")}
        second = start["hour"] * 3600 + start["minute"] * 60
    clock = validate_clock({
        "calendar": "Harptos", "local_convention": "Neverwinter local",
        "start_date": date, "start_second": second, "elapsed_seconds": 0,
    })
    world["campaign_time"] = clock
    world.setdefault("scheduled_events", [])
    return clock


# Night and dawn are left out: a first scene should not start with every door shut, and the inn opens at 07:00.
_SEEDED_START_HOURS = (7, 10, 14, 17, 18)


def seed_start(world, seed):
    """A new campaign's first hour comes from its seed; a running or anchored clock stays."""
    clock = world.get("campaign_time")
    if (not isinstance(clock, dict) or clock.get("elapsed_seconds") != 0
            or world.get("canonical_start_time") is not None or not seed):
        return
    digest = hashlib.sha256(f"{seed}|start-hour".encode("utf-8")).digest()
    clock["start_second"] = _SEEDED_START_HOURS[digest[0] % len(_SEEDED_START_HOURS)] * 3600


def public_time(world):
    clock = world.get("campaign_time")
    if clock is None:
        return None
    validate_clock(clock)
    date = clock["start_date"]
    days, second = divmod(clock["start_second"] + clock["elapsed_seconds"], DAY)
    year = date["year"]
    index = year_days(year).index((date["month"], date["day"])) + days
    while index >= len(year_days(year)):
        index -= len(year_days(year))
        year += 1
    month, day = year_days(year)[index]
    hour, remainder = divmod(second, 3600)
    minute, seconds = divmod(remainder, 60)
    period = "dawn" if 5 <= hour < 7 else "day" if 7 <= hour < 17 else "evening" if 17 <= hour < 20 else "night"
    names = {"dawn": "Şafak", "day": "Gündüz", "evening": "Akşam", "night": "Gece"}
    label = f"{day} {month}" if month in MONTHS else month
    return {
        "year": year, "month": month, "day": day, "hour": hour, "minute": minute,
        "second": seconds, "day_index": days, "calendar": "Harptos",
        "local_convention": clock["local_convention"], "time_of_day": period,
        "display": f"{label} — {names[period]}",
        "detail": f"{label} {year} DR — {hour:02d}:{minute:02d}:{seconds:02d}",
    }


def advance(world, seconds, reason, source, *, observation=None):
    """Engine calls only. The API's existing atomic action receipt owns replay."""
    if type(seconds) is not int or not 0 <= seconds <= DAY * 365:
        raise ValueError("Resolved gameplay duration is invalid.")
    if not isinstance(source, str) or not source or not isinstance(reason, str) or not reason:
        raise ValueError("Time advancement needs a gameplay source.")
    clock = world.get("campaign_time")
    if clock is None:
        # Unresolved worlds cannot accrue time before their first scene.
        raise ValueError("The first campaign scene has not been resolved.")
    validate_clock(clock)
    before = public_time(world)
    old = clock["elapsed_seconds"]
    candidate = dict(clock, elapsed_seconds=old + seconds)
    validate_clock(candidate)
    from scheduled_events import process_events
    resolution = {}
    journey = world.get("journey")
    travelling = bool(journey and journey["status"] != "ARRIVED")
    known = process_events(
        world, old, candidate["elapsed_seconds"], observation=observation,
        resolution=resolution, allow_interrupt=reason != "combat_round",
        travelling=travelling,
    )
    import adventure.play as adventure_play
    adventure_play.close_due(world)
    actual = resolution["stop_at"] - old
    clock["elapsed_seconds"] = old + actual  # before the town moves: what happens now happens at the new hour
    if actual > 0:
        import npc_statements
        npc_statements.return_escorts(world, old + actual)  # whoever walked along goes home before the town moves
        import world_threads
        world_threads.tick(world, old + actual)
        import bold_acts
        bold_acts.on_time(world, old + actual)
    return {"elapsed_seconds": actual, "requested_seconds": seconds,
            "remaining_seconds": seconds - actual, "interrupted": resolution["interrupted"],
            "before": before, "after": public_time(world),
            "reason": reason, "player_known_events": known}


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text).casefold().replace("ı", "i"))
    return "".join(c for c in text if not unicodedata.combining(c))


DURATION_CONFLICT = "Aynı satırda iki farklı süre söyledin; tek bir süre yaz."


class DurationConflict(ValueError):
    """One line names two different amounts of the same unit ("2 saat ..., yok 3 saat"), or the same amount again as a
    next step ("2 saat ..., sonra 2 saat daha"): the player is asked."""


# Between two mentions of one length, or "daha"/"more" right after the second: the second is a next span, not a
# restatement. The English words are the Turkish ones' twins (Dilim 3D Task 2).
_ONE_MORE_SPAN = re.compile(r"\b(?:sonra\w*|daha|tekrar\w*|ardindan|then|again|another|more|afterwards?)\b")
_MORE_OF_IT = re.compile(r"\s*(?:daha|more)\b")

# Number words: a ten may take a one after it ("on altı", "twenty-four"). Turkish words go with Turkish units only and
# English words with English units only ("on saat" is ten hours, "on the shelf" is nothing).
_TR_ONES = {"bir": 1, "iki": 2, "uc": 3, "dort": 4, "bes": 5, "alti": 6, "yedi": 7, "sekiz": 8, "dokuz": 9}
_TR_TENS = {"on": 10, "yirmi": 20, "otuz": 30, "kirk": 40, "elli": 50, "altmis": 60, "yetmis": 70, "seksen": 80,
            "doksan": 90}
_EN_ONES = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_EN_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
             "seventeen": 17, "eighteen": 18, "nineteen": 19}
_EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
            "ninety": 90}
_UNIT_SECONDS = {"saniye": 1, "dakika": 60, "saat": 3600, "gun": DAY, "hafta": 7 * DAY, "ay": 30 * DAY}
_EN_UNIT = {"second": "saniye", "minute": "dakika", "hour": "saat", "day": "gun", "week": "hafta"}
_ONE_OF = {"a", "an", "another"}  # "an hour", never "a second time"; "half a second" is no span either


def _alternatives(*tables):
    return "|".join(word for table in tables for word in sorted(table, key=len, reverse=True))


_DIGITS = r"\d+(?:[.,]\d+)?"
_TR_DURATION = re.compile(
    rf"\b({_DIGITS}|(?:{_alternatives(_TR_TENS)})(?:\s+(?:{_alternatives(_TR_ONES)}))?|{_alternatives(_TR_ONES)}"
    r"|yarim)\s*(saniye|dakika|saat|gun|hafta|ay)\b")
_EN_DURATION = re.compile(
    rf"\b(?:({_DIGITS})\s*|((?:{_alternatives(_EN_TENS)})(?:[-\s](?:{_alternatives(_EN_ONES)}))?"
    rf"|{_alternatives(_EN_TEENS, _EN_ONES)}|half(?:\s+an?)?|another|an?)\s+)"
    r"(?:(?:full|whole)\s+)?(second|minute|hour|day|week)s?\b")


def _number(word, *tables):
    """'on altı' -> 16, 'twenty-four' -> 24, '8' -> 8.0."""
    if re.fullmatch(_DIGITS, word):
        return float(word.replace(",", "."))
    merged = {key: value for table in tables for key, value in table.items()}
    return sum(merged[part] for part in re.split(r"[-\s]+", word))


def _spans(normalized):
    """(amount, canonical unit, start, end) for every length said, Turkish and English, in line order."""
    spans = []
    for match in _TR_DURATION.finditer(normalized):
        amount, unit = match.groups()
        number = 0.5 if amount == "yarim" else _number(amount, _TR_ONES, _TR_TENS)
        spans.append((number, unit, match.start(), match.end()))
    for match in _EN_DURATION.finditer(normalized):
        digits, word, unit = match.groups()
        word = word or ""
        if (word in _ONE_OF or word.startswith("half")) and unit == "second":
            continue
        number = (_number(digits) if digits else 0.5 if word.startswith("half") else 1 if word in _ONE_OF
                  else _number(word, _EN_ONES, _EN_TEENS, _EN_TENS))
        spans.append((number, _EN_UNIT[unit], match.start(), match.end()))
    return sorted(spans, key=lambda span: span[2])


def requested_duration(text):
    """Read only explicit player duration, never generated prose.

    The same length said twice counts once ("16 saat ... 16 saat"); different units add ("2 saat 30 dakika");
    two different amounts of one unit, or the same one again after "sonra/daha/tekrar/ardından" (English: "then",
    "again", "another", "more"), raise DurationConflict. English lengths read as their Turkish twins."""
    normalized = normalize(text)
    matches = _spans(normalized)
    if not matches:
        return None
    amounts, last_end = {}, {}
    for number, unit, start, end in matches:
        if unit in amounts and (amounts[unit] != number
                                or _ONE_MORE_SPAN.search(normalized, last_end[unit], start)
                                or _MORE_OF_IT.match(normalized, end)):
            raise DurationConflict(DURATION_CONFLICT)  # "sonra 2 saat daha": more time, not the same said again
        amounts[unit], last_end[unit] = number, end
    total = 0
    for unit, number in amounts.items():
        total += number * _UNIT_SECONDS[unit]
    if total <= 0 or total > DAY * 365 or total != int(total):
        raise ValueError("Bekleme süresi pozitif ve en fazla bir oyun yılı olmalı.")
    return int(total)


def names_duration(text):
    """The line names a length; two lengths that disagree still name one (the wait owner asks which)."""
    try:
        return requested_duration(text) is not None
    except DurationConflict:
        return True


def until_morning(world):
    return _until_hour(world, 7)


def _until_hour(world, hour):
    time = public_time(world)
    second = time["hour"] * 3600 + time["minute"] * 60 + time["second"]
    return (hour * 3600 - second) % DAY or DAY


_NAMED_HOURS = (("sabaha kadar", 7), ("ogleye kadar", 12), ("ogle vaktine kadar", 12),
                ("aksama kadar", 18), ("geceye kadar", 21))


def mentions_named_hour(normalized):
    return any(words in normalized for words, _ in _NAMED_HOURS)


def until_named_hour(world, normalized):
    """Seconds to the part of the day the player named, if they named one."""
    return next((_until_hour(world, hour) for words, hour in _NAMED_HOURS if words in normalized), None)


def named_hour_now(world, normalized):
    """It already is the part of the day the player named ("akşama kadar" at 18:30): it runs from its hour to the next
    named one (evening 18-21, night 21-7). Waiting for it is no wait, not a whole day. "Sabaha kadar" keeps its own
    meaning (until_morning: the next morning, the night let go by)."""
    hour = next((hour for words, hour in _NAMED_HOURS if words in normalized), None)
    time = public_time(world)
    if hour is None or hour == 7 or time is None:
        return False
    starts = sorted({start for _, start in _NAMED_HOURS})
    end = next((start for start in starts if start > hour), starts[0])
    now = time["hour"]
    return hour <= now < end if hour < end else (now >= hour or now < end)