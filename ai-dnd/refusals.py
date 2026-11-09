"""The one table of refusal texts (Dilim 2, Task 13): what a fight or an action will not allow, in Turkish, saying why and
what can be done instead. `text_for` is the player's line, `note` also tells the narrator ("olmadı: ...") through the
turn notes, so a refused move is never narrated as done. The texts take only the facts the engine gives them
(`{weapon}`, `{have}`, `{names}`, `{item}`, `{left}`); a model's words never enter them (tasarım karar 52)."""
from __future__ import annotations

import logging

logger = logging.getLogger("refusals")

FALLBACK_TEXT = "Bu hamle şu an işlemedi; başka bir şey dene."

REFUSAL_TEXT: dict[str, str] = {
    # Named by the plan, word for word.
    "invalid_ready_trigger": "Hazırlanmak için neyi bekleyeceğini ve o olunca ne yapacağını söyle (ör. 'Haydut yaklaşırsa vururum').",
    "invalid_ready_response": "Hazırladığın karşılık bir saldırı ya da hızını aşmayan bir hareket olmalı.",
    "no_weapon": "Elinde ya da çantanda bununla vurabileceğin bir silah yok; yumrukla vurabilirsin.",
    "combat_travel": "Savaş sürerken buradan yürüyüp gidemezsin; bir rakibe yaklaşabilir, kaçmayı deneyebilir ya da yerinde kalabilirsin.",
    "out_of_turn": "Rakibin hamlesi sürüyor; önce onun ne yaptığını görüyorsun.",
    "reaction_pending": "Rakibin açık veriyor; önce bu ana ne yapacağına karar vermelisin.",
    "invalid_combat_target": "Burada öyle vurabileceğin biri yok.",
    "weapon_not_owned": "{weapon} yok; yumrukla vuruyorsun.",
    "nothing_to_draw": "olmadı: istediğin silah çantanda yok, kını ya da kabzası da yok; hiçbir şey çekilmedi (çantadaki silahlar: {have}).",
    "which_enemy": "Hangisine yaklaşıyorsun: {names}?",
    "spell_visibility_unknown": "Büyünün hedefini açıkça görmen gerekiyor; şu an bu büyü için yeterince net görünmüyor.",
    "parcel_not_here": "olmadı: {item} burada değil",
    "which_parcel": "olmadı: hangi işin eşyasını kastettiğin belli değil",
    "which_item_to_give": "olmadı: hangi eşyayı verdiğin belli değil",
    "approach_short": "{left} feet daha var; bu tur bu kadar yaklaşabildin.",
    "no_exit": "Buradan çıkış yok; dövüşmeye devam edebilirsin.",
    # The same, while a guard is arresting the player (a world_reactions hold with arrest).
    "no_exit_held": "Buradan çıkış yok; dövüşmeye devam edebilir ya da teslim olabilirsin.",
    # The same refusal, reached through the line that says "ready" with nothing after it.
    "ready_needs_trigger": "Hazırlanmak için neyi bekleyeceğini ve o olunca ne yapacağını söyle (ör. 'Haydut yaklaşırsa vururum').",
    # A click on the scene's event the engine will not take (ambient_actions; Dilim 3, Task 8).
    "event_expired": "Onlar çoktan dağıldı.",
    "event_already_resolved": "Bu karşılaşma zaten gelişti.",
    "combat": "Kavga sürerken buna yetişemezsin.",
    "promotion_unavailable": "Kalabalıkta onlara yaklaşacak yer bulamıyorsun.",
    "event_not_interactive": "Orada artık katılabileceğin bir şey yok.",
    "event_referent_missing": "Orada artık katılabileceğin bir şey yok.",
    "no_event": "Orada artık katılabileceğin bir şey yok.",
    # Everything else a fight or an action can say no to.
    "action_unavailable": "Bu tur bunun için kullanabileceğin bir hakkın kalmadı.",
    "actor_cannot_act": "Şu an bunu yapamazsın; durumun buna izin vermiyor.",
    "bonus_action_spent": "Bu turdaki ek eylemini zaten kullandın; sıradaki turu bekle.",
    "bonus_action_unavailable": "Şu an bunun için kullanabileceğin bir ek eylem yok.",
    "capability_unavailable": "Bu yeteneği şu an kullanamıyor.",
    "charmed_target_forbidden": "Seni büyüleyen kişiye saldıramazsın; büyü sürdükçe elin kalkmıyor.",
    "cleave_unavailable": "Bu vuruşun ardından ikinci bir hedefe geçme hakkın yok.",
    "combat_closed": "Bu dövüş artık bitti; vuracak kimse kalmadı.",
    "combat_required": "Bu hamle yalnız savaşın içinde yapılır.",
    "distance_unknown": "Rakibin ne kadar uzakta olduğu belli değil; önce yerini netleştir.",
    "equipment_unknown": "Hangi elinde ne tuttuğun belli değil; önce elindekini düzenle.",
    "incapacitated": "Bu yaratık artık bu yeteneği kullanamaz.",
    "invalid_action_grant": "Bu ek hak geçerli değil, kullanılamadı.",
    "invalid_action_sequence": "Bir turda bir ila sekiz adım yapabilirsin; hamleni daha sade anlat.",
    "invalid_attack_ability": "Bu silah ya da yetenek o özellikle kullanılamaz.",
    "invalid_attack_allowance": "Bu eylemdeki saldırı hakkı geçerli değil, vuruş yapılmadı.",
    "invalid_attack_choice": "Bu saldırı seçimi şu an geçerli değil; saldırını yeniden anlat.",
    "invalid_attack_origin": "Bu saldırının nereden geldiği belli değil; yeniden dene.",
    "invalid_attack_state": "Bu saldırı şu an hesaplanamadı; hamleni yeniden anlat.",
    "invalid_check_feature": "Bu yetenek bu sınama için kullanılamaz.",
    "invalid_cleave_target": "İkinci hedef, ilk hedefin hemen yanında duran başka bir rakip olmalı.",
    "invalid_combat_actor": "Bu hamleyi yapan kişi savaşın içinde değil.",
    "invalid_conversion_command": "Büyü yuvası dönüşümünü tek ve açık bir adım olarak söylemelisin.",
    "invalid_equipment_change": "Silahı bırakmak için elinde bir silah ve bir saldırı eylemi gerekir.",
    "invalid_exhaustion": "Tükenmişlik seviyesi geçersiz; bu hamle işlenmedi.",
    "invalid_fighter_command": "Bu savaşçı yeteneğini tek ve açık bir adım olarak söylemelisin.",
    "invalid_grip": "Silahı bu şekilde tutamazsın; bir ya da iki elle tutmayı seç.",
    "invalid_hands": "Bunun için ellerin yetmiyor; önce bir elini boşalt.",
    "invalid_monk_command": "Bu keşiş yeteneğini tek ve açık bir adım olarak söylemelisin.",
    "invalid_monster_event": "Bu rakip hamlesi geçerli değil, işlenmedi.",
    "invalid_movement": "Hareket için ayak cinsinden bir uzaklık söylemelisin (ör. '10 feet ilerliyorum').",
    "invalid_movement_routes": "Bu hareket yolu geçerli değil; daha basit bir yol söyle.",
    "invalid_paladin_command": "Bu paladin yeteneğini tek ve açık bir ek eylem adımı olarak söylemelisin.",
    "invalid_push_choice": "Bu itme seçimi desteklenmiyor; yeniden seç.",
    "invalid_rage_command": "Öfkeyi tek ve açık bir ek eylem adımı olarak söylemelisin.",
    "invalid_reaction_trigger": "Şu an tepki verebileceğin bir an yok.",
    "invalid_ready_spell_metadata": "Bu büyüyü hazırlık olarak bekletemezsin.",
    "invalid_resource_type": "Bu hak tanınan haklar arasında değil; başka bir şey dene.",
    "invalid_rogue_command": "Bu hırsız yeteneğini tek ve açık bir adım olarak söylemelisin.",
    "invalid_save_choice": "Bu kurtarma zarı seçimi geçerli değil.",
    "invalid_shove_choice": "İtmek için yere devirmeyi ya da beş feet geri itmeyi seç.",
    "invalid_species_action": "Bu tür yeteneğini şu an kullanamazsın.",
    "invalid_spell_slot_choice": "Büyü yuvası yalnız büyü yapılırken seçilir.",
    "invalid_spell_state": "Büyü yeteneğin şu an hesaplanamadı; büyü yapılmadı.",
    "invalid_spell_target": "Büyü için savaştaki bir yaratığı hedef göstermelisin.",
    "invalid_target_size": "Hedefin senden bir boydan fazla büyük; onu bu şekilde yakalayamazsın.",
    "invalid_unarmed_option": "Bu yumruk seçeneği tanınmıyor; vur, yakala ya da it.",
    "invalid_weapon_mode": "Bu silah o şekilde kullanılamaz.",
    "light_unavailable": "Hafif silahla ikinci vuruş için elinde farklı bir hafif silah ve kullanılmamış bir vuruş hakkı gerekir.",
    "loading_limit": "Bu silah her eylemde yalnız bir kez ateşlenir; yeniden doldurmayı bekle.",
    "mastery_unavailable": "Bu silah ustalığına sahip değilsin.",
    "movement_unavailable": "Bu kadar yol yürüyemezsin; hızın ya da yolun buna yetmiyor.",
    "nick_unavailable": "Bu ikinci vuruş için gereken silah ustalığına sahip değilsin.",
    "no_ammunition": "Cephanen kalmadı; bununla ateş edemezsin.",
    "no_attack_continuation": "Bu eylemde yapabileceğin başka bir saldırı kalmadı.",
    "out_of_range": "Hedef erişimin dışında; önce ona yaklaşmalısın.",
    "rage_spellcasting_forbidden": "Öfke sürerken büyü yapamazsın.",
    "reaction_spent": "Bu turdaki tepkini zaten kullandın.",
    "reckless_attack_unavailable": "Pervasız saldırı yalnız saldırı zarı atılan bir vuruşla yapılır.",
    "spell_components_unavailable": "Büyü için gereken sözleri ve el hareketlerini şu an yapamıyorsun.",
    "spell_mechanic_unavailable": "Bu büyünün etkisi henüz oyunda çözülmüyor.",
    "spell_not_available": "Bu büyüyü şu an yapamazsın; hazırladığın büyüler arasında değil.",
    "spell_out_of_range": "Hedef büyünün menzilinin dışında; yaklaş ya da başka bir büyü seç.",
    "spell_path_blocked": "Hedefle aranda büyünün geçebileceği açık bir yol yok.",
    "spell_save_modifier_unknown": "Hedefin çeviklik kurtarma zarı bilinmiyor; büyü yapılmadı.",
    "spell_slot_turn_limit": "Bir turda yalnız bir büyü yuvası harcayabilirsin.",
    "spell_slot_unavailable": "Seçtiğin seviyede büyü yuvan kalmadı.",
    "spell_target_required": "Büyü için hedefi açıkça söylemelisin.",
    "stale_combat": "Savaşın durumu değişmiş; ekranı yenileyip yeniden dene.",
    "too_many_monster_interrupts": "Aynı anda çok fazla rakip tepkisi birikti; sırayı ilerlet.",
    "total_cover": "Hedef tamamen siperde; ona doğrudan nişan alamazsın.",
    "unsupported_action": "Bu eylemi savaşta yapamazsın; saldır, hareket et, kaç ya da bekle.",
    "unsupported_action_sequence": "Bu bileşik hamle şu an desteklenmiyor; adımları tek tek söyle.",
    "unsupported_interaction_mode": "Savaş sürerken konuşamazsın; bir eylem söyle (saldır, yaklaş, kaç).",
    "unsupported_metamagic": "Bu büyü ayarı şu an desteklenmiyor.",
    "unsupported_spell": "Tek bir büyünün adını açıkça söylemelisin; bu büyü şu an desteklenmiyor.",
    "unsupported_spell_attack_mode": "Bu büyü saldırısı şu an desteklenmiyor.",
    "unsupported_spell_damage_mode": "Bu büyünün hasar etkisi şu an desteklenmiyor.",
    "unsupported_spell_mode": "Büyü için yalnız büyünün adını ve tek bir hedefi söylemelisin.",
    "unsupported_spell_progression": "Bu büyü yuvası şu an desteklenmiyor.",
    "unsupported_spell_save_mode": "Bu kurtarma zarı şekli şu an desteklenmiyor.",
    "unsupported_spell_target_mode": "Bu hedefe büyü yapmak şu an desteklenmiyor.",
    "weapon_not_held": "İstediğin silah elinde değil; önce onu eline almalısın.",
    "tactical_mind_immediate_check_only": "Taktik Zihin yalnız hemen yapılan bir sınamada kullanılır.",
    "primal_knowledge_immediate_check_only": "İlkel Bilgi yalnız hemen yapılan bir sınamada kullanılır.",
    # A counter asked for what its own list does not hold (Dilim 3, Task 27): `{have}` is that list.
    "not_sold_here": "Burada satılık {item} yok; bu tezgâhta {have} var.",
    "goods_unclear": "Ne almak istediğini anlayamadım; bu tezgâhta {have} var.",
    "coin_below_price": "{item} {price} bakır; uzattığın {coin} bakır bunu karşılamıyor.",
    # A turn the engine could not finish safely (HTTP 500, Dilim 3 Task 37): it was taken back whole.
    "engine_error": "Bu hamlenin sonucu oyunda doğrulanamadı; hiçbir şey değişmedi. Aynı şeyi yeniden ya da başka sözlerle dene.",
}


class _Facts(dict):
    def __missing__(self, key):
        return ""


def text_for(code: str, **facts) -> str:
    """The Turkish line for a refusal code; an unknown code is logged and still answered in Turkish."""
    template = REFUSAL_TEXT.get(code)
    if template is None:
        logger.warning("refusal code without a Turkish text: %s", code)
        return FALLBACK_TEXT
    return template.format_map(_Facts(facts))


def note(session, code: str, *, npc_id: str | None = None, **facts) -> str:
    """The refusal as a turn note ("olmadı: ..."), so the narrator hears the move did not happen; returns the text."""
    text = text_for(code, **facts)
    if not text.startswith("olmadı:"):
        text = "olmadı: " + text
    if getattr(session, "_turn_notes", None) is None:
        session._turn_notes = []
    session._turn_notes.append((npc_id, text))
    return text
