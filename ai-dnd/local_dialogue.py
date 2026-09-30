"""Bounded, campaign-local personal facts and dialogue intent.

These facts belong to a procedural NPC in one campaign. They are not
Forgotten Realms canon and must never be added to Lore Authority.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any


VERIFIED_SETTING_FACT = "VERIFIED_SETTING_FACT"
CAMPAIGN_FACT = "CAMPAIGN_FACT"
PROCEDURAL_PERSONAL_FACT = "PROCEDURAL_PERSONAL_FACT"
EPHEMERAL_SCENE_TEXTURE = "EPHEMERAL_SCENE_TEXTURE"
PERSONAL_PROFILE_SCHEMA_VERSION = 1


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


def explicit_player_name_disclosure(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = normalize_text(value)
    if re.search(r"\b(?:mi|miydi|miydim|musun|musunuz|daha once|once)\b", normalized):
        return None
    name_pattern = r"([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü'’-]{1,})"
    patterns = (
        rf"\b(?:benim\s+)?(?:adım|ismim)\s+{name_pattern}\b",
        rf"\badımı\s+söylüyorum\s*[:;,]?\s*{name_pattern}\b",
        rf"\bben\s+{name_pattern}\s*[,!.]?\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            name = match.group(1).strip("'’-")
            if name and normalize_text(name) not in {"adim", "ismim"}:
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
        r"\b(?:bugun|gunun|keyfin|halin|isler)\b.{0,45}"
        r"\b(?:nasil|gidiyor|geciyor|durum)\b|"
        r"\b(?:nasilsin|keyfin nasil)\b",
        text,
    ):
        return "day"
    if re.search(
        r"\b(?:ad|adi|adiniz|adin|ismin|ismi)\b.{0,24}"
        r"\b(?:ne|nedir|sor\w*)\b|"
        r"\b(?:kimsin|sen kimsin|adini sor)\b",
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
    name = npc["name"]
    answers = {
        "occupation": profile["occupation"],
        "current_activity": profile["current_activity"],
        "recent_activity": profile["recent_activity"],
        "day": profile["mood"],
        "origin": profile["origin"],
        "personal_context": profile["personal_detail"],
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