"""Server-owned Harptos clock. No wall clock, timers, or independent receipts."""

from __future__ import annotations

import copy
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
    clock["elapsed_seconds"] = old + actual
    return {"elapsed_seconds": actual, "requested_seconds": seconds,
            "remaining_seconds": seconds - actual, "interrupted": resolution["interrupted"],
            "before": before, "after": public_time(world),
            "reason": reason, "player_known_events": known}


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text).casefold().replace("ı", "i"))
    return "".join(c for c in text if not unicodedata.combining(c))


def requested_duration(text):
    """Read only explicit player duration, never generated prose."""
    normalized = normalize(text)
    words = {"bir": 1, "iki": 2, "uc": 3, "dort": 4, "bes": 5, "alti": 6,
             "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10, "yarim": 0.5}
    pattern = r"\b(\d+(?:[.,]\d+)?|" + "|".join(words) + r")\s*(saniye|dakika|saat|gun|hafta|ay)\b"
    matches = re.findall(pattern, normalized)
    if not matches:
        return None
    total = 0
    for amount, unit in matches:
        number = words[amount] if amount in words else float(amount.replace(",", "."))
        total += number * {"saniye": 1, "dakika": 60, "saat": 3600, "gun": DAY,
                           "hafta": 7 * DAY, "ay": 30 * DAY}[unit]
    if total <= 0 or total > DAY * 365 or total != int(total):
        raise ValueError("Bekleme süresi pozitif ve en fazla bir oyun yılı olmalı.")
    return int(total)


def until_morning(world):
    time = public_time(world)
    second = time["hour"] * 3600 + time["minute"] * 60 + time["second"]
    return (7 * 3600 - second) % DAY or DAY