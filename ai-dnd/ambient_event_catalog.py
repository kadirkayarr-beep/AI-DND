"""Small, bounded scene events used by the existing living-world scene state."""

from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from typing import Any


def _event(
    event_id: str,
    event_type: str,
    kinds: str,
    text: str,
    aliases: str = "",
    *,
    group: str,
    times: str = "",
    weather: str = "",
    environments: str = "",
    backgrounds: str = "",
    origins: str = "",
    max_npcs: int | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "variation_id": "v1",
        "event_type": event_type,
        "kinds": tuple(kinds.split("|")),
        "text": text,
        "aliases": tuple(item for item in aliases.split("|") if item),
        "repeat_group": group,
        "times": tuple(item for item in times.split("|") if item),
        "weather": tuple(item for item in weather.split("|") if item),
        "environments": tuple(
            item for item in environments.split("|") if item
        ),
        "backgrounds": tuple(
            item.casefold() for item in backgrounds.split("|") if item
        ),
        "origins": tuple(item.casefold() for item in origins.split("|") if item),
        "max_npcs": max_npcs,
        "weight": 1,
    }


# GREEN events are presentation-only. BLUE events create a temporary,
# location-scoped referent in living_world.py so players can address it.
EVENT_CATALOG: tuple[dict[str, Any], ...] = (
    _event("city_baker", "BLUE", "city|tavern", "Bir fırıncı, tezgâhtaki son ekmekleri aceleyle yeniden dizer.", "fırıncı|ekmek tezgâhı", group="market", times="dawn|day", backgrounds="Artisan|Merchant"),
    _event("city_cart_wheel", "BLUE", "city|village|road", "Bir yük arabasının tekeri taşların arasına sıkışır; sürücüsü çevreden yardım ister gibi bakınır.", "araba|teker|sürücü", group="street_work", max_npcs=7),
    _event("city_guard_shift", "BLUE", "city|building", "İki muhafız kısa bir nöbet değişimi yapar; biri eldivenini düzeltirken öteki kapıya yönelir.", "muhafız|nöbet değişimi", group="guards", times="dawn|day|evening", backgrounds="Soldier|Guard", max_npcs=10),
    _event("city_vendor_bargain", "BLUE", "city|village|tavern", "Bir seyyar satıcıyla müşteri, küçük bir eşyanın fiyatı üzerine pazarlık eder.", "satıcı|müşteri|pazarlık", group="market", times="day|evening", backgrounds="Merchant|Charlatan"),
    _event("city_lost_ring", "BLUE", "city|tavern|temple", "Bir yolcu yerde bir yüzük arar; telaşını saklayamaz.", "yolcu|yüzük|yerde arayan kişi", group="lost_property", environments="city|temple"),
    _event("city_prayer", "GREEN", "city|temple|village", "Bir rahip, geçenlere kısa bir dua diler; kimseyi durdurmaz.", group="faith", times="dawn|day", environments="temple"),
    _event("city_children_run", "GREEN", "city|village", "İki çocuk dar bir aralıktan kahkahalarla geçip kalabalığın içinde kaybolur.", group="children", times="day|evening", weather="clear|unknown", max_npcs=12),
    _event("city_street_artist", "BLUE", "city|tavern", "Bir sokak sanatçısı birkaç dinleyici toplar ve gösterisini yeni baştan kurar.", "sanatçı|gösteri|dinleyiciler", group="street_performance", times="day|evening", backgrounds="Entertainer", max_npcs=14),
    _event("city_dropped_purse", "BLUE", "city|tavern|road", "Bir kişi yürürken küçük bir keseyi düşürür ve henüz fark etmeden ilerler.", "kese|keseyi düşüren kişi", group="lost_property", max_npcs=10),
    _event("city_guard_yawn", "GREEN", "city|building", "Kapıdaki muhafız esneyip omuzlarını gerer, ardından yeniden sokağı izlemeye koyulur.", group="guards", times="dawn|night", backgrounds="Soldier|Guard"),
    _event("city_workers_load", "GREEN", "city|village|road", "Üç işçi ağır bir sandığı kısa aralıklarla el değiştirerek taşır.", group="street_work", times="day|evening", backgrounds="Artisan|Farmer", max_npcs=12),
    _event("city_priest_watches", "BLUE", "city|temple", "Sessiz bir rahip, kalabalığın içinden birini dikkatle izler; nedenini belli etmez.", "rahip|sessiz kişi", group="faith", environments="temple"),
    _event("city_advice", "GREEN", "city|tavern|village", "Yaşlı bir gezgin, genç birine alçak sesle öğüt verir; sözlerin çoğu kalabalıkta kaybolur.", group="conversation", backgrounds="Sage|Hermit"),
    _event("city_angry_price", "BLUE", "city|tavern", "Bir tüccar, müşteriyle fiyat konusunda anlaşamayınca sesini yükseltir.", "tüccar|müşteri|fiyat", group="market", times="day|evening", backgrounds="Merchant"),
    _event("city_weapon_glance", "GREEN", "city|village|tavern", "Bir çocuk, yakındaki silaha kısa bir merakla bakar; yanında yürüyen yetişkin onu nazikçe çağırır.", group="children", times="day|evening", weather="clear|unknown", max_npcs=12),
    _event("city_bell", "GREEN", "city|village|temple", "Uzaklardan tek bir çan sesi gelir ve sokakların üzerinde kısa süre asılı kalır.", group="distant_sound", environments="city|village|temple"),
    _event("city_slammed_door", "GREEN", "city|building|tavern", "Yakındaki bir kapı sertçe kapanır; ardından içeriden anlaşılmayan birkaç söz duyulur.", group="doors", environments="city|tavern|castle"),
    _event("city_cat_between", "GREEN", "city|tavern|village", "Bir kedi iki kişinin arasından süzülür ve güneş alan bir basamağa kıvrılır.", group="animals", weather="clear|unknown"),
    _event("city_dogs_bark", "GREEN", "city|village|road", "Sokağın ilerisinde bir köpek havlar; başka bir köpek kısa bir karşılık verir.", group="animals", max_npcs=12),
    _event("city_drunk_wall", "BLUE", "city|tavern", "Sarhoş bir yolcu duvara yaslanıp dengesini toplamaya çalışır.", "sarhoş|yolcu|duvara yaslanan kişi", group="traveler", times="evening|night", weather="clear|rain|fog|unknown"),
    _event("city_hat_rain", "GREEN", "city|road|village", "Yağmurda yürüyen biri şapkasını tutarken diğer eliyle pelerininin yakasını kapatır.", group="weather", weather="rain|storm"),
    _event("city_small_crowd", "GREEN", "city|tavern|village", "Küçük bir kalabalık bir tezgâhın önünde oluşup birkaç dakika içinde dağılır.", group="crowds", times="day|evening", max_npcs=16),
    _event("city_hurried_runner", "BLUE", "city|road|building", "Bir haberci kalabalığın arasından aceleyle geçer, kimseye çarpmamaya çalışır.", "haberci|aceleyle geçen kişi", group="travelers", times="day|evening", backgrounds="Soldier|Scribe"),
    _event("city_step_aside", "GREEN", "city|village", "Bir yaya, geçişi daraltmamak için sessizce kenara çekilir.", group="crowds", max_npcs=16),
    _event("city_peddler_moves", "BLUE", "city|village|road", "Seyyar bir satıcı, tezgâhını toplayıp yakındaki başka bir sokağa taşınır.", "seyyar satıcı|tezgâhını toplayan kişi", group="market", times="day|evening", backgrounds="Merchant"),
    _event("city_market_check", "BLUE", "city|village", "Bir muhafız pazar girişinde arabaları sırayla kontrol eder.", "muhafız|pazar girişi|araba", group="guards", times="day", backgrounds="Soldier|Guard", max_npcs=14),
    _event("city_laundry_wind", "GREEN", "city|village|building", "Bir avluda asılı çamaşırlar rüzgârla savrulur; biri mandalları yeniden tutturur.", group="daily_work", weather="clear|wind|unknown"),
    _event("city_water_carrier", "BLUE", "city|village", "Bir su taşıyıcısı yükünü yere bırakıp bileğini dinlendirir.", "su taşıyıcısı|su testileri", group="daily_work", times="day", backgrounds="Farmer|Laborer"),
    _event("city_small_argument", "BLUE", "city|tavern|village", "İki esnaf kısa bir tartışmaya tutuşur; biri avucunu tezgâha vurur.", "esnaf|tartışan kişiler", group="conversation", times="day|evening", backgrounds="Merchant|Artisan"),
    _event("city_street_musician", "BLUE", "city|tavern|village", "Bir sokak müzisyeni yanlış bir nota çalıp gülümser ve ezgiye yeniden başlar.", "müzisyen|ezgi|yanlış nota", group="street_performance", times="day|evening", backgrounds="Entertainer"),
    _event("city_distant_chimes", "GREEN", "city|village|temple", "Uzak bir kuleden peş peşe birkaç çan sesi yükselir.", group="distant_sound", environments="city|village|temple"),
    _event("city_seller_pitch", "BLUE", "city|village|tavern", "Bir satıcı, mallarını yüksek sesle överken çevresinden geçenleri gülümseyerek selamlar.", "satıcı|mallarını öven kişi", group="market", times="day|evening", backgrounds="Merchant|Charlatan"),
    _event("city_directions", "BLUE", "city|village|road", "İki gezgin bir yol tarifi üzerinde anlaşamayınca haritayı tekrar açar.", "gezginler|harita|yol tarifi", group="travelers", times="day|evening", backgrounds="Guide|Sailor"),
    _event("city_open_shutters", "GREEN", "city|village|building", "Bir dükkân kepengi açılır ve içeriden taze ekmek kokusu sokağa yayılır.", group="daily_work", times="dawn|day"),
    _event("city_close_shutters", "GREEN", "city|village|building", "Bir dükkân sahibi kepenkleri indirirken son müşterisine başıyla veda eder.", group="daily_work", times="evening|night"),
    _event("city_rain_gutter", "GREEN", "city|building|tavern", "Çatı oluğundan biriken yağmur suyu taşların üzerine düzenli aralıklarla damlar.", group="weather", weather="rain|storm"),
    _event("city_fog_lantern", "GREEN", "city|road|village", "Sis, sokağın sonundaki feneri soluk bir ışık halkasına dönüştürür.", group="weather", weather="fog", times="dawn|night"),
    _event("city_snow_sweep", "GREEN", "city|village|building", "Bir dükkân sahibi kapısının önündeki karı küçük bir kürekle kenara iter.", group="weather", weather="snow", times="dawn|day"),
    _event("city_soldier_patrol", "GREEN", "city|building", "Bir devriye sokağın köşesini dönüp düzenli adımlarla uzaklaşır.", group="guards", times="evening|night", backgrounds="Soldier|Guard"),
    _event("city_beggar_dispute", "BLUE", "city|temple|tavern", "İki yolcu, bir bankın yanında alçak sesle tartışır; biri avucunu uzatıp sonra geri çeker.", "yolcu|bank|tartışan kişiler", group="conversation", environments="city|temple"),
    _event("city_child_coin", "BLUE", "city|village|tavern", "Bir çocuk taşların arasında bozuk para arar, başını kaldırıp çevresine bakar.", "çocuk|bozuk para|para arayan kişi", group="children", times="day|evening", weather="clear|unknown"),
    _event("city_lantern_flicker", "GREEN", "city|building|road", "Bir sokak lambasının alevi titrer, sonra yeniden sabitlenir.", group="light", times="evening|night", weather="wind|rain|storm|unknown"),
    _event("city_fish_cart", "BLUE", "city|village|tavern", "Bir balıkçı, ağlarını tezgâhın kenarına serip düğümlerini çözmeye başlar.", "balıkçı|ağlar|tezgâh", group="daily_work", times="dawn|day", backgrounds="Sailor|Fisher", origins="harbor|liman|kıyı|sahil|deniz|coast"),
    _event("city_carriage_stuck", "BLUE", "city|road", "Bir at arabası dar geçitte sıkışır; sürücüsü kalabalıktan yol açmasını ister.", "at arabası|sürücü|dar geçit", group="street_work", times="day|evening", max_npcs=12),
    _event("city_tavern_server", "GREEN", "tavern", "Bir çalışan boş kupaları toplarken tezgâhın arkasından kısa bir selam verir.", group="tavern_service", times="day|evening|night", environments="tavern"),
    _event("city_tavern_cook", "BLUE", "tavern", "Mutfaktan bir aşçı başını uzatıp eksik bir malzemeyi sorar.", "aşçı|mutfak|malzeme", group="tavern_service", times="day|evening", environments="tavern", backgrounds="Artisan|Farmer"),
    _event("city_tavern_story", "BLUE", "tavern", "Bir gezgin, masadakilere uzun bir yolculuğun yalnızca ilk kısmını anlatır.", "gezgin|hikâye|yolculuk", group="tavern_talk", times="evening|night", backgrounds="Sailor|Guide"),
    _event("city_tavern_chair", "GREEN", "tavern", "Bir sandalye gıcırdar; oturan kişi ağırlığını değiştirip sohbetine devam eder.", group="tavern_detail", times="day|evening|night"),
    _event("city_tavern_song", "BLUE", "tavern", "Bir masadan başlayan mırıldanma kısa bir ezgiye dönüşür, sonra kahkahalarla kesilir.", "ezgi|şarkı|masa", group="tavern_talk", times="evening|night", backgrounds="Entertainer"),
    _event("city_tavern_spill", "BLUE", "tavern", "Bir müşteri kupasını devirmeden son anda yakalar; yanındaki kişi peçete uzatır.", "müşteri|kupa|peçete", group="tavern_detail", times="day|evening|night"),
    _event("wild_bird_call", "GREEN", "wilderness|road", "Yakındaki çalılıktan kısa bir kuş ötüşü gelir; ardından çevre yeniden sessizleşir.", group="wildlife", environments="forest|wilderness"),
    _event("wild_branch", "GREEN", "wilderness|road", "Rüzgâr, yol kenarındaki kuru bir dalı taşların üzerinde yuvarlar.", group="weather", weather="wind|storm|unknown"),
    _event("wild_tracks", "BLUE", "wilderness|road", "Çamurun kenarında küçük hayvan izleri görülür; yağış izlerin bir bölümünü yumuşatmıştır.", "izler|çamur|hayvan izleri", group="wildlife", weather="rain|storm|clear|unknown", environments="forest|wilderness|road"),
    _event("wild_stream", "GREEN", "wilderness|road", "Yolun aşağısından akan suyun sesi duyulur; akıntının üstünde birkaç yaprak döner.", group="water", environments="forest|wilderness"),
    _event("wild_camp_smoke", "BLUE", "wilderness|road", "Ağaçların ötesinde ince bir duman yükselir; kaynağı görünmez.", "duman|ağaçların ötesi", group="distant_activity", times="dawn|day|evening", environments="forest|wilderness"),
    _event("wild_owl", "GREEN", "wilderness|road", "Gece kuşunun sesi karanlığın içinden gelir ve uzaklaşır.", group="wildlife", times="night", environments="forest|wilderness"),
    _event("wild_rain_leaves", "GREEN", "wilderness|road", "Yağmur damlaları geniş yapraklardan toprağa ağır ağır düşer.", group="weather", weather="rain|storm", environments="forest|wilderness"),
    _event("wild_deer_glimpse", "GREEN", "wilderness|road", "Ağaçların arasında bir geyik silueti belirip gözden kaybolur.", group="wildlife", times="dawn|day|evening", environments="forest|wilderness"),
    _event("wild_traveler", "BLUE", "wilderness|road", "Yol kenarında bir gezgin çantasını yere bırakıp haritasını inceler.", "gezgin|çanta|harita", group="travelers", backgrounds="Guide|Sailor|Wayfarer", origins="forest|orman|kuzey|dağ|mountain"),
    _event("building_scribe", "BLUE", "building|temple", "Bir kâtip, kayıt defterindeki satırı yeniden okuyup mürekkebin kurumasını bekler.", "kâtip|kayıt defteri|defter", group="daily_work", backgrounds="Scribe|Sage"),
    _event("building_stair", "GREEN", "building|tavern|temple", "Üst kattan birkaç ayak sesi iner, kapı açılır ve sonra yeniden kapanır.", group="building_sounds", environments="castle|temple|tavern"),
    _event("building_candle", "GREEN", "building|temple|tavern", "Bir mumun alevi kısa süre eğilir; balmumu tabağın kenarına doğru akar.", group="light", times="evening|night", weather="wind|storm|unknown"),
    _event("building_courier", "BLUE", "building|city|temple", "Bir ulak kapının önünde durup içeriden yanıt bekler.", "ulak|kapı|haberci", group="travelers", times="day|evening", backgrounds="Scribe|Noble"),
    _event("building_prayer", "GREEN", "building|temple", "Bir ziyaretçi başını eğip sessizce dua eder, sonra kapıya yönelir.", group="faith", times="dawn|day|evening", environments="temple"),
    _event("building_wind", "GREEN", "building|castle|ruins", "Koridordan geçen hava, gevşek bir perdeyi hafifçe kıpırdatır.", group="weather", environments="castle|ruins"),
)


def _normalize(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    plain = plain.replace("ı", "i")
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def select_ambient_event(
    *,
    scene_kind: str,
    location_id: str,
    turn_index: int,
    context: dict[str, Any],
    history: list[dict[str, Any]],
    campaign_seed: str,
    allowed_types: set[str] | None = None,
) -> dict[str, Any] | None:
    """Choose one context-compatible event without repeating recent groups."""
    candidates = [
        event
        for event in EVENT_CATALOG
        if scene_kind in event["kinds"]
        and (allowed_types is None or event["event_type"] in allowed_types)
        and (not event["times"] or context.get("time_of_day") in event["times"])
        and (not event["weather"] or context.get("weather") in event["weather"])
        and (
            not event["environments"]
            or context.get("environment") in event["environments"]
        )
        and (
            event["max_npcs"] is None
            or int(context.get("npc_density", 0)) <= event["max_npcs"]
        )
    ]
    if not candidates:
        return None

    recent = history[-12:]
    recent_ids = {item.get("event_id") for item in recent[-8:]}
    recent_groups = {item.get("repeat_group") for item in recent[-4:]}
    fresh = [
        event for event in candidates
        if event["event_id"] not in recent_ids
        and event["repeat_group"] not in recent_groups
    ]
    if not fresh:
        fresh = [
            event for event in candidates
            if event["event_id"] not in {
                item.get("event_id") for item in recent[-3:]
            }
        ]
    if not fresh:
        fresh = candidates

    background = _normalize(context.get("background"))
    origin = _normalize(context.get("origin"))
    weighted: list[tuple[dict[str, Any], int]] = []
    for event in fresh:
        weight = int(event["weight"])
        if any(_normalize(tag) in background for tag in event["backgrounds"]):
            weight += 2
        if any(_normalize(tag) in origin for tag in event["origins"]):
            weight += 1
        weighted.append((event, weight))

    digest = hashlib.sha256(
        f"{campaign_seed}|{location_id}|{turn_index}|{len(history)}".encode("utf-8")
    ).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    return dict(rng.choices(
        [item[0] for item in weighted],
        weights=[item[1] for item in weighted],
        k=1,
    )[0])