"""Arrival narration: the model proposes a short scene from what Python already knows; Python checks it.

The world is already changed before the call (location, visited, seen_at, people, clock). The call only
chooses text: the model's checked scene, then Python's recorded fact lines unchanged, or Python's own
arrival text when the model is not asked, fails or is refused.
"""
from __future__ import annotations

import copy
import json
from typing import Any

import game as _game
import living_world
import local_places

SCHEMA = copy.deepcopy(_game._dm_response_schema_for_turn(narration_only=True))
SCHEMA["properties"]["arrival"] = {"type": "boolean"}

RULES = ("Bir yere varışı anlat. Yalnız verilen yeri, verilen vakti ve oradakileri kullan. İlk ziyarette en çok 4, "
         "dönüşte en çok 3 cümle yaz. Verilen vakit dışında vakit söyleme; vakit verilmediyse vakitten söz etme. "
         "Havadan söz etme. Yeni kişi, eşya, çıkış, yol, ücret, para ya da görev ekleme. Tırnak içinde konuşma "
         "yazma. Oyuncu adına karar, söz ya da duygu yazma. Soru sorma, seçenek sunma. Model, veri, kayıt ya da "
         "Python'dan söz etme. world_updates ve lore_claims boş kalsın; yalnız narration yaz.")

ABSENCE = ((1800, "kısa bir süre"), (6 * 3600, "birkaç saat"), (24 * 3600, "yarım günü aşkın"),
           (48 * 3600, "bir gün kadar"))
_LONG_ABSENCE = "birkaç gün"
_PERIODS = {"dawn": "şafak", "day": "gündüz", "evening": "akşam", "night": "gece"}
_QUOTES = ("“", "”", '"')


def _absence(seconds: int) -> str:
    return next((words for limit, words in ABSENCE if seconds < limit), _LONG_ABSENCE)


def _joined(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def venue_scene(world: dict[str, Any], record: dict[str, Any], people, *, seen_before: bool = False) -> dict[str, Any]:
    """An inn or tavern walked into: the same keys as an arrival_parts scene, today's door line as fallback."""
    import campaign_time
    people = [npc for npc in people or () if isinstance(npc, dict)]
    inside = f" İçeride {living_world.public_scene_people(people)} var." if people else ""
    description = record.get("description") or ""
    return {
        "place_id": record.get("id"),
        "name": record.get("name"),
        "noun": "mekân",
        "description": str(description),
        "feature": None,
        "form": "indoor",
        "burning": False,
        "visit": "return" if seen_before else "first",
        "away_seconds": None,
        "clock": campaign_time.public_time(world) if world.get("campaign_time") else None,
        "present": [{"name": living_world.public_npc_name(npc)} for npc in people],
        "fallback": (f"Kapıdan içeri giriyorsun. {record.get('name')} içindesin. "
                     f"{description}{inside or ' İçerisi sessiz.'}"),
        "presence_line": inside,
        "facts_line": "",
        "wants_model": True,
    }


def facts(scene: dict[str, Any], messages) -> dict[str, Any]:
    """What the model is told: only what Python knows and the player can see. No exits, weather, purse or jobs."""
    place = {"tur": scene["noun"], "ad": scene["name"], "tarif": scene["description"]}
    if scene.get("feature"):
        place["ozellik"] = scene["feature"]
    place.update(bicim=scene["form"], yaniyor=bool(scene["burning"]))
    out: dict[str, Any] = {"yer": place}
    clock = scene.get("clock")
    if clock:
        out["zaman"] = {"gun": clock["day_index"], "vakit": _PERIODS[clock["time_of_day"]]}
    first = scene["visit"] == "first"
    out["ziyaret"] = "ilk" if first else "dönüş"
    if not first and scene.get("away_seconds") is not None:
        out["yokluk"] = _absence(int(scene["away_seconds"]))
    people = [{"ad": person["name"], **({"etkinlik": person["activity"]} if person.get("activity") else {})}
              for person in scene.get("present") or ()]
    if people:
        out["oradakiler"] = people
    last = next((message["content"] for message in reversed(messages or [])
                 if isinstance(message, dict) and message.get("role") == "assistant"
                 and isinstance(message.get("content"), str) and message["content"].strip()), None)
    if last:
        out["son_anlatim"] = last[:400]
    return out


def _shaped(game, narration: str, scene: dict[str, Any]) -> str:
    """Form limits, not word lists: quoted speech goes, the scene stays short, unbacked money goes."""
    import town_knowledge
    limit = 4 if scene["visit"] == "first" else 3
    sentences = [sentence.strip() for sentence in game._split_sentences_keep_speech(narration.strip())
                 if sentence.strip() and not any(mark in sentence for mark in _QUOTES)]
    return town_knowledge.without_unbacked_money(" ".join(sentences[:limit])) or ""


def narrate(game, scene: dict[str, Any], *, player_input, messages) -> tuple[str, dict[str, Any]]:
    """The arrival text and {source, reason_code, calls}. The world is never changed here."""
    import grounded_action
    from api.model_phase import resolved_narration_scope
    from api.ollama_adapter import model_calls_left
    session = game._session()
    fallback = _joined(scene["fallback"], scene["facts_line"])

    def done(text, source, reason_code, calls):
        info = {"source": source, "reason_code": reason_code, "calls": calls}
        session.last_arrival_narration = dict(info)
        return text, info

    if not scene["wants_model"]:
        return done(fallback, "python", "short_return", 0)
    left = model_calls_left()
    if left is None:
        return done(fallback, "python", "no_counted_turn", 0)
    speech = grounded_action.spoken_request(player_input)
    if left < (2 if speech else 1):
        return done(fallback, "python", "speech_first" if speech else "no_budget", 0)
    system = "Narrate only the supplied arrival.\n" + game.NARRATOR_VOICE + "\n" + RULES
    try:
        with resolved_narration_scope(True):
            response = game.ollama.chat(
                model="qwen3:8b",
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": json.dumps(facts(scene, messages), ensure_ascii=False)}],
                format=SCHEMA, think=False, options={"temperature": 0.6, "num_predict": 250},
            )
        packet = game._extract_json_object(game.ollama_response_content(response))
    except Exception:  # a fake that asserts, a timeout, a dead server: the turn keeps the Python text
        return done(fallback, "python", "model_error", 1)
    if not isinstance(packet, dict) or not isinstance(packet.get("narration"), str):
        return done(fallback, "python", "invalid_packet", 1)
    # A bare {"narration": ...} packet proposes nothing; a missing field reads as empty.
    updates = packet.get("world_updates") or {}
    proposes = (any(updates.values()) if isinstance(updates, dict) else True) or bool(packet.get("lore_claims"))
    if proposes:
        return done(fallback, "python", "MODEL_WORLD_PROPOSAL_REJECTED", 1)
    text = _shaped(game, packet["narration"], scene)
    if not text.strip():
        return done(fallback, "python", "empty", 1)
    text = game.finalize_narration(
        text, player_input, None,
        action_result={"action": "travel", "status": "resolved", "success": True,
                       "target_id": scene["place_id"], "state_changes": ["location"]},
        resolved_fallback_response=scene["fallback"],
    )
    safety = session.last_narration_safety or {}
    if safety.get("handling") not in {"accepted", "repaired"}:
        return done(fallback, "python", safety.get("reason_code"), 1)
    folded = text.casefold()
    if scene.get("presence_line") and any(person["name"].casefold() not in folded
                                          for person in scene.get("present") or ()):
        text = _joined(text, scene["presence_line"])
    return done(_joined(text, scene["facts_line"]), "model", None, 1)


def arrive(game, world, record, npc, feature, *, first_visit, player_input, messages) -> tuple[str, dict[str, Any]]:
    """The one arrival entry for PLACE_KINDS places, from either path."""
    scene = local_places.arrival_parts(world, record, npc, feature, first_visit=first_visit)
    text, info = narrate(game, scene, player_input=player_input, messages=messages)
    return game._with_job_news(world, record["id"], text), info
