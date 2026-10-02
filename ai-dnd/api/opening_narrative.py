"""Deterministic, campaign-persistent first-scene presentation."""

from __future__ import annotations

from typing import Any

import living_world
from api.world_metadata import world_metadata_for_state


_TIME_OPENERS = {
    "dawn": "Şafak söküp",
    "day": "Gün ışığı altında",
    "evening": "Akşam yaklaşırken",
    "night": "Gece çökmüşken",
}
_WEATHER_LINES = {
    "clear": "Gökyüzü açık; çevrenin çizgileri belirgin.",
    "rain": "Yağmur taşlara ve çatılara düzenli aralıklarla vuruyor.",
    "fog": "Sis, uzaktaki ayrıntıları yumuşatıp sesleri öne çıkarıyor.",
    "snow": "Kar, açıkta kalan yüzeylerde ince bir tabaka bırakmış.",
    "storm": "Fırtına rüzgârı sokakların ve yapıların arasından geçiyor.",
    "unknown": "Havanın ayrıntıları henüz doğrulanmış değil.",
}
_BACKGROUND_NOTES = {
    "Acolyte": "İnanç ve hizmet, geçmişinin bir parçası.",
    "Artisan": "Bir zanaatın emeğini ve düzenini tanıyorsun.",
    "Criminal": "Geçmişin, kuralların dışında kalan hayatı da tanıyor.",
    "Entertainer": "Sahne ve seyirci, geçmişinde yer tutuyor.",
    "Farmer": "Toprağa ve günlük emeğe dayanan bir geçmişin var.",
    "Guard": "Nöbet ve düzen, geçmişinin parçası.",
    "Guide": "Yol bulmak ve çevreyi okumak sana yabancı değil.",
    "Hermit": "Uzun süre kendi başına yaşamak geçmişinde yer alıyor.",
    "Merchant": "Alışveriş ve pazarlık, geçmişinin bir parçası.",
    "Noble": "Soy ve toplumsal beklentiler geçmişinde yer tutuyor.",
    "Sage": "Bilgi arayışı, geçmişinin merkezinde.",
    "Sailor": "Deniz ve gemi yaşamı geçmişinde yer alıyor.",
    "Scribe": "Yazı ve kayıt tutmak geçmişinin parçası.",
    "Soldier": "Askerlik ve disiplin, geçmişinin bir parçası.",
    "Wayfarer": "Yolculuk, geçmişinde önemli bir yer tutuyor.",
}


def _tone(character: dict[str, Any], metadata: dict[str, str]) -> str:
    time_of_day = metadata.get("time_of_day")
    weather = metadata.get("weather")
    personality = str(character.get("personality") or "").casefold()
    backstory = str(character.get("backstory") or "").casefold()
    if weather == "storm":
        return "gergin"
    if time_of_day == "night" or weather == "fog":
        return "gizemli"
    if any(word in personality for word in ("neşeli", "iyimser", "şakacı")):
        return "sıcak"
    if any(word in backstory for word in ("kayıp", "yas", "sürgün", "yalnız")):
        return "melankolik"
    if time_of_day == "day":
        return "canlı"
    return "sakin"


def initialize_campaign_opening(
    session: Any,
    campaign_id: str,
) -> dict[str, Any] | None:
    """Create one opening for a registered location; never call the model."""
    world_state = session.world_state
    character = session.character
    metadata = world_metadata_for_state(
        world_state,
        getattr(session, "world_metadata", None),
    )
    living_world.set_ambient_context(
        world_state,
        metadata,
        character,
        campaign_id,
    )
    location_id = world_state.get("location")
    locations = world_state.get("locations", {})
    location = locations.get(location_id) if isinstance(locations, dict) else None
    if (
        not isinstance(location_id, str)
        or not isinstance(location, dict)
        or not isinstance(location.get("name"), str)
    ):
        # Older API callers can still create campaigns without a verified
        # start-catalog selection. Preserve that contract without inventing
        # a location name or ambient scene.
        return None

    event = living_world.select_and_record_ambient_event(
        world_state,
        location_id,
        0,
        allowed_types={"GREEN"},
    )
    if event is None:
        raise ValueError("No context-compatible ambient opening event exists.")

    tone = _tone(character, metadata)
    time_opener = _TIME_OPENERS[metadata["time_of_day"]]
    weather_line = _WEATHER_LINES[metadata["weather"]]
    parts = [
        f"{time_opener} {location['name']} içindeki yolculuğun açılıyor.",
        weather_line,
        event["text"],
    ]
    background_note = _BACKGROUND_NOTES.get(character.get("background"))
    if background_note:
        parts.append(background_note)
    origin = character.get("origin")
    if isinstance(origin, str) and origin.strip():
        parts.append(
            f"Kökenin {origin.strip()}; bu bilgiyi çevrendekilerden kimin "
            "bildiği henüz belirlenmiş değil."
        )
    backstory = character.get("backstory")
    if isinstance(backstory, str) and backstory.strip():
        parts.append(
            f"Geçmişinden aklında kalan kayıt: “{backstory.strip()[:360]}”"
        )
        parts.append("Geçmişinin bugünkü yolculukta ne anlama geldiğini sen belirlersin.")
    parts.append(
        "Burada sana dayatılmış bir görev yok; bir sonraki adım sana ait."
    )
    text = " ".join(parts)
    return living_world.set_scene_opening(
        world_state,
        location_id,
        text,
        tone,
        event,
    )