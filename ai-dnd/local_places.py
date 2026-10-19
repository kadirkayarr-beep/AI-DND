"""LR00-P3 pilot: a local place the player heads for becomes a real, saved place.

Scope (OH1-SCOPE-01): inside the current settlement only. One place per kind
per settlement, one local person, one interactable detail and one small local
matter that is NOT a quest, reward or obligation. No new city, route, distance
or economy. Python owns identity and persistence; the model only narrates later
turns. Revisits and restarts reuse the saved records, never re-roll them.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import living_world

MAX_LOCAL_PLACES_PER_SETTLEMENT = 8

# kind -> vocabulary and small, mundane, campaign-seeded content banks.
PLACE_KINDS: dict[str, dict[str, Any]] = {
    # activities/issues are (narrator, first person) pairs: the narrator line is
    # what the player sees on arrival, the first-person line is what the person
    # can say about it later (personal profile, never a quest or a reward).
    "archive": {
        "stems": ("arsiv",), "suffix": "Arşivi", "noun": "arşiv", "role": "Arşivci",
        "descriptions": (
            "Taş duvarlı, serin bir salon; havada eski kâğıt ve mum isi kokusu var.",
            "Basık tavanlı, uzun bir oda; pencerelerden süzülen ışık tozu görünür kılıyor.",
        ),
        "feature": ("Tozlu raflar", "Tavana kadar uzanan, etiketleri solmuş raflar; bazı kutuların mührü kırık.",
                    ["raf", "raflar", "etiket", "kutu", "kutular", "muhur"]),
        "activities": (("Bir deftere kayıt numaraları geçiriyor.", "Deftere kayıt numaralarını geçiriyorum."),
                       ("Nemlenmiş bir tomarı mum ışığında kurutmaya çalışıyor.", "Nemlenmiş bir tomarı kurutmaya çalışıyorum.")),
        "issues": (("Bir kayıt defterinin son sayfaları yırtılmış; kimin yaptığı belli değil.",
                    "Bir kayıt defterinin son sayfalarını yırtmışlar; kimin yaptığını bulmak istiyorum."),
                   ("Raflardaki kutuların bazıları gece yer değiştirmiş gibi duruyor.",
                    "Raflardaki bazı kutular gece yer değiştirmiş; kimin dokunduğunu öğrenmek istiyorum.")),
    },
    "smithy": {
        "stems": ("demirci", "demirhane"), "suffix": "Demirhanesi", "noun": "demirhane", "role": "Demirci",
        "descriptions": ("Körüğün soluğu ve çekiç sesiyle dolu, isli bir dükkân.",
                         "Sıcak, kara duvarlı bir atölye; kapısı sokağa açık duruyor."),
        "feature": ("Örs", "Kararmış, kenarı çentikli ağır bir örs; yanında bir kova su duruyor.",
                    ["ors", "kova", "korük", "korugu", "cekic"]),
        "activities": (("Kızgın bir nalı örsün üzerinde düzeltiyor.", "Bir nalı düzeltiyorum."),
                       ("Körüğü sabırla çalıştırıp ateşi canlandırıyor.", "Ateşi canlı tutmaya uğraşıyorum.")),
        "issues": (("Duvarda, sahibinin almaya gelmediği bir kılıç asılı duruyor.",
                    "Siparişini almaya gelmeyen birinin kılıcı günlerdir duvarımda asılı; sahibini bulmak isterim."),
                   ("Ocağın yanındaki kömür yığını epey azalmış.",
                    "Kömürcü iki gündür uğramadı; ateşi zor besliyorum.")),
    },
    "temple": {
        "stems": ("tapina", "mabet", "mabed"), "suffix": "Tapınağı", "noun": "tapınak", "role": "Rahip",
        "descriptions": ("Mum ışığının titrediği, sessiz ve serin bir iç mekân.",
                         "Yüksek pencereli, taş zeminli küçük bir mabet."),
        "feature": ("Mumlu sunak", "Üstünde erimiş mum kalıntıları olan, basit taş bir sunak.",
                    ["sunak", "mum", "mumlar"]),
        "activities": (("Sunaktaki mumları tek tek yeniliyor.", "Sunaktaki mumları yeniliyorum."),
                       ("Kısık sesle bir dua mırıldanıyor.", "Sabah duasını bitirmeye çalışıyorum.")),
        "issues": (("Bağış kutusunun kilidinde taze çizikler var.",
                    "Bağış kutusunun kilidini kurcalamışlar; eksik bir şey yok ama içim rahat değil."),
                   ("Kapının önünde kurumuş birkaç çiçek duruyor.",
                    "Her sabah kapının önüne kuru çiçek bırakılıyor; kimin bıraktığını merak ediyorum.")),
    },
    "harbor": {
        "stems": ("liman", "iskele", "rihtim"), "suffix": "İskelesi", "noun": "iskele", "role": "Liman işçisi",
        "descriptions": ("Tuzlu rüzgârın estiği, tahtaları yosun tutmuş bir iskele.",
                         "Sandıkların ve halatların arasında martıların bağrıştığı bir rıhtım."),
        "feature": ("Halat yığını", "Islak, kalın halatlardan oluşan dağınık bir yığın.",
                    ["halat", "yigin", "halatlar"]),
        "activities": (("Bir sandığı iple bağlıyor.", "Sandıkları bağlıyorum."),
                       ("Ağları kurumaya seriyor.", "Ağları kurumaya seriyorum.")),
        "issues": (("Sandık dizisinde bir boşluk göze çarpıyor.",
                    "Dün gece iskeleden bir sandık kayboldu; kimse görmemiş."),
                   ("Bir teknenin bağlama halatının ucu temiz bir şekilde kesilmiş.",
                    "Birinin teknesinin halatını kesmişler; sahibi küplere bindi.")),
    },
    "market": {
        "stems": ("pazar", "carsi"), "suffix": "Pazarı", "noun": "pazar", "role": "Seyyar satıcı",
        "descriptions": ("Tezgâhların arasında bağrışmaların yükseldiği kalabalık bir alan.",
                         "Bez gölgeliklerin altında sebze ve kumaş satılan küçük bir meydan."),
        "feature": ("Elma tezgâhı", "Üzerinde ezik ve sağlam elmaların karıştığı eğreti bir tezgâh.",
                    ["tezgah", "elma", "elmalar"]),
        "activities": (("Elmaları renklerine göre diziyor.", "Elmaları diziyorum."),
                       ("Gelip geçenlere fiyat sesleniyor.", "Müşteri çağırıyorum.")),
        "issues": (("Tezgâhın bir köşesi boşalmış gibi duruyor.",
                    "Sabahtan beri tezgâhımdan küçük şeyler eksiliyor."),
                   ("Yan tezgâhtaki satıcıyla arasında gergin bir sessizlik var.",
                    "Yan tezgâhtakiyle yer yüzünden atıştık; hâlâ sinirliyim.")),
    },
    "library": {
        "stems": ("kutuphane",), "suffix": "Kütüphanesi", "noun": "kütüphane", "role": "Kütüphaneci",
        "descriptions": ("Fısıltıların bile yankılandığı, uzun okuma masalı bir salon.",),
        "feature": ("Okuma masası", "Kenarları aşınmış, üstünde açık bırakılmış bir kitap duran uzun masa.",
                    ["masa", "kitap", "okuma masasi"]),
        "activities": (("Geri getirilen kitapları yerlerine diziyor.", "Gelen kitapları yerine diziyorum."),),
        "issues": (("Raflardan birinde, bir kitabın olması gereken yerde boşluk var.",
                    "Ödünç verdiğim bir harita kitabı geri gelmedi."),),
    },
    "bakery": {
        "stems": ("firin",), "suffix": "Fırını", "noun": "fırın", "role": "Fırıncı",
        "descriptions": ("Taze ekmek kokusunun sokağa taştığı sıcak bir dükkân.",),
        "feature": ("Taş fırın", "Ağzı kızıl kızıl parlayan, kubbeli bir taş fırın.", ["tas firin", "kurek"]),
        "activities": (("Uzun bir kürekle fırından somun çıkarıyor.", "Somunları fırından çıkarıyorum."),),
        "issues": (("Köşedeki un çuvallarından birinin dibinde küçük bir delik var.",
                    "Un çuvallarımdan biri delinmiş; fare mi başka bir şey mi bilmiyorum."),),
    },
    "workshop": {
        "stems": ("atolye", "marangoz"), "suffix": "Atölyesi", "noun": "atölye", "role": "Usta",
        "descriptions": ("Talaş kokulu, aletlerin duvarlara asılı olduğu bir atölye.",),
        "feature": ("Çalışma tezgâhı", "Üzerinde yarım kalmış bir sandık duran, çentikli bir tezgâh.",
                    ["tezgah", "sandik", "alet"]),
        "activities": (("Bir sandık kapağını rendeliyor.", "Bir sandık kapağını rendeliyorum."),),
        "issues": (("Duvardaki alet askısında bir yer boş duruyor.", "En iyi rendem ortadan kayboldu."),),
    },
    "barracks": {
        "stems": ("kisla", "karakol"), "suffix": "Karakolu", "noun": "karakol", "role": "Nöbetçi çavuş",
        "descriptions": ("Mızrakların duvara dayandığı, sert ışıklı küçük bir karakol.",),
        "feature": ("Silah askısı", "Birkaç mızrak ve kalkanın asılı olduğu ahşap bir askı.",
                    ["aski", "mizrak", "kalkan"]),
        "activities": (("Nöbet çizelgesine isim yazıyor.", "Nöbet çizelgesini yazıyorum."),),
        "issues": (("Çizelgede bir ismin üstü kalın bir çizgiyle karalanmış.",
                    "Gece nöbetçilerimden biri vaktinde gelmedi."),),
    },
    "graveyard": {
        "stems": ("mezarli", "kabristan"), "suffix": "Mezarlığı", "noun": "mezarlık", "role": "Mezarcı",
        "descriptions": ("Eğri taşların ve yabani otların arasında sessiz bir mezarlık.",),
        "feature": ("Eğri mezar taşı", "Yazısı yarı silinmiş, bir yana yatmış eski bir mezar taşı.",
                    ["mezar tasi", "tas", "yazit"]),
        "activities": (("Bir mezarın çevresindeki otları temizliyor.", "Otları temizliyorum."),),
        "issues": (("Mezarlardan birinin başındaki fener sönük duruyor.",
                    "Bir mezarın başındaki fener her gece kendiliğinden sönüyor; açıklayamıyorum."),),
    },
    "stable": {
        "stems": ("ahir",), "suffix": "Ahırı", "noun": "ahır", "role": "Seyis",
        "descriptions": ("Saman ve at kokusunun yoğun olduğu, loş bir ahır.",),
        "feature": ("Saman balyaları", "Duvar dibine yığılmış, bağları gevşek saman balyaları.",
                    ["saman", "balya", "balyalar"]),
        "activities": (("Bir atın yelesini tarıyor.", "Atları tımar ediyorum."),),
        "issues": (("Bölmelerden birindeki at önündeki yeme dokunmamış.",
                    "Atlardan biri iki gündür yem yemiyor."),),
    },
}

_MOTION = re.compile(
    r"\b(?:gid|git|yonel|ugra|ugru|varmak|variyor|varacag|varir|ilerl|yuru|don(?:uyor|ecek|ucem|eyim|elim)"
    r"|doguru|dogru|gec(?:iyor|ecek))\w*\b"
)
_NEGATED_MOTION = re.compile(
    r"\b(?:gitm|gitme|yonelm|ugram|donm|yurum)\w*\b|\bgitmiyor\w*|\bistemiyorum\b"
)
_CONDITIONAL = re.compile(r"\b(?:eger|sayet|\w+(?:irsem|irsen|ersem|ersen|arsam|arsan)\b)")
_QUESTION = re.compile(r"\?|\b(?:nasil|nerede|nereden|ne kadar)\b")


def _fold(value: Any) -> str:
    return living_world.normalize_text(value)


def place_kind_in(text: Any) -> str | None:
    """Return the place kind named in the player's words, or None."""
    words = _fold(text).split()
    for kind, spec in PLACE_KINDS.items():
        for stem in spec["stems"]:
            if any(word.startswith(stem) for word in words):
                return kind
    return None


def is_local_place_visit(text: Any) -> str | None:
    """'Arşive gidiyorum', 'Marek'in bahsettiği demirciye uğruyorum' -> kind."""
    if not isinstance(text, str):
        return None
    folded = _fold(text)
    kind = place_kind_in(text)
    if kind is None or not _MOTION.search(folded):
        return None
    if _NEGATED_MOTION.search(folded) or _CONDITIONAL.search(folded) or _QUESTION.search(text.casefold()):
        return None
    return kind


def _pick(world: dict[str, Any], location_id: str, options: tuple, salt: str) -> Any:
    seed = living_world._campaign_seed(world)
    digest = hashlib.sha256(f"{seed}\x00{location_id}\x00{salt}".encode("utf-8")).digest()
    return options[int.from_bytes(digest[:4], "big") % len(options)]


def settlement_of(world: dict[str, Any], location_id: Any) -> str | None:
    """The city a local place belongs to (the location itself if it is the city)."""
    locations = world.get("locations", {})
    record = locations.get(location_id)
    if not isinstance(record, dict):
        return None
    if living_world.scene_kind(world, location_id) == "city":
        return location_id
    parent = record.get("parent_location_id")
    if isinstance(parent, str) and living_world.scene_kind(world, parent) == "city":
        return parent
    return None


def find_local_place(world: dict[str, Any], settlement_id: str, kind: str) -> dict[str, Any] | None:
    return next(
        (
            record for record in world.get("locations", {}).values()
            if isinstance(record, dict)
            and record.get("parent_location_id") == settlement_id
            and record.get("place_kind") == kind
        ),
        None,
    )


def mentioned_by(world: dict[str, Any], kind: str) -> str | None:
    """The NPC who last spoke about this kind of place, if any (provenance only)."""
    stems = PLACE_KINDS[kind]["stems"]
    flags = world.get("flags", {}) if isinstance(world.get("flags"), dict) else {}
    candidates = [flags.get("active_npc_id"), flags.get("last_npc_id")]
    for npc in world.get("npcs", []):
        if not isinstance(npc, dict) or npc.get("id") not in candidates:
            continue
        for entry in reversed(npc.get("memory", []) or []):
            if isinstance(entry, dict) and entry.get("speaker") == "npc":
                if any(stem in _fold(entry.get("text", "")) for stem in stems):
                    return npc["id"]
                break
    return None


def create_local_place(world: dict[str, Any], settlement_id: str, kind: str) -> dict[str, Any] | None:
    """Create the saved place record (no person yet). Idempotent per settlement+kind."""
    existing = find_local_place(world, settlement_id, kind)
    if existing:
        return existing
    locations = world.setdefault("locations", {})
    local = [
        r for r in locations.values()
        if isinstance(r, dict) and r.get("parent_location_id") == settlement_id and r.get("place_kind")
    ]
    if len(local) >= MAX_LOCAL_PLACES_PER_SETTLEMENT or len(locations) >= 80:
        return None
    spec = PLACE_KINDS[kind]
    number = max(1, int(world.get("next_location_number", 1)))
    while f"location_{number:03d}" in locations:
        number += 1
    location_id = f"location_{number:03d}"
    world["next_location_number"] = number + 1
    name = f"{living_world.stable_local_name(world, settlement_id, 'place:' + kind)} {spec['suffix']}"
    record = {
        "id": location_id,
        "name": name,
        "type": "building",
        "aliases": [spec["noun"], *spec["stems"], name],
        "description": _pick(world, location_id, spec["descriptions"], "description"),
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        "parent_location_id": settlement_id,
        "exit_location_id": settlement_id,
        "scene_kind": "building",
        "place_kind": kind,
        "local_issue": _pick(world, location_id, spec["issues"], "issue")[0],
        "tags": ["campaign_local", "lr00_p3_pilot"],
    }
    locations[location_id] = record
    return record


_APPEARANCES = (
    "Kolları sıvanmış, ellerinde işinin izleri olan orta yaşlı biri.",
    "İnce yapılı, dikkatli bakışlı, saçları ensesinde toplanmış biri.",
    "Geniş omuzlu, sakin hareketli, yıpranmış bir önlük giymiş biri.",
    "Genç sayılır; yüzünde yorgunlukla karışık bir merak var.",
)
_PERSONALITIES = (
    "Az konuşur ama söylediğini tartarak söyler.",
    "Meraklı ve konuşkan; yabancılara hemen soru sorar.",
    "Temkinli; güvenmeden önce karşısındakini süzer.",
    "Sıcakkanlı ama işi aksarsa çabuk sabırsızlanır.",
)


def resident_of(world: dict[str, Any], place_id: str) -> dict[str, Any] | None:
    return next(
        (
            npc for npc in world.get("npcs", [])
            if isinstance(npc, dict) and npc.get("place_role_of") == place_id
            and npc.get("location") == place_id
        ),
        None,
    )


def feature_of(world: dict[str, Any], place_id: str, name: str) -> dict[str, Any] | None:
    return next(
        (
            feature for feature in world.get("features", [])
            if isinstance(feature, dict) and feature.get("location") == place_id
            and str(feature.get("name", "")).casefold() == name.casefold()
        ),
        None,
    )


def furnish(world: dict[str, Any], record: dict[str, Any], *, create_npc, create_feature):
    """Ensure the place's one person and one detail exist. Reuses saved ones."""
    spec = PLACE_KINDS[record["place_kind"]]
    place_id = record["id"]
    npc = resident_of(world, place_id)
    if npc is None:
        npc = create_npc({
            "name": living_world.stable_local_name(world, place_id, spec["role"]),
            "role": spec["role"],
            "location": place_id,
            "appearance": _pick(world, place_id, _APPEARANCES, "appearance"),
            "personality": _pick(world, place_id, _PERSONALITIES, "personality"),
            "relationship": "neutral",
        })
        if isinstance(npc, dict):
            npc["place_role_of"] = place_id
            npc["role_known_to_player"] = True
            activity = _pick(world, place_id, spec["activities"], "activity")
            issue = _pick(world, place_id, spec["issues"], "issue")
            profile = npc.get("personal_profile")
            if isinstance(profile, dict):
                profile["occupation"] = f"Burada, {record['name']} içinde {spec['role'].casefold()} olarak çalışıyorum."
                profile["current_activity"] = activity[1]
                profile["immediate_goal"] = issue[1]
                profile["reason_for_being_here"] = "Burası benim işim; günüm burada geçer."
    name, description, aliases = spec["feature"]
    feature = feature_of(world, place_id, name) or create_feature({
        "location": place_id,
        "name": name,
        "description": description,
        "kind": "furnishing",
        "aliases": list(aliases),
    })
    return npc, feature


def arrival_text(world: dict[str, Any], record: dict[str, Any], npc, feature, *, first_visit: bool) -> str:
    spec = PLACE_KINDS[record["place_kind"]]
    parts = []
    if first_visit:
        parts.append(f"{record['name']} karşına çıkıyor ve içeri adım atıyorsun.")
        parts.append(str(record.get("description") or ""))
    else:
        parts.append(f"Yeniden {record['name']} içindesin; her şey bıraktığın gibi.")
    if isinstance(feature, dict):
        parts.append(str(feature.get("description") or ""))
    if isinstance(npc, dict):
        who = living_world.public_npc_name(npc)
        activity = _pick(world, record["id"], spec["activities"], "activity")[0]
        parts.append(f"{who} burada. {activity}")
    if first_visit and record.get("local_issue"):
        parts.append(str(record["local_issue"]))
    return " ".join(part.strip() for part in parts if part and part.strip())
