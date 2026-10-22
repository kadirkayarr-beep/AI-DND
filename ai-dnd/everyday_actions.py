"""Ordinary harmless actions get a concrete, in-character result (LR00 step 7).

Knocking, ringing a bell, reading your own book, whistling or dancing,
following someone you can see: none of these needs a new mechanic, and none
should hit a "you can't do that" wall. Python decides the small, truthful
outcome from saved state (is there a door, is it locked, do you carry a book,
is that person here); nothing is invented that would change the world.
Negated, conditional and question forms are left to the normal pipeline.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Callable

import equipment_economy
import living_world

_NEGATED = re.compile(r"\b\w+(?:miyorum|muyorum|mayacagim|meyecegim|mayi|meyi)\b|\bistemiyorum\b")
_CONDITIONAL = re.compile(r"\b(?:eger|sayet)\b|\b\w+(?:sam|sem|rsa|rse)\b")
_QUESTION = re.compile(r"\?")

# "çal" (ring/knock) but not "çalış" (try/work): calis... is excluded.
_CAL = r"cal(?!is)\w*"
_KNOCK = re.compile(rf"\b(?:kapi\w*)\b.{{0,60}}\b(?:vur\w*|{_CAL}|tiklat\w*|tikirdat\w*|yumrukla\w*)|\btak tak\b")
_BELL = re.compile(rf"\b(?:zil\w*|can|cani|cana|canin|kampana\w*)\b.{{0,40}}\b(?:{_CAL}|cek\w*|salla\w*)")
_READ = re.compile(r"\b(?:kitab\w*|kitap|defter\w*|gunlug\w*|parsomen\w*)\b.{0,50}\b(?:oku|ac|karistir|goz gezdir)\w*")
_PERFORM = re.compile(r"\b(?:islik|sarki|turku|dans|oyna(?:yorum|rim)|zipla)\w*")
_FOLLOW = re.compile(r"\b(?:pesin\w*|pesine|arkasindan|takip)\b")
# "Eğer kapı açıksa içeri süzülürüm, değilse beklerim": the condition is checked
# against the saved door; a closed door means the player waits, nothing moves.
_CONDITIONAL_ENTRY = re.compile(
    r"\b(?:eger|sayet)\b.{0,40}\bkapi\w*\b.{0,20}\bacik\w*.{0,40}\b(?:gir|suzul|dal)\w*"
)


def _fold(value: Any) -> str:
    return living_world.normalize_text(value)


def _pick(seed: str, options: tuple[str, ...]) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return options[int.from_bytes(digest[:4], "big") % len(options)]


def classify(text: Any) -> str | None:
    if not isinstance(text, str):
        return None
    folded = _fold(text)
    if _NEGATED.search(folded) or _CONDITIONAL.search(folded) or _QUESTION.search(text):
        return None
    # A bell over a door is rung, not knocked: check the bell first.
    for kind, pattern in (("bell", _BELL), ("knock", _KNOCK), ("read", _READ),
                          ("follow", _FOLLOW), ("perform", _PERFORM)):
        if pattern.search(folded):
            return kind
    return None


def _present_people(world: dict[str, Any]) -> list[dict[str, Any]]:
    here = world.get("location")
    return [
        npc for npc in world.get("npcs", [])
        if isinstance(npc, dict) and npc.get("location") == here
        and npc.get("status", "active") not in {"dead", "deceased"}
        and npc.get("combat_status", "active") == "active"
    ]


def _named_person(world: dict[str, Any], text: str,
                  reference: Callable[[str, str], bool]) -> dict[str, Any] | None:
    matches = [
        npc for npc in _present_people(world)
        if (living_world.npc_name_known_to_player(npc) and reference(npc.get("name", ""), text))
        or (living_world.npc_role_known_to_player(npc)
            and reference(living_world.public_npc_role(npc) or "", text))
    ]
    return matches[0] if len(matches) == 1 else None


def resolve(world: dict[str, Any], text: str, *, door: dict[str, Any] | None,
            reference: Callable[[str, str], bool], turn: int) -> dict[str, Any] | None:
    if (isinstance(text, str) and isinstance(door, dict) and not door.get("open")
            and _CONDITIONAL_ENTRY.search(_fold(text))):
        state = "kapalı ve kilitli" if door.get("locked") else "kapalı"
        return {"kind": "conditional_wait", "door_id": door.get("id"), "text": (
            f"{door.get('name', 'Kapı')} {state}; koşulun gerçekleşmiyor. "
            "İçeri girmeden kapının önünde bekliyorsun."
        )}
    kind = classify(text)
    if kind is None:
        return None
    seed = f"{world.get('location')}|{turn}|{kind}"
    people = _present_people(world)
    if kind == "knock":
        if not isinstance(door, dict):
            return None
        name = door.get("name", "Kapı")
        if door.get("open"):
            line = f"{name} zaten aralık; vurmana gerek kalmadan içerisi görünüyor."
        elif door.get("locked"):
            line = _pick(seed, (
                f"{name} üzerine birkaç kez vuruyorsun. Tahta tok bir ses veriyor; bir süre bekliyorsun ama içeriden yanıt gelmiyor ve kapı kilitli kalıyor.",
                f"Parmak eklemlerinle {name} kapısını tıklatıyorsun. Kulak veriyorsun: içeride ne ayak sesi ne bir seslenme var. Kapı kilitli.",
            ))
        else:
            line = f"{name} üzerine vuruyorsun. Yanıt gelmiyor; kapı kapalı ama kilitli görünmüyor."
        return {"kind": kind, "text": line, "door_id": door.get("id")}
    if kind == "bell":
        listener = living_world.public_npc_name(people[0]) if people else None
        line = "Çanı çalıyorsun; tiz sesi sokak boyunca yankılanıp yavaşça sönüyor."
        if listener:
            line += f" {listener} başını çevirip sesin nereden geldiğine bakıyor."
        return {"kind": kind, "text": line}
    if kind == "read":
        labels = [label for label in equipment_economy.labels(world.get("inventory", []))
                  if re.search(r"kitap|defter|günlük|parşömen", str(label).casefold())]
        if not labels:
            return {"kind": kind, "text": "Çantanı karıştırıyorsun ama içinde okuyabileceğin bir kitap yok.",
                    "item": None}
        return {"kind": kind, "item": labels[0], "text": (
            f"{labels[0]} çantandan çıkarıp birkaç sayfa okuyorsun. "
            "Bir süre çevrendeki sesler uzaklaşıyor; yeni bir şey öğrenmiş sayılmazsın ama zihnin biraz duruluyor."
        )}
    if kind == "follow":
        person = _named_person(world, text, reference)
        if person is not None:
            who = living_world.public_npc_name(person)
            return {"kind": kind, "npc_id": person.get("id"), "text": _pick(seed, (
                f"{who} birkaç adım ötede işine devam ediyor; arkasından yürüyorsun. Uzağa gitmiyor, çevrede dolaşıp yine aynı yere dönüyor. Seni fark edip etmediği belli değil.",
                f"Mesafeni koruyarak {who} arkasından yürüyorsun. Yalnızca birkaç sokak köşesi dolaşıp tanıdık yüzlerle selamlaşıyor, sonra olduğu yere dönüyor.",
            ))}
        return {"kind": kind, "npc_id": None, "text": (
            "Kalabalığın içinde gözünü bir an ayırınca izini kaybediyorsun; kimin peşinde olduğunu artık seçemiyorsun."
        )}
    if kind == "perform":
        watcher = living_world.public_npc_name(people[0]) if people else None
        line = "Kendi kendine ıslık çalıp birkaç adım atıyorsun; sokağın gürültüsü bir an için hafifliyor gibi."
        if watcher:
            line += f" {watcher} göz ucuyla sana bakıp hafifçe gülümsüyor."
        return {"kind": kind, "text": line}
    return None
