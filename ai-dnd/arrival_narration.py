"""Arrival narration: the model proposes a short scene from what Python already knows; Python checks it.

The world is already changed before the call (location, visited, seen_at, people, clock). The call only
chooses text: the model's checked scene, then Python's recorded fact lines unchanged, or Python's own
arrival text when the model is not asked, fails or is refused.
"""
from __future__ import annotations

import json
from typing import Any

import living_world
import local_places

# The text and the marker only. The narrator's schema sits at Haiku's grammar limit: one more field and every
# call came back HTTP 400 "The compiled grammar is too large" (Task 6b). A packet that still proposes is refused below.
SCHEMA = {
    "type": "object",
    "properties": {"narration": {"type": "string"}, "arrival": {"type": "boolean"}},
    "required": ["narration", "arrival"],
    "additionalProperties": False,
}

RULES = ("Bir yere varışı anlat. Yalnız verilen yeri, verilen vakti ve oradakileri kullan. İlk ziyarette en çok 6, "
         "dönüşte en çok 4 cümle yaz. Verilen vakit dışında vakit söyleme; vakit verilmediyse vakitten söz etme. "
         "Yeni kişi, eşya, çıkış, yol, ücret, para ya da görev ekleme. Tırnak içinde konuşma "
         "yazma. Oyuncu adına karar, söz ya da duygu yazma. Soru sorma, seçenek sunma. Model, veri, kayıt ya da "
         "Python'dan söz etme. Yalnız narration yaz; arrival true olsun.")

LIMITS = {"first": 6, "return": 4}
RETURN_FLOOR = 2

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


def _sentences(game, text) -> list[str]:
    return [sentence.strip() for sentence in game._split_sentences_keep_speech((text or "").strip()) if sentence.strip()]


def fit(game, pieces: list[tuple[int, str]], limit: int) -> str:
    """The whole shown arrival: pieces are (rank, text) in reading order; the `limit` best-ranked sentences stay, in order."""
    flat = [(rank, sentence) for rank, text in pieces for sentence in _sentences(game, text)]
    ranked = [(rank, position, sentence) for position, (rank, sentence) in enumerate(flat)]
    kept = sorted(sorted(ranked)[:limit], key=lambda item: item[1])
    return " ".join(sentence for _, _, sentence in kept)


def _body_pieces(game, text) -> list[tuple[int, str]]:
    """Rank the body's own sentences: the first leads, the second is next, the rest go first when room is short."""
    return [(1 if index == 0 else 4 if index == 1 else 6, sentence)
            for index, sentence in enumerate(_sentences(game, text))]


def facts(scene: dict[str, Any], messages, budget: int | None = None) -> dict[str, Any]:
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
        out["son_anlatim"] = last[:1200]
    if budget is not None:
        out["sentence_budget"] = budget
    return out


def _shaped(game, narration: str, scene: dict[str, Any]) -> str:
    """Form limits, not word lists: quoted speech goes, the scene stays short, unbacked money goes."""
    import town_knowledge
    limit = LIMITS["first" if scene["visit"] == "first" else "return"]
    sentences = [sentence.strip() for sentence in game._split_sentences_keep_speech(narration.strip())
                 if sentence.strip() and not any(mark in sentence for mark in _QUOTES)]
    return town_knowledge.without_unbacked_money(" ".join(sentences[:limit])) or ""


def narrate(game, scene: dict[str, Any], *, player_input, messages, lead: str = "",
            tail: str = "") -> tuple[str, dict[str, Any]]:
    """The whole shown arrival (lead, scene, facts, tail; capped) and {source, reason_code, calls}. The world is never changed here."""
    import grounded_action
    from api.model_phase import resolved_narration_scope
    from api.ollama_adapter import model_calls_left
    session = game._session()
    limit = LIMITS["first" if scene["visit"] == "first" else "return"]

    def whole(body, *, presence="", model=False):
        pieces = [(0, lead)]
        pieces += _body_pieces(game, body)
        named = scene["name"].casefold() in _joined(lead, body).casefold()
        if model and scene["visit"] != "first" and (not named or len(_sentences(game, body)) < RETURN_FLOOR):
            pieces.append((1, scene.get("back") or ""))  # a return names its place and is never one bare sentence
        pieces += [(5, presence), (2, scene["facts_line"]), (3, tail)]
        return fit(game, pieces, limit)

    def done(body, source, reason_code, calls, *, presence="", model=False):
        info = {"source": source, "reason_code": reason_code, "calls": calls}
        session.last_arrival_narration = dict(info)
        return whole(body, presence=presence, model=model), info

    def python(reason_code, calls):
        line = (scene.get("presence_line") or "").strip()
        body = scene["fallback"].rstrip()
        if line and body.endswith(line):  # the Python text ends with its presence line: it ranks on its own
            return done(body[:-len(line)], "python", reason_code, calls, presence=line)
        return done(body, "python", reason_code, calls)

    if not scene["wants_model"]:
        return python("short_return", 0)
    left = model_calls_left()
    if left is None:
        return python("no_counted_turn", 0)
    speech = grounded_action.spoken_request(player_input)
    rest = bool(getattr(session, "_front_rest", ""))  # the rest of the line is read at the place walked to (D3D T4)
    if left < (2 if speech or rest else 1):
        return python("speech_first" if speech else "rest_first" if rest else "no_budget", 0)
    budget = max(RETURN_FLOOR, limit - sum(len(_sentences(game, piece)) for piece in (lead, scene["facts_line"], tail)))
    system = "Narrate only the supplied arrival.\n" + game.NARRATOR_VOICE + "\n" + RULES
    try:
        with resolved_narration_scope(True):
            response = game.ollama.chat(
                model="qwen3:8b",
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": json.dumps(facts(scene, messages, budget), ensure_ascii=False)}],
                format=SCHEMA, think=False, options={"temperature": 0.6, "num_predict": 450},
            )
        packet = game._extract_json_object(game.ollama_response_content(response))
    except Exception:  # a fake that asserts, a timeout, a dead server: the turn keeps the Python text
        return python("model_error", 1)
    if not isinstance(packet, dict) or not isinstance(packet.get("narration"), str):
        return python("invalid_packet", 1)
    # A bare {"narration": ...} packet proposes nothing; a missing field reads as empty.
    updates = packet.get("world_updates") or {}
    proposes = (any(updates.values()) if isinstance(updates, dict) else True) or bool(packet.get("lore_claims"))
    if proposes:
        return python("MODEL_WORLD_PROPOSAL_REJECTED", 1)
    text = _shaped(game, packet["narration"], scene)
    if not text.strip():
        return python("empty", 1)
    text = game.finalize_narration(
        text, player_input, None,
        action_result={"action": "travel", "status": "resolved", "success": True,
                       "target_id": scene["place_id"], "state_changes": ["location"]},
        resolved_fallback_response=scene["fallback"],
    )
    safety = session.last_narration_safety or {}
    if safety.get("handling") not in {"accepted", "repaired"}:
        return python(safety.get("reason_code"), 1)
    folded = text.casefold()
    presence = ""
    if scene.get("presence_line") and any(person["name"].casefold() not in folded
                                          for person in scene.get("present") or ()):
        presence = scene["presence_line"]
    return done(text, "model", None, 1, presence=presence, model=True)


def arrive(game, world, record, npc, feature, *, first_visit, player_input, messages,
           lead: str = "") -> tuple[str, dict[str, Any]]:
    """The one arrival entry for PLACE_KINDS places, from either path."""
    scene = local_places.arrival_parts(world, record, npc, feature, first_visit=first_visit)
    return narrate(game, scene, player_input=player_input, messages=messages, lead=lead,
                   tail=game._job_news_line(world, record["id"]))
