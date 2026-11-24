import game
import action_economy
import adventure
from api.dnd_2024_rules import get_expertise_choice_count
import campaign_time
import copy
import equipment_economy
import held_weapon
import initiative
import interaction_adventure
import json
import living_world
import local_exploration
import monster_sense
from pathlib import Path
import re
import scheduled_events
import talk_mode
import tempfile
import timed_gameplay
import weapon_attack


SAVE_FORMAT_VERSION = 4

_SUPPORTED_SAVE_VERSIONS = (1, 2, 3, 4, 5, 6)

def _validate_species_trait_state(value, species, proficiency_bonus=2):
    if not isinstance(value, dict):
        raise ValueError("Kayıt tür yetenekleri geçersiz.")
    limits = game._new_species_trait_state(species, proficiency_bonus)
    expected = set(limits)
    if set(value) - {"effect_clock"} != expected:  # K03: optional, versioned; older saves lack it
        raise ValueError("Kayıt tür yetenek alanları geçersiz.")
    if "effect_clock" in value:
        game.effect_lifecycle.validate_clock(value["effect_clock"])
    integer_fields = (
        "healing_hands_uses_remaining",
        "celestial_revelation_uses_remaining",
        "celestial_revelation_turns_remaining",
        "giant_ancestry_uses_remaining",
        "large_form_uses_remaining",
        "large_form_turns_remaining",
        "adrenaline_rush_uses_remaining",
        "temporary_hit_points",
        "movement_budget_ft",
        "player_turn_counter",
    )
    if any(
        type(value.get(field)) is not int or value[field] < 0
        for field in integer_fields
    ):
        raise ValueError("Kayıt tür yetenek sayacı geçersiz.")
    if any(
        type(value.get(field)) is not bool
        for field in ("giant_ancestry_armed", "relentless_endurance_available")
    ):
        raise ValueError("Kayıt tür yetenek durumu geçersiz.")
    form = value.get("active_celestial_form")
    if form is not None and form not in game.CELESTIAL_REVELATION_FORMS:
        raise ValueError("Kayıt göksel biçimi geçersiz.")
    if (
        (form is None and value["celestial_revelation_turns_remaining"])
        or (form is not None and not 1 <= value["celestial_revelation_turns_remaining"] <= 10)
        or (form is not None and species != "Aasimar")
    ):
        raise ValueError("Kayıt göksel biçim süresi geçersiz.")
    for field in (
        "healing_hands_uses_remaining",
        "celestial_revelation_uses_remaining",
        "giant_ancestry_uses_remaining",
        "large_form_uses_remaining",
        "adrenaline_rush_uses_remaining",
    ):
        if value[field] > limits[field]:
            raise ValueError("Kayıt tür yeteneği kullanım sınırı geçersiz.")
    if (
        value["large_form_turns_remaining"] > 100
        or (species != "Goliath" and value["large_form_turns_remaining"] != 0)
        or (species != "Goliath" and value["giant_ancestry_armed"])
        or (
            value["giant_ancestry_armed"]
            and value["giant_ancestry_uses_remaining"] == 0
        )
        or (species != "Orc" and value["adrenaline_rush_uses_remaining"] != 0)
        or (
            species not in {"Orc", "Half-Orc"}
            and value["relentless_endurance_available"]
        )
        or value["temporary_hit_points"] > proficiency_bonus
    ):
        raise ValueError("Kayıt tür yeteneği durumu tutarsız.")
    used_round = value.get("bonus_action_used_round")
    if used_round is not None and (
        type(used_round) is not int or used_round < 1
    ):
        raise ValueError("Kayıt bonus eylem durumu geçersiz.")
    used_turn = value.get("celestial_damage_used_turn")
    if used_turn is not None and (type(used_turn) is not int or used_turn < 0):
        raise ValueError("Kayıt göksel hasar durumu geçersiz.")
    movement_effect = value.get("movement_effect")
    if movement_effect is not None and not isinstance(movement_effect, dict):
        raise ValueError("Kayıt hareket etkisi geçersiz.")

def _origin_choices_valid(choices):
    """C02: the shape of the saved origin choices; anything else is refused, never silently reshaped."""
    if not isinstance(choices, dict) or set(choices) - set(game._ORIGIN_TEXT_KEYS + game._ORIGIN_LIST_KEYS + game._ORIGIN_SCORE_KEYS):
        return False
    for key in game._ORIGIN_TEXT_KEYS:
        if key in choices and not (choices[key] is None or (type(choices[key]) is str and 0 < len(choices[key]) <= 60)):
            return False
    from api.dnd_2024_rules import BACKGROUND_DEFINITIONS
    if choices.get("background") is not None and "background" in choices and choices["background"] not in BACKGROUND_DEFINITIONS:
        return False  # a background the rules do not know is refused, never kept as free text
    bonuses = choices.get("background_ability_bonuses")
    if bonuses is not None:
        positive = sorted(value for value in bonuses.values() if value > 0)
        if any(value < 0 or value > 2 for value in bonuses.values()) or positive not in ([], [1, 2], [1, 1, 1]):
            return False  # the book allows +2/+1 or +1/+1/+1 only
    for key in game._ORIGIN_LIST_KEYS:
        if key in choices and not (type(choices[key]) is list and len(choices[key]) <= 24
                                   and all(type(item) is str and 0 < len(item) <= 60 for item in choices[key])):
            return False
    for key in game._ORIGIN_SCORE_KEYS:
        if key in choices and not (type(choices[key]) is dict and set(choices[key]) <= set(game._ABILITY_NAMES)
                                   and all(type(value) is int and 0 <= value <= 30 for value in choices[key].values())):
            return False
    return True

def _origin_choices_for_save(character):
    """The player's creation choices (background, score split, languages, ...); written only when the character has them."""
    choices = {key: copy.deepcopy(character[key]) for key in game._ORIGIN_TEXT_KEYS + game._ORIGIN_LIST_KEYS + game._ORIGIN_SCORE_KEYS
               if key in character}
    if choices and not game._origin_choices_valid(choices):
        raise ValueError("Origin choice state is invalid.")
    return choices

_PERSISTED_PLAYER_CONDITION_FIELDS = (
    "conditions", "charmed_by", "frightened_by", "grappled_by", "grapple_escape_dc",
    "prone", "frightened_until_player_turn", "speed_penalty_ft", "speed_penalty_turns_remaining",
)

def _validate_player_condition_state(player):
    """Validate existing sparse condition metadata, not effect eligibility/lifetimes."""
    if "conditions" in player:
        names = player["conditions"]
        if not isinstance(names, (list, dict)):
            raise ValueError("Saved player conditions must be a list or boolean mapping.")
        if any(not isinstance(name, str) or not name.strip() for name in names):
            raise ValueError("Saved player condition names must be nonempty strings.")
        if isinstance(names, dict) and any(type(value) is not bool for value in names.values()):
            raise ValueError("Saved player condition flags must be booleans.")
    for field in ("charmed_by", "frightened_by", "grappled_by"):
        if field in player and (not isinstance(player[field], str) or not player[field].strip()):
            raise ValueError("Saved condition source identity is invalid.")
    if "prone" in player and type(player["prone"]) is not bool:
        raise ValueError("Saved prone flag must be boolean.")
    for field in ("grapple_escape_dc", "frightened_until_player_turn", "speed_penalty_ft", "speed_penalty_turns_remaining"):
        if field in player and (type(player[field]) is not int or player[field] < 0):
            raise ValueError("Saved condition numeric metadata is invalid.")

def _validate_player_weapon_proficiencies(player, version):
    """Optional explicit capability; absent state stays absent here (weapon_attack.proficiencies reads a class grant at attack time)."""
    if "weapon_proficiencies" not in player:
        return
    from weapon_catalog import WEAPONS
    values = player["weapon_proficiencies"]
    allowed = {"simple", "martial"} | {weapon["weapon_id"] for weapon in WEAPONS.values()}
    if (version not in (4, 5, 6) or type(values) is not list
            or any(type(value) is not str or value not in allowed for value in values)
            or len(values) != len(set(values))):
        raise ValueError("Saved weapon proficiencies are invalid.")

def _player_state_for_save():
    character = game._session().character
    import character_progression
    # Selected earned ASI requires format4/5/6; loaded formats are not promoted.
    character_progression._validate_asi_choice_storage(character, world=game._session().world_state)
    character_progression._validate_primal_knowledge(character)
    if "primal_knowledge_choice" in character and getattr(game._session(), "_persisted_engine_format", SAVE_FORMAT_VERSION) not in (4, 5, 6):
        raise ValueError("Primal Knowledge requires save format4–6.")
    if character.get("asi_choices") and getattr(game._session(), "_persisted_engine_format", SAVE_FORMAT_VERSION) not in (4, 5, 6):
        raise ValueError("Earned ASI requires save format4/5/6.")
    game._validate_player_weapon_proficiencies(character, getattr(game._session(), "_persisted_engine_format", SAVE_FORMAT_VERSION))
    saved = {
        "name": game._session().character["name"],
        "race": game._session().character["race"],
        "species": game._session().character.get(
            "species", game._session().character["race"]
        ),
        "giant_ancestry": game._session().character.get("giant_ancestry"),
        "species_trait_state": copy.deepcopy(
            game._session().character.get("species_trait_state")
        ),
        "speed_ft": game._session().character.get("speed_ft", 30),
        "exhaustion": weapon_attack.exhaustion(game._session().character),
        "proficient_tools": list(game._session().character.get("proficient_tools", [])),
        "saving_throw_mods": copy.deepcopy(game._session().character.get("saving_throw_mods", {})),
        "class": game._session().character["class"],
        "strength": game._session().character["strength"],
        "dexterity": game._session().character["dexterity"],
        "constitution": game._session().character["constitution"],
        "intelligence": game._session().character["intelligence"],
        "wisdom": game._session().character["wisdom"],
        "charisma": game._session().character["charisma"],
        "proficient_skills": list(game._session().character["proficient_skills"]),
        "expertise_skills": list(
            game._session().character.get("expertise_skills", [])
        ),
        "species_bonus_skills": list(
            game._session().character.get("species_bonus_skills", [])
        ),
        "level": game._session().character["level"],
        "proficiency_bonus": game._session().character["proficiency_bonus"],
        "max_hp": game._session().character["max_hp"],
        "current_hp": game._session().character["current_hp"],
        "armor_class": game._session().character["armor_class"],
        "xp": game._session().character.get("xp", 0) if type(game._session().character.get("xp", 0)) is int and game._session().character.get("xp", 0) >= 0 else 0,
    }
    if (
        character.get("species", character.get("race"))
        not in game.SPECIES_WITH_TRAIT_STATE
        and "temporary_hit_points" in character
    ):
        saved["temporary_hit_points"] = character["temporary_hit_points"]
    for field in ("origin", "appearance", "personality", "backstory"):
        if field not in character or character[field] is None:
            saved[field] = None
            continue
        value = character[field]
        if type(value) is not str:
            raise ValueError("Kayıt kimlik metni geçersiz.")
        saved[field] = value
    game._validate_player_condition_state(character)
    for field in _PERSISTED_PLAYER_CONDITION_FIELDS:
        if field in character:
            saved[field] = copy.deepcopy(character[field])
    choices = game._origin_choices_for_save(character)
    if choices:
        saved["origin_choices"] = choices
    if "progression_level" in character:  # C06: the level whose class-table choices were applied (XP may be ahead of it)
        saved["progression_level"] = character["progression_level"]
    if character.get("asi_choices"):
        saved["asi_choices"] = copy.deepcopy(character["asi_choices"])
    if "weapon_proficiencies" in character:
        saved["weapon_proficiencies"] = list(character["weapon_proficiencies"])
    if character.get("metamagic"):
        saved["metamagic"] = list(character["metamagic"])
    if "primal_knowledge_choice" in character:
        saved["primal_knowledge_choice"] = copy.deepcopy(character["primal_knowledge_choice"])
    if "subclass_id" in character:
        saved["subclass_id"] = copy.deepcopy(character["subclass_id"])
    if "hit_dice" in character:  # K07: spent Hit Point Dice and the open Short Rest window (additive, absent in older saves)
        saved["hit_dice"] = dict(character["hit_dice"])
    if "fighter_uses" in character:  # additive: spent Second Wind and Action Surge uses
        saved["fighter_uses"] = dict(character["fighter_uses"])
    for field in ("draconic_ancestry", "breath_weapon_spent"):  # additive (D-233): absent in older saves
        if character.get(field) is not None:
            saved[field] = character[field]
    if "paladin_uses" in character:  # additive: spent Paladin pools and timed effects
        saved["paladin_uses"] = copy.deepcopy(character["paladin_uses"])
    if "uncanny_dodge_off" in character:  # additive: the player turned Uncanny Dodge off
        saved["uncanny_dodge_off"] = character["uncanny_dodge_off"]
    if "monk_state" in character:  # additive: spent Focus Points, Uncanny Metabolism, Deflect Attacks setting
        saved["monk_state"] = dict(character["monk_state"])
    if "armor_origin" in character:  # additive: without it an older save cannot let Armor Class follow Dexterity
        saved["armor_origin"] = copy.deepcopy(character["armor_origin"])
    if character.get("fighting_style") is not None:  # additive: the style keeps applying after a load
        saved["fighting_style"] = character["fighting_style"]
    # Formats 4 and 5 store spell lists, slots, and an origin feat.
    # A loaded v1–v3 campaign keeps that version and does not gain these fields on save.
    if getattr(game._session(), "_persisted_engine_format", SAVE_FORMAT_VERSION) >= 4:
        import spells
        spell_fields = spells.empty_spell_state()
        for field in ("cantrips", "spells", "spell_slots_remaining"):
            if field in character:
                spell_fields[field] = copy.deepcopy(character[field])
        spells.validate_saved_spell_fields(spell_fields)
        saved.update(spell_fields)
        if "origin_feat" in character:
            feat = character["origin_feat"]
            if not isinstance(feat, str) or not feat.strip() or len(feat) > 40:
                raise ValueError("Origin feat state is invalid.")
            saved["origin_feat"] = feat
    game._validate_saved_multilevel_slots(saved, game._session().world_state)
    return saved

def serialize_game_state():
    """Return a JSON-safe, versioned snapshot of the complete game session."""
    recent_dm_narrations = game._session().recent_dm_narrations
    world_state = game._session().world_state
    living_world.ensure_scene_state(world_state)
    import barbarian_rage
    barbarian_rage.validate(world_state, game._session().character, getattr(game._session(), "_persisted_engine_format", SAVE_FORMAT_VERSION), strict_active=True)
    if "sorcery_points_v1" in world_state:
        import sorcery_points
        sorcery_points.validate(world_state["sorcery_points_v1"], game._session().character, getattr(game._session(), "_persisted_engine_format", SAVE_FORMAT_VERSION))
    return {
        "format": "ai-dnd-save",
        "version": getattr(game._session(), "_persisted_engine_format", SAVE_FORMAT_VERSION),
        "player": copy.deepcopy(game._player_state_for_save()),
        "world_state": copy.deepcopy(world_state),
        "recent_dm_narrations": list(recent_dm_narrations),
    }

def _validate_combat_v3_payload(combat):
    """Validate the persisted scheduler without normalizing or discarding it."""
    if not isinstance(combat, dict) or combat.get("schema_version") != 3:
        raise ValueError("Kayıt çatışma sürümü geçersiz.")
    if type(combat.get("active")) is not bool:
        raise ValueError("Kayıt çatışma durumu geçersiz.")
    combat_status = combat.get("status")
    if (
        (combat["active"] and combat_status not in ("active", "death_resolution"))
        or (not combat["active"] and combat_status != "ended")
    ):
        raise ValueError("Kayıt çatışma durumu geçersiz.")
    if "combat_id" in combat and combat["combat_id"] is not None and (
        not isinstance(combat["combat_id"], str) or not combat["combat_id"]
    ):
        raise ValueError("Kayıt çatışma kimliği geçersiz.")
    if combat["active"] and not combat.get("combat_id"):
        raise ValueError("Etkin çatışmanın kimliği eksik.")

    round_number = combat.get("round")
    order = combat.get("initiative_order")
    actor_index = combat.get("current_turn_index")
    actor_id = combat.get("current_actor_id")
    participants = combat.get("participants")
    records = combat.get("participant_records")
    actions_used = combat.get("actions_used")
    target_id = combat.get("target_id")
    if (
        type(round_number) is not int
        or not isinstance(order, list)
        or not isinstance(participants, list)
        or not isinstance(records, list)
        or type(actor_index) is not int
        or not isinstance(actions_used, list)
    ):
        raise ValueError("Kayıt çatışma sırası geçersiz.")
    if any(not isinstance(item, str) or not item for item in order + participants + actions_used):
        raise ValueError("Kayıt çatışma katılımcısı geçersiz.")
    if len(set(order)) != len(order) or len(set(participants)) != len(participants):
        raise ValueError("Kayıt çatışma katılımcısı yineleniyor.")
    if not set(actions_used).issubset(set(participants)):
        raise ValueError("Kayıt çatışma eylem kullanımı geçersiz.")
    if target_id is not None and (
        not isinstance(target_id, str) or target_id not in participants
    ):
        raise ValueError("Kayıt çatışma hedefi geçersiz.")

    if not combat["active"]:
        if (
            round_number != 0
            or order
            or participants
            or records
            or actor_index != 0
            or actor_id is not None
            or actions_used
            or target_id is not None
        ):
            raise ValueError("Pasif çatışma kaydı tutarsız.")
        if combat.get("end_reason") is not None and not isinstance(
            combat.get("end_reason"), str
        ):
            raise ValueError("Kayıt çatışma sonlandırma nedeni geçersiz.")
        return

    if (
        round_number < 1
        or len(order) < (1 if combat_status == "death_resolution" else 2)
        or "player" not in participants
        or set(order) != set(participants)
        or len(order) != len(participants)
        or type(actor_index) is not int
        or not 0 <= actor_index < len(order)
        or actor_id != order[actor_index]
        or (target_id is None and combat_status != "death_resolution")
        or len(records) != len(participants)
    ):
        raise ValueError("Kayıt etkin çatışma sırası tutarsız.")
    if combat.get("end_reason") is not None:
        raise ValueError("Etkin çatışmanın sonlandırma nedeni olamaz.")

    record_ids = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Kayıt çatışma katılımcı verisi geçersiz.")
        participant_id = record.get("id")
        kind = record.get("kind")
        name = record.get("name")
        initiative_count = record.get("initiative")
        current_hp = record.get("current_hp")
        max_hp = record.get("max_hp")
        armor_class = record.get("armor_class")
        participant_status = record.get("status")
        action_available = record.get("primary_action_available")
        if (
            not isinstance(participant_id, str)
            or participant_id not in participants
            or kind not in ("player", "npc")
            or (participant_id == "player") != (kind == "player")
            or not isinstance(name, str)
            or not name.strip()
            or (initiative_count is not None and type(initiative_count) is not int)
            or type(current_hp) is not int
            or type(max_hp) is not int
            or type(armor_class) is not int
            or current_hp < 0
            or max_hp < 1
            or current_hp > max_hp
            or armor_class < 0
            or participant_status not in ("active", "unconscious", "defeated", "dead", "inactive", "surrendered")
            or type(action_available) is not bool
            or action_available != (participant_id not in actions_used)
        ):
            raise ValueError("Kayıt çatışma katılımcı verisi geçersiz.")
        record_ids.append(participant_id)
    if len(set(record_ids)) != len(record_ids) or set(record_ids) != set(participants):
        raise ValueError("Kayıt çatışma katılımcı listesi tutarsız.")
    action_economy.validate_saved(combat)
    initiative.validate_saved(combat)

def _validate_long_rest_history(world):
    """Optional legacy-compatible completion time; campaign time is the only clock."""
    if "last_long_rest_completed_at" not in world:
        return None
    clock = world.get("campaign_time")
    if not isinstance(clock, dict):
        raise ValueError("Uzun dinlenme kaydı için oyun saati gerekli.")
    campaign_time.validate_clock(clock)
    completed = world["last_long_rest_completed_at"]
    if type(completed) is not int or not 0 <= completed <= clock["elapsed_seconds"]:
        raise ValueError("Uzun dinlenme tamamlanma zamanı geçersiz.")
    return completed

def _validate_saved_multilevel_slots(player, saved_world):
    """Expanded encoding is not entitlement; keep the legacy level-one mirror contract."""
    slots = player.get("spell_slots_remaining")
    if slots is None or (isinstance(slots, dict) and set(slots) == {"1"}):
        return
    import character_progression
    capacity = character_progression.slot_capacity(player)
    if (not isinstance(saved_world.get("spellcasting_v1"), dict) or capacity is None
            or not isinstance(slots, dict) or set(slots) != set(capacity)
            or any(type(count) is not int or not 0 <= count <= capacity[key]
                   for key, count in slots.items())):
        raise ValueError("Saved multi-level spell slots require supported applied-level capacity.")

def _validate_save_header(payload):
    """Format, version, and the player and world objects; returns (version, player, saved_world)."""
    if not isinstance(payload, dict):
        raise ValueError("Kayıt dosyası bir JSON nesnesi olmalı.")
    if payload.get("format") != "ai-dnd-save":
        raise ValueError("Bu dosya bir Unwritten kayıt dosyası değil.")
    version = payload.get("version")
    if version not in _SUPPORTED_SAVE_VERSIONS:
        raise ValueError("Bu kayıt sürümü desteklenmiyor.")

    player = payload.get("player")
    saved_world = payload.get("world_state")
    if not isinstance(player, dict) or not isinstance(saved_world, dict):
        raise ValueError("Kayıt oyuncu veya dünya verisini içermiyor.")
    return version, player, saved_world


def _validate_save_subsystems(player, saved_world, version):
    """The clock, rest history and the subsystems that own their own saved state."""
    if "campaign_time" in saved_world:
        campaign_time.validate_clock(saved_world["campaign_time"])
    game._validate_long_rest_history(saved_world)
    import barbarian_rage
    barbarian_rage.validate(saved_world, player, version, strict_active=True)
    if "sorcery_points_v1" in saved_world:
        import sorcery_points
        sorcery_points.validate(saved_world["sorcery_points_v1"], player, version)
    game._validate_player_condition_state(player)
    game._validate_player_weapon_proficiencies(player, version)
    if "concentration" in player:
        raise ValueError("Saved player concentration has no supported schema.")
    scheduled_events.validate_events(saved_world.get("scheduled_events", []), saved_world)
    timed_gameplay.validate_state(saved_world)
    weapon_attack.exhaustion(player)
    if (not isinstance(player.get("proficient_tools", []), list)
            or any(not isinstance(t, str) for t in player.get("proficient_tools", []))
            or not isinstance(player.get("saving_throw_mods", {}), dict)
            or any(k not in {"strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"}
                   or type(v) is not int for k, v in player.get("saving_throw_mods", {}).items())):
        raise ValueError("Kayıt araç veya kurtarma yeterliliği geçersiz.")
    import authored_dungeon
    authored_dungeon.validate_state(saved_world)
    import exploration
    exploration.validate_state(saved_world)
    local_exploration.validate_saved(saved_world)
    held_weapon.validate_saved(saved_world)
    monster_sense.validate_saved(saved_world)


_REQUIRED_PLAYER = {
    "name", "race", "class", "strength", "dexterity", "constitution",
    "intelligence", "wisdom", "charisma", "proficient_skills", "level",
    "proficiency_bonus", "max_hp", "current_hp", "armor_class",
}


def _validate_saved_player_fields(player):
    """Required player fields and the optional advancement fields."""
    if not _REQUIRED_PLAYER.issubset(player):
        raise ValueError("Kayıt oyuncu alanları eksik.")
    if "xp" in player and (type(player["xp"]) is not int or player["xp"] < 0):
        raise ValueError("Kayıt deneyim alanı geçersiz.")
    if "origin_choices" in player and not game._origin_choices_valid(player["origin_choices"]):
        raise ValueError("Kayıt köken seçimleri geçersiz.")
    if "progression_level" in player and (type(player["progression_level"]) is not int
                                          or not 1 <= player["progression_level"] <= player["level"]):
        raise ValueError("Kayıt seviye ilerlemesi geçersiz.")
    if "metamagic" in player and (not isinstance(player["metamagic"], list) or len(player["metamagic"]) > 20
                                  or any(not isinstance(m, str) or not 0 < len(m) <= 40 for m in player["metamagic"])
                                  or len(set(player["metamagic"])) != len(player["metamagic"])):
        raise ValueError("Kayıt metamagic seçimleri geçersiz.")
    import hit_dice
    hit_dice.validate_saved(player)


def _validate_saved_world_sections(player, saved_world, version):
    """Required world fields, receipts, and the versioned world sections."""
    required_world = {
        "location", "locations", "npcs", "inventory", "doors", "features",
        "events", "flags", "combat", "player_combat_status",
    }
    if not required_world.issubset(saved_world):
        raise ValueError("Kayıt dünya alanları eksik.")
    if not isinstance(saved_world["locations"], dict):
        raise ValueError("Kayıt konumları geçersiz.")
    if not isinstance(saved_world["npcs"], list):
        raise ValueError("Kayıt NPC listesi geçersiz.")
    if not isinstance(saved_world["inventory"], list):
        raise ValueError("Kayıt envanteri geçersiz.")
    # Every save version: a receipt list that is not a list of strings is refused, never repaired to [] (that would
    # pay every finished job still in history again). Version 5+ also checks each id in xp.validate_saved_advancement.
    receipts = saved_world.get("xp_awarded_event_ids", [])
    if not isinstance(receipts, list) or any(not isinstance(item, str) for item in receipts):
        raise ValueError("Kayıt deneyim olayları geçersiz.")
    if interaction_adventure.KEY in saved_world:
        interaction_adventure.validate(saved_world[interaction_adventure.KEY], saved_world)
    if "incidents" in saved_world or "emergence_state" in saved_world or "incident_threads" in saved_world:
        import incidents
        import incidents.state
        import incidents.threads
        incidents.load_incidents(saved_world)
        incidents.state.read(saved_world)
        if "incident_threads" in saved_world:
            incidents.threads.validate(saved_world["incident_threads"])
    if "relationships" in saved_world:
        import relationships
        relationships.validate(saved_world["relationships"])
    if "companions" in saved_world:
        import companions
        companions.validate(saved_world["companions"])
    if "adventure_arcs" in saved_world:
        import adventure.arcs as adventure_arcs
        adventure_arcs.validate(saved_world["adventure_arcs"])
    if "world_threads_v1" in saved_world:
        import world_threads
        # a happening row of unknown kind is not a reason to refuse: loading drops it (_repair_dilim2_fields)
        world_threads.validate(game._known_happenings(saved_world["world_threads_v1"])[0])
    if version >= 2 and (
        "quests" not in saved_world or "quest_processed_event_ids" not in saved_world
    ):
        raise ValueError("Kayıt görev alanlarını içermiyor.")
    if version >= 3:
        game._validate_combat_v3_payload(saved_world.get("combat"))
    if version >= 4:
        import spells
        spells.validate_saved_spell_fields(player)
    if version >= 5:
        import xp
        xp.validate_saved_advancement(player, saved_world, policy=6 if version >= 6 else 5)


def _validate_saved_character(player, saved_world, version):
    """Skills, class and species rules, spells, hit points and stats of the saved character."""
    if not isinstance(player["proficient_skills"], list):
        raise ValueError("Kayıt yetenek listesi geçersiz.")
    species_bonus_skills = player.get("species_bonus_skills", [])
    if (
        not isinstance(species_bonus_skills, list)
        or any(
            not isinstance(skill, str)
            or skill not in game.SKILLS
            or skill not in player["proficient_skills"]
            for skill in species_bonus_skills
        )
        or len(species_bonus_skills) != len(set(species_bonus_skills))
    ):
        raise ValueError("Kayıt tür becerileri geçersiz.")
    for field in _REQUIRED_PLAYER - {"name", "race", "class", "proficient_skills"}:
        if type(player[field]) is not int:
            raise ValueError(f"Kayıt sayısal alanı geçersiz: {field}")
    if not isinstance(player["name"], str) or not player["name"].strip():
        raise ValueError("Karakter adı geçersiz.")
    if player["race"] not in game.RACES or player["class"] not in game.CLASSES:
        raise ValueError("Karakter ırkı veya sınıfı geçersiz.")
    import spell_scope
    spell_scope.validate(saved_world.get("spellcasting_v1"), player)
    import character_progression
    if player.get("asi_choices") and version not in (4, 5, 6):
        raise ValueError("Earned ASI requires save format4/5/6.")
    if "primal_knowledge_choice" in player and version not in (4, 5, 6):
        raise ValueError("Primal Knowledge requires save format4–6.")
    character_progression.validate_saved(player, saved_world, saved=True)
    weapon_attack.validate_saved_reckless(saved_world, player)
    import monk_features
    monk_features.validate_saved_effects(saved_world, player)
    import spell_concentration
    spell_concentration.validate_saved(saved_world, player)
    import spell_scope
    spell_scope.validate_saved_riders(saved_world)
    import spell_effects
    spell_effects.validate_saved(saved_world)
    game._validate_saved_multilevel_slots(player, saved_world)
    species = player.get("species", player["race"])
    if species not in game.RACES:
        raise ValueError("Karakter türü geçersiz.")
    if "temporary_hit_points" in player and (
        type(player["temporary_hit_points"]) is not int
        or player["temporary_hit_points"] < 0
    ):
        raise ValueError("Kayıt geçici can puanı geçersiz.")
    import dragonborn_breath
    dragonborn_breath.validate_saved({**player, "species": species})
    giant_ancestry = player.get("giant_ancestry")
    if giant_ancestry is not None and (
        species != "Goliath" or giant_ancestry not in game.GIANT_ANCESTRY_IDS
    ):
        raise ValueError("Kayıt dev atası seçimi geçersiz.")
    if "species_trait_state" in player and player["species_trait_state"] is not None:
        game._validate_species_trait_state(
            player["species_trait_state"],
            species,
            player.get("proficiency_bonus", 2),
        )
    if "speed_ft" in player and (
        type(player["speed_ft"]) is not int or player["speed_ft"] < 0
    ):
        raise ValueError("Kayıt hareket hızı geçersiz.")
    if any(not isinstance(skill, str) or skill not in game.SKILLS
           for skill in player["proficient_skills"]):
        raise ValueError("Karakter yetenekleri geçersiz.")
    expertise_skills = player.get("expertise_skills", [])
    if (
        not isinstance(expertise_skills, list)
        or any(
            not isinstance(skill, str)
            or skill not in game.SKILLS
            or skill not in player["proficient_skills"]
            for skill in expertise_skills
        )
        or len(expertise_skills) != len(set(expertise_skills))
    ):
        raise ValueError("Karakter uzmanlık becerileri geçersiz.")
    if expertise_skills and len(expertise_skills) != get_expertise_choice_count(
        player["class"], player["level"]
    ):
        raise ValueError("Karakter uzmanlık seçimi sınıf veya seviye ile uyuşmuyor.")
    if not 0 <= player["current_hp"] <= player["max_hp"] or player["max_hp"] < 0 or (
        player["max_hp"] == 0 and not saved_world.get("death_state", {}).get("dead")
    ):
        raise ValueError("Karakter HP değerleri geçersiz.")
    if player["level"] < 1 or player["proficiency_bonus"] < 0 or player["armor_class"] < 0:
        raise ValueError("Karakter mekanik değerleri geçersiz.")
    for stat in game.SKILLS.values():
        if not 1 <= player[stat] <= 30:
            raise ValueError("Karakter stat değeri geçersiz.")


def _validate_saved_world_fields(saved_world):
    """Saved world fields keep the type of their initial value; the scene state still builds."""
    for key, default in game.INITIAL_WORLD_STATE.items():
        if key not in saved_world:
            continue
        if key == "campaign_id":
            campaign_id = saved_world[key]
            if campaign_id is not None and (
                not isinstance(campaign_id, str)
                or not campaign_id.strip()
                or len(campaign_id) > 120
            ):
                raise ValueError("Dünya kampanya kimliği geçersiz.")
            continue
        if type(saved_world[key]) is not type(default):
            raise ValueError(f"Dünya alanı geçersiz: {key}")
    if "scene_state" in saved_world:
        try:
            living_world.ensure_scene_state(copy.deepcopy(saved_world))
        except (TypeError, ValueError):
            raise ValueError("Kayıt sahne verisi geçersiz.") from None


def _validate_saved_quests(saved_world):
    """Quest rows (dynamic rows by adventure, legacy rows here) and processed quest event ids."""
    quests = saved_world.get("quests", [])
    processed = saved_world.get("quest_processed_event_ids", [])
    if not isinstance(quests, list) or not isinstance(processed, list):
        raise ValueError("Görev durumu geçersiz.")
    if any(not isinstance(item, str) or not re.match(
        r"^(location|defeat|item):[0-9]+:.+$", item
    ) for item in processed):
        raise ValueError("Görev olay kimliği geçersiz.")
    if len(processed) != len(set(processed)):
        raise ValueError("Görev olay kimliği yineleniyor.")
    quest_ids = set()
    for quest in quests:
        if isinstance(quest, dict) and set(quest) != adventure.LEGACY_QUEST_FIELDS:
            adventure.validate_dynamic_saved_quest(quest, quest_ids)
            continue
        quest_fields = {
            "quest_id", "title", "description", "giver_npc_id", "status",
            "objectives", "created_turn", "accepted_turn", "updated_turn",
        }
        if (
            not isinstance(quest, dict)
            or set(quest) != quest_fields
            or not isinstance(quest.get("quest_id"), str)
            or not quest["quest_id"].strip()
            or len(quest["quest_id"]) > 120
            or quest["quest_id"] in quest_ids
            or not isinstance(quest.get("title"), str)
            or not quest["title"].strip()
            or len(quest["title"]) > 160
            or not isinstance(quest.get("description"), str)
            or not quest["description"].strip()
            or len(quest["description"]) > 2000
            or (
                quest.get("giver_npc_id") is not None
                and (
                    not isinstance(quest["giver_npc_id"], str)
                    or not quest["giver_npc_id"].strip()
                    or len(quest["giver_npc_id"]) > 120
                )
            )
            or not isinstance(quest.get("status"), str)
            or quest.get("status") not in {"accepted", "completed", "cancelled"}
        ):
            raise ValueError("Kayıt görev durumu geçersiz.")
        quest_ids.add(quest["quest_id"])
        for turn_field in ("created_turn", "updated_turn"):
            if type(quest.get(turn_field)) is not int or quest[turn_field] < 0:
                raise ValueError("Kayıt görev turu geçersiz.")
        accepted_turn = quest.get("accepted_turn")
        if accepted_turn is not None and (
            type(accepted_turn) is not int or accepted_turn < quest["created_turn"]
        ):
            raise ValueError("Kayıt görev kabul turu geçersiz.")
        if (
            quest["updated_turn"] < quest["created_turn"]
            or (
                quest["status"] in {"accepted", "completed"}
                and accepted_turn is None
            )
        ):
            raise ValueError("Kayıt görev zamanlaması tutarsız.")
        if not isinstance(quest.get("objectives"), list):
            raise ValueError("Kayıt görev hedefleri geçersiz.")
        if not quest["objectives"]:
            raise ValueError("Kayıt görevinin hedefi yok.")
        objective_ids = set()
        for objective in quest["objectives"]:
            objective_fields = {
                "objective_id", "description", "type", "target", "status",
                "required_count", "progress",
            }
            if (
                not isinstance(objective, dict)
                or set(objective) != objective_fields
                or not isinstance(objective.get("objective_id"), str)
                or not objective["objective_id"].strip()
                or len(objective["objective_id"]) > 120
                or objective["objective_id"] in objective_ids
                or not isinstance(objective.get("description"), str)
                or not objective["description"].strip()
                or len(objective["description"]) > 1000
                or not isinstance(objective.get("target"), str)
                or not objective["target"].strip()
                or len(objective["target"]) > 160
            ):
                raise ValueError("Kayıt görev hedefi geçersiz.")
            objective_ids.add(objective["objective_id"])
            if (
                not isinstance(objective["type"], str)
                or objective["type"]
                not in {"visit_location", "defeat_entity", "acquire_item"}
            ):
                raise ValueError("Kayıt görev hedef türü geçersiz.")
            if objective["type"] == "acquire_item" and objective["target"] != "Kılıç":
                raise ValueError("Kayıt eşya hedefi desteklenmiyor.")
            if (
                not isinstance(objective["status"], str)
                or objective["status"] not in {"active", "completed", "cancelled"}
            ):
                raise ValueError("Kayıt görev hedef durumu geçersiz.")
            if (
                type(objective["required_count"]) is not int
                or not 1 <= objective["required_count"] <= 1000
            ):
                raise ValueError("Kayıt görev hedef sayısı geçersiz.")
            if type(objective["progress"]) is not int or not 0 <= objective["progress"] <= objective["required_count"]:
                raise ValueError("Kayıt görev ilerlemesi geçersiz.")
            if (
                objective["status"] == "active"
                and objective["progress"] >= objective["required_count"]
            ) or (
                objective["status"] == "completed"
                and objective["progress"] != objective["required_count"]
            ):
                raise ValueError("Kayıt görev hedef ilerlemesi tutarsız.")
        statuses = {item["status"] for item in quest["objectives"]}
        if (
            quest["status"] == "completed" and statuses != {"completed"}
        ) or (
            quest["status"] == "accepted"
            and (statuses == {"completed"} or "cancelled" in statuses)
        ) or (
            quest["status"] == "cancelled"
            and ("active" in statuses or statuses == {"completed"})
        ):
            raise ValueError("Kayıt görev durumu hedeflerle tutarsız.")


def _validate_saved_world_lists(payload, saved_world):
    """Equipment, world lists and objects, and the narration history."""
    equipment_economy.validate_world(saved_world)
    for key in ("player_knowledge",):
        if any(not isinstance(item, str) for item in saved_world.get(key, [])):
            raise ValueError(f"Dünya listesi geçersiz: {key}")
    for items in saved_world.get("ground_items_by_location", {}).values():
        if not isinstance(items, list) or any(not isinstance(item, (str, dict)) for item in items):
            raise ValueError("Yerdeki eşya listesi geçersiz.")
    for key in ("npcs", "doors", "containers"):
        if any(not isinstance(item, dict) for item in saved_world.get(key, [])):
            raise ValueError(f"Dünya nesneleri geçersiz: {key}")
    if any(not isinstance(item, dict) for item in saved_world["locations"].values()):
        raise ValueError("Konum kayıtları geçersiz.")
    narrations = payload.get("recent_dm_narrations", [])
    if not isinstance(narrations, list) or any(not isinstance(item, str) for item in narrations):
        raise ValueError("Anlatı geçmişi geçersiz.")


def _validate_save_payload(payload):
    """Refuse a save any section finds invalid; the sections run in this fixed order (first error wins)."""
    version, player, saved_world = game._validate_save_header(payload)
    game._validate_save_subsystems(player, saved_world, version)
    game._validate_saved_player_fields(player)
    game._validate_saved_world_sections(player, saved_world, version)
    game._validate_saved_character(player, saved_world, version)
    game._validate_saved_world_fields(saved_world)
    game._validate_saved_quests(saved_world)
    game._validate_saved_world_lists(payload, saved_world)

def save_game(path):
    """Atomically save a validated JSON snapshot to *path*."""
    destination = Path(path).expanduser()
    payload = game.serialize_game_state()
    game._validate_save_payload(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            game.os.fsync(handle.fileno())
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def _repair_dilim1_fields(world: dict) -> list[str]:
    """Repair optional slice-one rows through their owners; never change payment operations."""
    import logging
    import npc_told
    import economic_actions
    import bold_acts
    dropped = npc_told.repair(world)
    dropped += economic_actions.repair_declines(world)
    dropped += economic_actions.repair_ledger_labels(world)
    dropped += bold_acts.repair_counter_tip(world)
    for name in dropped:
        logging.getLogger("game").warning("dilim1 load repaired: %s", name)
    return dropped

def _known_happenings(state):
    """The thread state with its ledger rows of unknown kind left out (a copy when any is), and those rows."""
    import world_happenings
    rows = state.get(world_happenings.KEY) if isinstance(state, dict) else None
    if not isinstance(rows, list):
        return state, []
    unknown = [row for row in rows if not isinstance(row, dict) or row.get("kind") not in world_happenings.KINDS]
    if not unknown:
        return state, []
    return {**state, world_happenings.KEY: [row for row in rows if row not in unknown]}, unknown

def _repair_dilim2_fields(world: dict) -> list[str]:
    """Repair slice-two fields a save can carry broken; never refuse the save. A sound save is left as it is.

    A happening row of unknown kind is dropped, a hand that names nothing (not in the bag, not a catalog weapon) is
    emptied and a talk with
    someone dead, elsewhere or not in the save is closed. Each repair is named and logged."""
    import logging
    import world_happenings
    import world_threads
    fixed = []
    if not isinstance(world, dict):
        return fixed
    state = world.get(world_threads.KEY)
    kept, unknown = game._known_happenings(state)
    if unknown:
        state[world_happenings.KEY] = kept[world_happenings.KEY]
        fixed += [f"happening:{row.get('kind') if isinstance(row, dict) else None}" for row in unknown]
    hands, inventory = world.get("equipment"), world.get("inventory")
    if isinstance(hands, dict) and isinstance(inventory, list):
        for hand in ("main_hand", "off_hand"):
            held = hands.get(hand)
            if isinstance(held, str) and not game._hand_names_something(inventory, held):
                hands[hand] = None
                fixed.append(f"equipment:{hand}")
    flags = world.get("flags")
    active = flags.get("active_npc_id") if isinstance(flags, dict) else None
    if isinstance(active, str) and active:
        npcs = world.get("npcs") if isinstance(world.get("npcs"), list) else []
        person = next((n for n in npcs if isinstance(n, dict) and n.get("id") == active), None)
        if person is None:
            talk_mode.close(world, "repair")
            fixed.append("talk:nobody")
        elif person.get("combat_status") == "dead" or person.get("location") != world.get("location"):
            talk_mode.close(world, "repair")
            fixed.append(f"talk:{active}")
    for name in fixed:
        logging.getLogger("game").warning("dilim2 load repaired: %s", name)
    return fixed

def load_game(path):
    """Validate and restore a JSON snapshot without executing arbitrary code."""
    previous_format = getattr(game._session(), "_persisted_engine_format", SAVE_FORMAT_VERSION)
    recent_dm_narrations = game._session().recent_dm_narrations
    world_state = game._session().world_state
    source = Path(path).expanduser()
    payload = json.loads(source.read_text(encoding="utf-8"))
    game._validate_save_payload(payload)

    player = payload["player"]
    saved_world = copy.deepcopy(payload["world_state"])
    saved_world.setdefault("ground_items_by_location", {})
    saved_world.setdefault("ground_items", [])
    saved_world.setdefault("containers", [])
    saved_world.setdefault("shops", [])
    saved_world.setdefault("next_shop_number", 1)
    saved_world.setdefault("player_knowledge", [])
    saved_world.setdefault("quests", [])
    saved_world.setdefault("quest_processed_event_ids", [])
    saved_world.setdefault("scene_state", living_world.initial_scene_state())
    saved_world.setdefault("campaign_id", None)
    saved_world.setdefault("death_state", game._death_state_defaults())

    character = game._session().character
    previous_world = copy.deepcopy(world_state)
    previous_character = copy.deepcopy(character)
    previous_narrations = list(recent_dm_narrations)
    try:
        world_state.clear()
        world_state.update(saved_world)
        game._repair_dilim1_fields(world_state)
        game._repair_dilim2_fields(world_state)
        living_world.ensure_scene_state(world_state)
        equipment_economy.give_old_save_gear(world_state)  # D-231 (+ D-207 purses): after the scene state, so the seed is read
        for field in ("name", "race", "class"):
            character[field] = str(player[field])
        character["species"] = str(player.get("species", player["race"]))
        character["exhaustion"] = player.get("exhaustion", 0)
        for field in (*_PERSISTED_PLAYER_CONDITION_FIELDS, "concentration"):
            character.pop(field, None)
            if field in player:
                character[field] = copy.deepcopy(player[field])
        character.pop("weapon_proficiencies", None)
        if "weapon_proficiencies" in player:
            character["weapon_proficiencies"] = list(player["weapon_proficiencies"])
        character["proficient_tools"] = list(player.get("proficient_tools", []))
        character["saving_throw_mods"] = copy.deepcopy(player.get("saving_throw_mods", {}))
        character["giant_ancestry"] = player.get("giant_ancestry")
        character["speed_ft"] = int(
            player.get(
                "speed_ft",
                35 if character["species"] == "Goliath" else 30,
            )
        )
        for field in ("strength", "dexterity", "constitution", "intelligence",
                      "wisdom", "charisma", "level", "proficiency_bonus",
                      "max_hp", "current_hp", "armor_class"):
            character[field] = int(player[field])
        if "xp" in player:
            character["xp"] = player["xp"]
        else:
            # No stored total exists to keep. Do not reuse XP left on this session.
            character["xp"] = 0
        if payload["version"] >= 4:
            character["cantrips"] = list(player["cantrips"])
            character["spells"] = list(player["spells"])
            character["spell_slots_remaining"] = copy.deepcopy(player["spell_slots_remaining"])
        else:
            character["cantrips"] = []
            character["spells"] = []
            character["spell_slots_remaining"] = {"1": 0}
        if isinstance(player.get("origin_feat"), str) and player["origin_feat"].strip():
            character["origin_feat"] = player["origin_feat"]
        else:
            character.pop("origin_feat", None)
        character["proficient_skills"] = list(player["proficient_skills"])
        character["expertise_skills"] = list(
            player.get("expertise_skills", [])
        )
        character["species_bonus_skills"] = list(
            player.get("species_bonus_skills", [])
        )
        for stale in (game._ORIGIN_TEXT_KEYS + game._ORIGIN_LIST_KEYS + game._ORIGIN_SCORE_KEYS
                      + ("final_ability_scores", "equipment_package", "equipment_choices", "fighting_style", "armor_origin")):
            character.pop(stale, None)  # choices and derived creation state of a previous character never leak into the loaded one
        character.update(copy.deepcopy(player.get("origin_choices") or {}))
        character.pop("asi_choices", None)
        # These player creation hints are not serialized authorities. Never
        # inherit them from a previously loaded character after an ASI.
        for cache in ("spell_save_dc", "spell_attack_bonus", "passive_perception"):
            character.pop(cache, None)
        if player.get("asi_choices"):
            character["asi_choices"] = copy.deepcopy(player["asi_choices"])
            character["final_ability_scores"] = {a: player[a] for a in
                ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")}
        character.pop("progression_level", None)
        character.pop("metamagic", None)
        character.pop("subclass_id", None)
        character.pop("primal_knowledge_choice", None)
        if "primal_knowledge_choice" in player:
            character["primal_knowledge_choice"] = copy.deepcopy(player["primal_knowledge_choice"])
        if "subclass_id" in player:
            character["subclass_id"] = player["subclass_id"]
        character.pop("hit_dice", None)
        if "hit_dice" in player:
            character["hit_dice"] = dict(player["hit_dice"])
        character.pop("fighter_uses", None)
        if "fighter_uses" in player:
            character["fighter_uses"] = dict(player["fighter_uses"])
        for field in ("draconic_ancestry", "breath_weapon_spent"):  # D-233: an older save chose and spent nothing
            character.pop(field, None)
            if field in player:
                character[field] = player[field]
        character.pop("paladin_uses", None)
        if "paladin_uses" in player:
            character["paladin_uses"] = copy.deepcopy(player["paladin_uses"])
        character.pop("uncanny_dodge_off", None)
        if "uncanny_dodge_off" in player:
            character["uncanny_dodge_off"] = player["uncanny_dodge_off"]
        character.pop("monk_state", None)
        if "monk_state" in player:
            character["monk_state"] = dict(player["monk_state"])
        if "fighting_style" in player:
            character["fighting_style"] = player["fighting_style"]
        import character_progression
        armor_origin = (copy.deepcopy(player["armor_origin"]) if "armor_origin" in player
                        else character_progression.repaired_armor_origin(player, saved_world))
        if armor_origin is not None:
            character["armor_origin"] = armor_origin
        if "progression_level" in player:
            character["progression_level"] = player["progression_level"]
        if player.get("metamagic"):
            character["metamagic"] = list(player["metamagic"])
        for field in ("origin", "appearance", "personality", "backstory"):
            if field not in player or player[field] is None:
                character[field] = None
                continue
            value = player[field]
            if type(value) is not str:
                raise ValueError("Kayıt kimlik metni geçersiz.")
            character[field] = value
        saved_trait_state = player.get("species_trait_state")
        if saved_trait_state is None:
            game.initialize_species_trait_state(
                giant_ancestry=character["giant_ancestry"]
            )
        else:
            character["species_trait_state"] = copy.deepcopy(saved_trait_state)
        character.pop("temporary_hit_points", None)
        if character["species"] not in game.SPECIES_WITH_TRAIT_STATE:
            if "temporary_hit_points" in player:
                character["temporary_hit_points"] = player["temporary_hit_points"]
            elif (isinstance(saved_trait_state, dict)
                  and "temporary_hit_points" in saved_trait_state):
                character["temporary_hit_points"] = saved_trait_state["temporary_hit_points"]
        character["modifiers"] = {
            ability: game.get_modifier(character[ability])
            for ability in ("strength", "dexterity", "constitution",
                            "intelligence", "wisdom", "charisma")
        }
        for ability, modifier in character["modifiers"].items():
            character[f"{ability}_mod"] = modifier
        recent_dm_narrations.clear()
        recent_dm_narrations.extend(payload.get("recent_dm_narrations", []))
        game._normalize_ground_items()
        game.ensure_combat_state()
        import spell_scope
        spell_scope.upgrade(world_state, character)  # 4C.2: spell state version 1 -> 2; chooses no spell
        # Keep the file's own version. The current default is v4, and a v1–v3
        # file must still be written back as that same version.
        game._session()._persisted_engine_format = payload["version"]
        loaded = game.serialize_game_state()
        # D-072: the sitting-only fight questions (never saved) belong to the replaced game, not the loaded one.
        game._session()._attack_asked, game._session()._blow_asked, game._session()._blow_asked_line = False, None, None
        game._session()._surrender_strike_asked = None
        game._session()._heavy_asked = game._session()._heavy_confirmed = None  # D-109: so do the crime/threat question and its yes
        return loaded
    except Exception:
        game._session()._persisted_engine_format = previous_format
        world_state.clear()
        world_state.update(previous_world)
        character.clear()
        character.update(previous_character)
        recent_dm_narrations.clear()
        recent_dm_narrations.extend(previous_narrations)
        raise
