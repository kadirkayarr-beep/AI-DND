"""Bounded, campaign-local personal facts and dialogue intent.

These facts belong to a procedural NPC in one campaign. They are not
Forgotten Realms canon and must never be added to Lore Authority.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

import living_world
import npc_statements


VERIFIED_SETTING_FACT = "VERIFIED_SETTING_FACT"
CAMPAIGN_FACT = "CAMPAIGN_FACT"
PROCEDURAL_PERSONAL_FACT = "PROCEDURAL_PERSONAL_FACT"
EPHEMERAL_SCENE_TEXTURE = "EPHEMERAL_SCENE_TEXTURE"
PERSONAL_PROFILE_SCHEMA_VERSION = 1


def remember_speech_exchange(world, npc_id, player_text, npc_text):
    """Bounded attributed dialogue context, never facts or instructions."""
    if not isinstance(npc_id, str) or not isinstance(npc_text, str) or not npc_text.strip():
        return
    log = world.get("npc_speech_log")
    if not isinstance(log, dict):
        log = {}
        world["npc_speech_log"] = log
    previous = log.get(npc_id)
    entries = [item for item in previous if isinstance(item, dict)
               and isinstance(item.get("player"), str)
               and isinstance(item.get("npc"), str)] if isinstance(previous, list) else []
    log[npc_id] = [*entries[-4:], {
        "player": str(player_text or "").strip()[:240],
        "npc": npc_text.strip()[:400],
    }][-4:]
    for stale in list(log)[:-24]:
        del log[stale]


def remember_native_reply(world, action_result, player_text, narration):
    """Bridge accepted native reply routes after final rendering, once per turn.

    Experimental prose already has its own accepted-speech writer. A resolved
    answer_field is native even when requested by the experimental classifier.
    No statement ledger or profile promotion is performed here.
    """
    if not isinstance(action_result, dict) or action_result.get("success") is not True:
        return
    action, status = action_result.get("action"), action_result.get("status")
    native_dialogue = action == "dialogue" and status in {
        "answered_personal_question", "answered_smalltalk", "conversation_started",
        "player_name_disclosed", "answered_without_offer",
    }
    identity = (action == "query" and status == "answered_from_campaign_state"
                and action_result.get("query_type") == "npc_identity")
    if not (native_dialogue or identity):
        return
    npc_id = action_result.get("npc_id")
    if not any(isinstance(n, dict) and n.get("id") == npc_id
               for n in world.get("npcs", [])):
        return
    remember_speech_exchange(world, npc_id, player_text, narration)


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.casefold().replace("ı", "i")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def reality_category_for_entity(
    entity: Any, *, personal_fact: bool = False
) -> str:
    if not isinstance(entity, dict):
        return EPHEMERAL_SCENE_TEXTURE
    layer = entity.get("reality_layer")
    if layer == VERIFIED_SETTING_FACT or entity.get("lore_fact_id"):
        return VERIFIED_SETTING_FACT
    if layer == "EPHEMERAL_SCENE_TEXTURE" or entity.get("kind") == "scene_referent":
        return EPHEMERAL_SCENE_TEXTURE
    if layer == "PROCEDURAL_LOCAL_FICTION" and personal_fact:
        return PROCEDURAL_PERSONAL_FACT
    return CAMPAIGN_FACT


_PROFILE_BANKS: dict[str, tuple[dict[str, str], ...]] = {
    "resident": (
        {
            "occupation": "Mahalledeki bir atölyede çıraklık ediyorum.",
            "current_activity": "Sokak başında biraz soluklanıyorum",
            "mood": "Fena değilim; bugün sokak da sakin.",
            "recent_activity": "Sabah atölyenin önünü toparlayıp işe koyuldum.",
            "origin": "Şehrin yakınlarındaki küçük bir yerleşimden geldim.",
            "reason_for_being_here": "Bugün şehirdeki gündelik işlerimi hallediyorum.",
            "personal_detail": "İş çıkışı kestirme sokaklardan yürümeyi tercih ederim.",
            "immediate_goal": "Günlük işlerimi bitirip eve dönmek.",
        },
        {
            "occupation": "Bir terzinin yanında çalışıyorum.",
            "current_activity": "Dükkânların önünden geçip eve dönüyorum",
            "mood": "Biraz yorgunum ama keyfim yerinde.",
            "recent_activity": "Sabah erkenden birkaç kumaş topunu taşıdım.",
            "origin": "Buralara uzak olmayan küçük bir köyden geldim.",
            "reason_for_being_here": "Ailem ve işim bu şehirde olduğu için buradayım.",
            "personal_detail": "Yağmurdan önce pazar yolunun çamurlandığını bilirim.",
            "immediate_goal": "Akşam olmadan evde olmak.",
        },
        {
            "occupation": "Bir fırında yardımcı olarak çalışıyorum.",
            "current_activity": "İşlerimi bitirip biraz dinleniyorum",
            "mood": "İyiyim; sabah erken kalktım, hepsi bu.",
            "recent_activity": "Güne fırını açmaya yardım ederek başladım.",
            "origin": "Bu şehrin dışındaki küçük bir yerleşimden geldim.",
            "reason_for_being_here": "İşim ve tanıdıklarım burada.",
            "personal_detail": "Sokağın köşesindeki çeşme öğleden sonra kalabalıklaşır.",
            "immediate_goal": "Kalan işlerimi tamamlamak.",
        },
    ),
    "guard": (
        {
            "occupation": "Şehir muhafızıyım.",
            "current_activity": "Bu sokakta nöbet tutuyorum",
            "mood": "İyiyim; nöbet sakin geçiyor.",
            "recent_activity": "Sabah nöbet değişiminde devriye arkadaşımı bilgilendirdim.",
            "origin": "Yakınlardaki küçük bir yerleşimden geldim.",
            "reason_for_being_here": "Bugünkü nöbet yerim bu sokak.",
            "personal_detail": "Nöbet değişimleri genelde günün aynı saatlerinde olur.",
            "immediate_goal": "Nöbetimi sorunsuz tamamlamak.",
        },
        {
            "occupation": "Kent kapılarından birinde muhafızlık yapıyorum.",
            "current_activity": "Çevreyi izleyip nöbetimi sürdürüyorum",
            "mood": "Fena değil; şimdilik her şey yolunda.",
            "recent_activity": "Sabah devriyesinde sokakları dolaşıp geri döndüm.",
            "origin": "Bu şehrin yakınındaki bir köyde büyüdüm.",
            "reason_for_being_here": "Görevim bugün bu bölgede.",
            "personal_detail": "Vardiyam bitince sıcak bir çorba içmeyi umuyorum.",
            "immediate_goal": "Vardiya sonuna kadar dikkatli kalmak.",
        },
    ),
    "bartender": (
        {
            "occupation": "Bu handa barmenlik yapıyorum.",
            "current_activity": "Tezgâhın arkasında çalışıyorum",
            "mood": "İyiyim; işler sakin gidiyor.",
            "recent_activity": "Sabah bardakları yıkayıp tezgâhı hazırladım.",
            "origin": "Yakınlardaki bir yerleşimden geldim; uzun zamandır bu handayım.",
            "reason_for_being_here": "Burası çalıştığım han.",
            "personal_detail": "Tezgâhın köşesindeki küçük çizik yıllardır orada.",
            "immediate_goal": "Tezgâhı düzenli tutup akşamı tamamlamak.",
        },
        {
            "occupation": "Han çalışanıyım; tezgâha ben bakıyorum.",
            "current_activity": "Biraz önce toparladığım tezgâhı düzenliyorum",
            "mood": "Fena değilim; bugün içerisi çok kalabalık değil.",
            "recent_activity": "Güne masaları silip bardakları dizerek başladım.",
            "origin": "Birkaç günlük yolculuk mesafesindeki küçük bir kasabadan geldim.",
            "reason_for_being_here": "Bu handa çalışıyorum.",
            "personal_detail": "Kapıya yakın masa, cereyandan en çok etkilenen yer.",
            "immediate_goal": "Gelenlerle ilgilenip işimi bitirmek.",
        },
    ),
    "traveler": (
        {
            "occupation": "Düzenli bir mesleğim yok; şehirler arasında yolculuk ediyorum.",
            "current_activity": "Yola çıkmadan önce çantamın kayışını düzeltiyorum",
            "mood": "Biraz yorgunum, ama yolculuk iyi gidiyor.",
            "recent_activity": "Bugün birkaç saat yürüyüp burada mola verdim.",
            "origin": "Yakınlardaki küçük bir köyden geldim; birkaç gündür yoldayım.",
            "reason_for_being_here": "Yoluma devam etmeden önce dinlenmek için uğradım.",
            "personal_detail": "Yol boyunca çantamın kayışı yine gevşedi.",
            "immediate_goal": "Biraz dinlenip yoluma devam etmek.",
        },
        {
            "occupation": "Yol üstünde iş buldukça çalışırım; şimdilik yolcuyum.",
            "current_activity": "Çantamı toparlayıp dinlenmeye hazırlanıyorum",
            "mood": "İyiyim; biraz dinlenince daha iyi olacağım.",
            "recent_activity": "Sabah yola çıkıp öğleden sonra bu şehre vardım.",
            "origin": "Bu şehrin batısındaki küçük bir yerleşimden yola çıktım.",
            "reason_for_being_here": "Gece olmadan önce dinlenecek bir yer arıyordum.",
            "personal_detail": "Yolculukta hafif eşya taşımayı öğrendim.",
            "immediate_goal": "Kısa bir mola verip sonra yola koyulmak.",
        },
    ),
    "merchant": (
        {
            "occupation": "Yerel bir tüccarım; burada küçük bir tezgâh tutuyorum.",
            "current_activity": "Tezgâhımın yanında durup çevreyi izliyorum",
            "mood": "İyiyim; bugün sakin bir gün.",
            "recent_activity": "Sabah tezgâhın yerini ayarlayıp çevreyi toparladım.",
            "origin": "Bu şehirde yaşamıyorum; yakındaki bir yerleşimden geldim.",
            "reason_for_being_here": "Bir süreliğine bu sokakta çalışıyorum.",
            "personal_detail": "Tezgâhın konumunu sabahları güneşe göre ayarlarım.",
            "immediate_goal": "Günü sakin biçimde tamamlamak.",
        },
    ),
    "craftsworker": (
        {
            "occupation": "Yakındaki bir atölyede zanaatkârlık yapıyorum.",
            "current_activity": "İşimin arasına kısa bir mola verdim",
            "mood": "İyiyim; işlerim yolunda.",
            "recent_activity": "Sabah atölyedeki aletleri düzenledim.",
            "origin": "Şehrin yakınlarındaki küçük bir yerleşimde büyüdüm.",
            "reason_for_being_here": "Atölyem bu şehirde.",
            "personal_detail": "Çalışırken aletlerimi hep aynı sırayla dizerim.",
            "immediate_goal": "Bugünkü işimi bitirmek.",
        },
    ),
}


def _profile_bank(role: str) -> str:
    text = normalize_text(role)
    if any(token in text for token in ("barmen", "hanci", "han calisani")):
        return "bartender"
    if any(token in text for token in ("yolcu", "gezgin", "traveler")):
        return "traveler"
    if any(token in text for token in ("muhafiz", "guard", "nobet")):
        return "guard"
    if any(token in text for token in ("tuccar", "tacir", "satici", "esnaf", "merchant")):
        return "merchant"
    if any(token in text for token in (
        "demirci", "terzi", "marangoz", "zanaat", "ustasi", "craft"
    )):
        return "craftsworker"
    return "resident"


def new_personal_profile(
    npc_id: str, location_id: str, role: str
) -> dict[str, Any]:
    """Create a small, stable personal profile from bounded mundane templates."""
    bank = _PROFILE_BANKS[_profile_bank(role)]
    seed = hashlib.sha256(
        f"{npc_id}\x00{location_id}\x00{normalize_text(role)}".encode("utf-8")
    ).digest()
    profile = dict(bank[int.from_bytes(seed[:4], "big") % len(bank)])
    profile["schema_version"] = PERSONAL_PROFILE_SCHEMA_VERSION
    return profile


def public_personal_detail(world, npc):
    """Project only a current visible NPC's bounded mundane template detail.

    Existing arbitrary profile strings are NOT made public by a procedural tag.
    This is a read-only eligibility check, not profile regeneration or migration.
    """
    if not isinstance(world, dict) or not isinstance(npc, dict):
        return None
    npc_id = npc.get("id")
    if not isinstance(npc_id, str) or not npc_id:
        return None
    matches = [item for item in world.get("npcs", [])
               if isinstance(item, dict) and item.get("id") == npc_id]
    if len(matches) != 1:
        return None
    canonical = matches[0]
    location = canonical.get("location")
    hp = canonical.get("current_hp", 1)
    if (
        canonical.get("reality_layer") != "PROCEDURAL_LOCAL_FICTION"
        or not isinstance(location, str) or not location
        or location != world.get("location")
        or canonical.get("hidden") or canonical.get("discovered") is False
        or canonical.get("status", "active") in {"dead", "unconscious", "defeated"}
        or canonical.get("combat_status") in {"dead", "unconscious", "defeated"}
        or not isinstance(hp, (int, float)) or hp <= 0
        or not living_world.npc_role_known_to_player(canonical)
    ):
        return None
    role = canonical.get("role")
    profile = canonical.get("personal_profile")
    if (
        not isinstance(role, str) or not role.strip()
        or not isinstance(profile, dict)
        or profile.get("schema_version") != PERSONAL_PROFILE_SCHEMA_VERSION
    ):
        return None
    value = profile.get("personal_detail")
    expected = new_personal_profile(npc_id, location, role)["personal_detail"]
    if not isinstance(value, str) or not value.strip() or value != expected:
        return None
    return {
        "evidence_id": f"npc-profile:{npc_id}:v1:personal_detail",
        "owner_id": npc_id,
        "field": "personal_detail",
        "value": value,
        "source": "npc_personal_profile",
    }


def ensure_personal_profile(npc: Any) -> dict[str, Any] | None:
    if (
        not isinstance(npc, dict)
        or npc.get("reality_layer") != "PROCEDURAL_LOCAL_FICTION"
        or not isinstance(npc.get("id"), str)
        or not isinstance(npc.get("location"), str)
    ):
        return None
    profile = npc.get("personal_profile")
    required = {
        "occupation", "current_activity", "mood", "recent_activity",
        "origin", "reason_for_being_here", "personal_detail", "immediate_goal",
    }
    if (
        not isinstance(profile, dict)
        or profile.get("schema_version") != PERSONAL_PROFILE_SCHEMA_VERSION
        or not required.issubset(profile)
        or any(not isinstance(profile.get(field), str) for field in required)
    ):
        profile = new_personal_profile(
            npc["id"], npc["location"], str(npc.get("role") or "")
        )
        npc["personal_profile"] = profile
    return profile


_WORLD_SUBJECT_TERMS = re.compile(
    r"\b(?:kral|krali[cç]e|h[üu]k[üu]mdar|y[öo]netici|"
    r"lord|lady|baron|duke|king|queen|ruler|"
    r"[şs]ehir|kent|krall[iı]k|hanedan|"
    r"rota|g[üu]zergah|mesafe|uzakl[iı]k|mil|kilometre|"
    r"Neverwinter|Phandalin)\w*\b",
    re.IGNORECASE,
)
_QUESTION_SIGNAL = re.compile(
    r"\?|^\s*(?:kim|ne|nerede|nerden|nereden|hangi|nas[ıi]l|"
    r"who|what|where|which|how)\b|\b(?:m[iıuü]|mi|m[ıuü])\s*$",
    re.IGNORECASE,
)


def is_world_subject_question(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(_WORLD_SUBJECT_TERMS.search(value) and _QUESTION_SIGNAL.search(value))


def is_local_place_recommendation_request(value: Any) -> bool:
    """An ordinary request for an NPC's local recommendation, not a canon claim."""
    text = normalize_text(value)
    if not text:
        return False
    if re.search(
        r"\b(?:daha once|onceki|gecmis|hatirla\w*|"
        r"soz ver\w*|soylemistin|demistin|anlatmistin|bahsetmistin|"
        r"secret|hidden|gizli|sakli|yasakli)\b",
        text,
    ):
        return False
    asks_for_place = bool(
        re.search(r"\b(?:yer\w*|mekan\w*|nereye|lokasyon\w*)\b", text)
        or any(npc_statements.place_kind_of(word) for word in text.split())
    )
    asks_for_recommendation = bool(
        re.search(
            r"\b(?:oner\w*|tavsiye\w*|recommend\w*|suggest\w*)\b",
            text,
        )
    )
    return asks_for_place and asks_for_recommendation


def local_place_recommendation_kind(value: Any) -> str | None:
    """Return a requested venue/service kind, not merely a request for a place."""
    if not is_local_place_recommendation_request(value):
        return None
    for word in normalize_text(value).split():
        place_kind = npc_statements.place_kind_of(word)
        if place_kind is not None:
            return place_kind[1]
    return None


def is_open_local_place_discovery(value: Any) -> bool:
    """An open-ended request for another place, with no requested venue kind."""
    text = normalize_text(value)
    return bool(
        is_local_place_recommendation_request(value)
        and local_place_recommendation_kind(value) is None
        and re.search(r"\b(?:baska|farkli|alternatif)\b", text)
    )


def explicit_player_name_disclosure(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = normalize_text(value)
    if re.search(r"\b(?:mi|miydi|miydim|musun|musunuz|daha once|once)\b", normalized):
        return None
    # A first-clause introduction may be followed by a question in one turn.
    # Require a capitalized name and a sentence boundary to avoid interpreting
    # ordinary 'ben ...' statements as identity disclosures.
    introduction = re.match(
        r"^\s*(?:(?:[Ss]elam|[Mm]erhaba)\s*[,!]\s*)?"
        r"[Bb]en\s+([A-ZÇĞİÖŞÜ][a-zçğıöşü'’-]{1,})\s*[.!;,]\s+",
        value,
    )
    if introduction:
        return introduction.group(1)
    name_pattern = r"([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü'’-]{1,})"
    patterns = (
        rf"\b(?:benim\s+)?(?:adım|ismim)\s+{name_pattern}\b",
        rf"\badımı\s+söylüyorum\s*[:;,]?\s*{name_pattern}\b",
        rf"\bben\s+{name_pattern}\s*[,!.]?\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            if re.match(
                r"""^\s*(?:[,;:]\s*)?["'“”‘’]?\s*(?:[,;:]\s*)?"""
                r"""(?:diye\s+)?(?:dedi|demiş|söyledi|söylemiş|"""
                r"""anlattı|anlatmış|aktardı|konuştu)\b""",
                value[match.end():],
                re.IGNORECASE,
            ):
                continue
            name = match.group(1).strip("'’-")
            normalized_name = normalize_text(name)
            if normalized_name in {"ne", "nedir"}:
                continue
            if name and normalized_name not in {"adim", "ismim"}:
                return name
    return None


def personal_question_kind(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = normalize_text(value)
    if explicit_player_name_disclosure(value):
        return "player_disclosure"
    if re.search(
        r"\b(?:benim adimi|benim ismimi|adimi|ismimi)\b.{0,35}"
        r"\b(?:hatirla\w*|bil\w*|duy\w*)\b|\bhatirliyor musun\b",
        text,
    ):
        return "player_name_memory"
    if re.search(r"\bise\s+basla\w*\b|\bbaslamaya hazir\w*\b|\bhazirim\b.{0,20}\b(?:is|calis)\w*\b", text):
        return "work_acceptance"
    if re.search(
        r"\b(?:is|calis)\w*\b.{0,55}\b(?:var mi|varmi|bul\w*|ara\w*|"
        r"nerede|nerde|bulabilir miyim|bulabilir misin)\b|"
        r"\b(?:buralarda|burada|yakinlarda|civar\w*)\b.{0,55}"
        r"\b(?:is|calis)\w*\b",
        text,
    ):
        return "local_work"
    if re.search(r"\b(?:meslek|mesleg|mesleginiz|ne is|ne isle|isle ugras|neyle ugras)\w*\b", text):
        return "occupation"
    if re.search(
        r"\b(?:bugun|bu sabah|az once|dun)\b.{0,45}"
        r"\b(?:ne yap\w*|neyle ugras\w*|neler yap\w*)\b|"
        r"\b(?:ne yap\w*|neler yap\w*)\b.{0,45}\b(?:bugun|bu sabah|az once)\b",
        text,
    ):
        return "recent_activity"
    if re.search(
        r"\b(?:nereden|nerden|nerde|hangi taraftan)\b.{0,35}"
        r"\b(?:gel\w*|yolculuk|yola cik\w*)\b|"
        r"\b(?:yolculuk|yol)\b.{0,35}\b(?:nereden|nerden|hangi taraftan)\b",
        text,
    ):
        return "origin"
    if re.search(
        r"\b(?:neden|niye|nicin|why)\b.{0,45}"
        r"\b(?:buraya|burada|buradan|here)\b.{0,35}"
        r"\b(?:gel\w*(?:n|niz|sin|siniz|sun|sunuz|din|dın|dun|dün|"
        r"diniz|dınız|dunuz|dünüz)|come\w*)\b|"
        r"\b(?:buraya|burada|buradan|here)\b.{0,35}"
        r"\b(?:neden|niye|nicin|why)\b.{0,45}"
        r"\b(?:gel\w*(?:n|niz|sin|siniz|sun|sunuz|din|dın|dun|dün|"
        r"diniz|dınız|dunuz|dünüz)|come\w*)\b|"
        r"\b(?:neden|niye|nicin|why)\b.{0,65}"
        r"\b(?:ara|ari|bul|yap|ugras|calis)\w*(?:sin|sın|sun|sün|siniz|sınız|sunuz|sünüz)\b",
        text,
    ):
        return "reason_for_being_here"
    if re.search(
        r"\bbugun\s+(?:nasil(?:\s+(?:gidiyor|geciyor))?|gidiyor|geciyor)\s*$|"
        r"\b(?:gunun|keyfin|halin|isler)\b.{0,45}"
        r"\b(?:nasil|gidiyor|geciyor|durum)\b|"
        r"\b(?:nasilsin|keyfin nasil)\b",
        text,
    ):
        return "day"
    if re.search(
        r"\b(?:ad|adi|adiniz|adin|ismin|ismi)\b.{0,24}"
        r"\b(?:ne|nedir|sor\w*)\b|"
        r"\b(?:kimsin|sen kimsin|adini sor)\b|"
        r"\b(?:ismini|adini|adinizi|isminizi)\b.{0,30}"
        r"\b(?:ogren\w*|soyle\w*|sora\w*|sorabilir\w*)\b|"
        r"\b(?:ismin|adin) ne\w*\b",
        text,
    ):
        return "npc_identity"
    if re.search(
        r"\b(?:su an|simdi)\b.{0,35}\b(?:ne yap\w*|neler yap\w*)\b",
        text,
    ):
        return "current_activity"
    if re.search(
        r"\b(?:peki sen|ya sen|kendinden)\b.{0,35}"
        r"\b(?:bahset\w*|anlat\w*|sen)\b|"
        r"\b(?:peki sen|ya sen)\b",
        text,
    ):
        return "personal_context"
    return None


def is_nominal_speech_reference(value: Any) -> bool:
    """An activity noun is not a command to address its mentioned participant.

    For example, liking conversation with people does not select a new actor.
    Anchor the nominal form to the matched reference, never a later clause.
    """
    return bool(re.match(
        r"^\S+(?:\s+(?:la|le|yla|yle|a|e))?\s+(?:konusma(?:yi|ya|ktan|dan)|"
        r"sohbet\s+etme(?:yi|ye|kten|den)|selam\s+verme(?:yi|ye|kten|den))\b",
        normalize_text(value),
    ))


def is_local_dialogue_input(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if personal_question_kind(value):
        return True
    text = normalize_text(value)
    return bool(re.search(
        r"\b(?:bugun|mesleg|meslek|adiniz|adin|ismin|yolculuk nereden|"
        r"buralarda is|is varm[iı]|is ariyorum|isler nasil|"
        r"kendimi tanit\w*|adimi soylo\w*|adimi soylu\w*)\b",
        text,
    ))


def personal_answer(npc: Any, player_input: Any) -> tuple[str, str] | None:
    if not isinstance(npc, dict) or not isinstance(npc.get("name"), str):
        return None
    kind = personal_question_kind(player_input)
    profile = ensure_personal_profile(npc)
    if not profile:
        return None
    name = living_world.public_npc_name(npc)
    answers = {
        "occupation": profile["occupation"],
        "current_activity": profile["current_activity"],
        "recent_activity": profile["recent_activity"],
        "day": profile["mood"],
        "origin": profile["origin"],
        "personal_context": profile["personal_detail"],
        "reason_for_being_here": profile["reason_for_being_here"],
    }
    if kind in answers:
        return (
            f'{name}, “{answers[kind]}” diye yanıt verir.',
            PROCEDURAL_PERSONAL_FACT,
        )
    if kind == "local_work":
        return (
            f'{name}, “Şu anda sana önerebileceğim belirli bir iş yok,” der.',
            PROCEDURAL_PERSONAL_FACT,
        )
    if kind == "work_acceptance":
        return (
            f'{name}, “Henüz sana belirli bir iş önermedim; '
            'şu an başlayabileceğin bir iş yok,” diye karşılık verir.',
            PROCEDURAL_PERSONAL_FACT,
        )
    return None


def quest_availability_question(value: Any) -> bool:
    """True for an explicit question about quests that Python can answer."""
    if not isinstance(value, str):
        return False
    text = normalize_text(value)
    if re.search(r"\b(?:kabul|tamamla|odul|xp|deneyim)\b", text):
        return False
    has_quest_word = bool(re.search(r"\b(?:gorev|quest)\w*\b", text))
    asks_availability = bool(re.search(
        r"\b(?:var mi|sunul\w*|etkin|aktif)\b",
        text,
    ))
    return has_quest_word and asks_availability


def unaddressed_work_answer(player_input: Any) -> tuple[str, str] | None:
    kind = personal_question_kind(player_input)
    if kind == "local_work":
        return (
            "Bu çevrede şu an belirli bir iş teklifi görünmüyor. "
            "Yerel halka gündelik iş olup olmadığını sorabilirsin.",
            CAMPAIGN_FACT,
        )
    if kind == "work_acceptance":
        return (
            "Henüz kabul edebileceğin belirli bir iş teklifi yok.",
            CAMPAIGN_FACT,
        )
    return None

# Discourse markers address the current interlocutor, not a newly named entity.
# Keep them separate from canonical NPC name matching and hidden-name disclosure.
DISCOURSE_ADDRESSES = frozenset({
    "evet", "hayir", "peki", "tamam", "selam", "selamlar", "merhaba", "merhabalar",
    "gunaydin", "hey", "dostum", "bayim", "hanimefendi", "beyefendi", "affedersiniz",
    "pardon", "usta", "lutfen", "ben",
})


def identity_disclosure_is_negated(value: Any) -> bool:
    """An explicit refusal/prohibition is not permission to reveal an identity."""
    text = normalize_text(value)
    return bool(re.search(
        r"\b(?:adini|adinizi|ismini|isminizi|kim oldugunu)\s+"
        r"(?:(?:soyleme|soylemeyin|soylemeyiniz|aciklama|aciklamayin)\b|"
        r"(?:soylemeni|soylemenizi|ogrenmek|duymak)\s+istemiyorum\b)", text))


def has_multiple_dialogue_clauses(value: Any, npc: Any) -> bool:
    """Keep a deterministic smalltalk answer from consuming another clause.

    Greetings and an explicit public addressee are discourse prefixes, not
    additional questions. Unknown remaining clauses belong to the speech path.
    """
    if not isinstance(value, str):
        return False
    prefixes = set(DISCOURSE_ADDRESSES)
    if isinstance(npc, dict):
        prefixes.update(normalize_text(npc.get(key, "")) for key in ("name", "role"))
    prefixes.discard("")
    clauses = []
    for part in re.split(r"[,;.!?]|\b(?:ve|bir de|ayrıca|ayrica|hem)\b", value, flags=re.IGNORECASE):
        text = normalize_text(part)
        for _ in range(3):
            prefix = next((p for p in sorted(prefixes, key=len, reverse=True)
                           if text == p or text.startswith(p + " ")), None)
            if prefix is None:
                break
            text = text[len(prefix):].strip()
        if text:
            clauses.append(text)
    return len(clauses) > 1


def is_identity_only_question(value: Any, npc: Any) -> bool:
    """Permit a fact-only shortcut only when no other request is left over."""
    text = normalize_text(value)
    prefixes = set(DISCOURSE_ADDRESSES)
    if isinstance(npc, dict):
        prefixes.update(normalize_text(npc.get(key, "")) for key in ("name", "role"))
    prefixes.discard("")
    # Strip salutations/explicit addressees, but never the question's remainder.
    for _ in range(3):
        prefix = next((p for p in sorted(prefixes, key=len, reverse=True)
                       if text.startswith(p + " ")), None)
        if prefix is None:
            break
        text = text[len(prefix):].strip()
    return bool(re.fullmatch(
        r"(?:(?:(?:senin|sizin) )?(?:adin|adiniz|ismin|isminiz) (?:ne|nedir)|"
        r"(?:sen )?kimsin(?:iz)?|"
        r"(?:bana )?(?:adini|adinizi|ismini|isminizi) "
        r"(?:soruyorum|(?:ogrenebilir|sorabilir) miyim|soyle(?:r|yebilir) misin(?:iz)?)|"
        r"mi(?:sin(?:iz)?)?|kim(?:dir)?)", text))


def unresolved_named_address(player_input: Any, available: list) -> str | None:
    """An explicit unknown vocative cannot inherit the active conversation."""
    if not isinstance(player_input, str):
        return None
    match = re.match(r"^\s*([A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü’'-]{1,40}),\s+", player_input)
    if not match:
        return None
    name = match.group(1)
    normalized = normalize_text(name)
    if normalized in DISCOURSE_ADDRESSES:
        return None
    for npc in available:
        if not isinstance(npc, dict):
            continue
        if normalized in {normalize_text(living_world.public_npc_name(npc)),
                          normalize_text(living_world.public_npc_role(npc))}:
            return None
    return name


def remember_explicit_player_name(npc: Any, name: str) -> None:
    """Store only the disclosed name, never an accompanying unverified story.

    This is a normalized player identity statement, not an invented NPC reply.
    Full actual exchanges remain in the separately attributed speech history.
    """
    if not isinstance(npc, dict) or not isinstance(npc.get("id"), str) or not npc["id"]:
        return
    if not isinstance(name, str) or len(name) > 100 or not re.fullmatch(r"[A-Za-zÇĞİÖŞÜçğıöşü'’-]+", name):
        return
    entry = {"speaker": "player", "text": f"Benim adım {name}."}
    memory = npc.setdefault("memory", [])
    if not isinstance(memory, list):
        return
    if not memory or memory[-1] != entry:
        memory.append(entry)
    del memory[:-16]
