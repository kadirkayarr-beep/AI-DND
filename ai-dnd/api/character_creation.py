"""HTTP-facing character setup composed from the frozen game engine and D&D 2024 rules."""

from __future__ import annotations

from typing import Any

import game
import spells as spell_rules
from api.dnd_2024_rules import (
    ABILITY_KEYS,
    BACKGROUND_DEFINITIONS,
    CLASS_DEFINITIONS,
    ORIGIN_FEATS,
    ALIGNMENTS,
    STANDARD_LANGUAGES,
    RARE_LANGUAGES,
    SKILL_DEFINITIONS,
    SPECIES_DEFINITIONS,
    SPELLS_CATALOG,
    STANDARD_ARRAY,
    CharacterCreationError,
    calculate_derived_stats,
    generate_random_2024_character,
    roll_4d6_drop_lowest,
    validate_ability_scores,
    validate_background_bonuses,
)


def _detect_armor_and_shield(equipment_choices: list[str] | None) -> tuple[str | None, bool]:
    if not equipment_choices:
        return None, False
    joined = " ".join(equipment_choices)
    armor = None
    if "Zincir Zırh" in joined or "Chain Mail" in joined:
        armor = "Chain Mail"
    elif "Pul Zırh" in joined or "Scale Mail" in joined:
        armor = "Scale Mail"
    elif "Deri Zırh" in joined or "Leather Armor" in joined:
        armor = "Leather Armor"
    has_shield = "Kalkan" in joined or "Shield" in joined
    return armor, has_shield


def configure_character(
    session: Any,
    *,
    mode: str,
    name: str | None = None,
    race: str | None = None,
    species: str | None = None,
    character_class: str | None = None,
    background: str | None = None,
    alignment: str | None = None,
    ability_score_method: str | None = None,
    ability_scores: dict[str, int] | None = None,
    background_ability_bonuses: dict[str, int] | None = None,
    proficient_skills: list[str] | None = None,
    proficient_tools: list[str] | None = None,
    origin_feat: str | None = None,
    fighting_style: str | None = None,
    equipment_package: str | None = None,
    equipment_choices: list[str] | None = None,
    background_equipment_option: str | None = None,
    languages: list[str] | None = None,
    cantrips: list[str] | None = None,
    spells: list[str] | None = None,
    appearance: str | None = None,
    personality: str | None = None,
    backstory: str | None = None,
    **extra: Any,
) -> None:
    """Populate the engine's canonical character record following D&D 2024 rules."""
    if mode not in {"custom", "random"}:
        raise CharacterCreationError("Choose custom or random character creation.")

    custom_inputs = (
        name,
        race,
        species,
        character_class,
        background,
        alignment,
        ability_score_method,
        ability_scores,
        background_ability_bonuses,
        proficient_skills,
        proficient_tools,
        origin_feat,
        fighting_style,
        equipment_package,
        equipment_choices,
        background_equipment_option,
        languages,
        cantrips,
        spells,
        appearance,
        personality,
        backstory,
    )

    if mode == "random":
        if any(value is not None for value in custom_inputs):
            raise CharacterCreationError(
                "Random character creation does not accept custom character fields."
            )
        name = session.rng.choice(game.RANDOM_NAMES)
        race = session.rng.choice(game.RACES)
        character_class = session.rng.choice(game.CLASSES)
        species = race

        default_bg_map = {
            "Fighter": "Soldier",
            "Barbarian": "Farmer",
            "Paladin": "Noble",
            "Rogue": "Wayfarer",
            "Ranger": "Guide",
            "Monk": "Hermit",
            "Cleric": "Acolyte",
            "Druid": "Guide",
            "Bard": "Entertainer",
            "Wizard": "Sage",
            "Sorcerer": "Charlatan",
            "Warlock": "Charlatan",
        }
        background = default_bg_map.get(character_class, "Soldier")
        bg_def = BACKGROUND_DEFINITIONS[background]
        alignment = "Neutral Good"
        ability_score_method = "rolled"

        cls_def = CLASS_DEFINITIONS[character_class]
        primary = cls_def["primary_ability"]
        rolled_pool = [roll_4d6_drop_lowest(session.rng) for _ in range(6)]
        rolled_pool.sort(reverse=True)
        assigned_scores = {primary: rolled_pool[0]}
        rem = [a for a in ABILITY_KEYS if a != primary]
        session.rng.shuffle(rem)
        for a, s in zip(rem, rolled_pool[1:]):
            assigned_scores[a] = s
        base_ability_scores = assigned_scores

        bg_abilities = list(bg_def["abilities"])
        plus_two = primary if primary in bg_abilities else bg_abilities[0]
        plus_one = next(a for a in bg_abilities if a != plus_two)
        background_ability_bonuses = {plus_two: 2, plus_one: 1}
        final_ability_scores = {
            k: base_ability_scores[k] + background_ability_bonuses.get(k, 0)
            for k in ABILITY_KEYS
        }

        skill_options = game.CLASS_SKILL_OPTIONS.get(character_class, cls_def["skill_options"])
        skill_count = 4 if character_class == "Rogue" else 2
        proficient_skills = session.rng.sample(skill_options, skill_count)
        proficient_tools = [bg_def["tool"]]
        origin_feat = bg_def["feat"]
        fighting_style = (
            cls_def["fighting_styles"][0]["id"]
            if character_class == "Fighter" and cls_def.get("fighting_styles")
            else None
        )
        equipment_package = cls_def["equipment_packages"][0]["id"] if cls_def.get("equipment_packages") else None
        bg_eq_opt = "A"
        class_items = list(cls_def["equipment_packages"][0]["items"]) if cls_def.get("equipment_packages") else []
        bg_items = list(bg_def["equipment"])
        combined_items = []
        for item in class_items + bg_items:
            if item not in combined_items or item.endswith("Altın") or item.endswith("GP"):
                combined_items.append(item)
        equipment_choices = combined_items

        avail_langs = [l for l in STANDARD_LANGUAGES if l != "Common"]
        random_langs = ["Common"] + sorted(session.rng.sample(avail_langs, 2))
        if character_class == "Druid" and "Druidic" not in random_langs:
            random_langs.append("Druidic")
        if character_class == "Rogue" and "Thieves' Cant" not in random_langs:
            random_langs.append("Thieves' Cant")
        languages = random_langs

        cantrips = []
        spells = []
        if cls_def.get("is_spellcaster"):
            sp_cat = SPELLS_CATALOG.get(character_class, {})
            c_avail = [c["id"] for c in sp_cat.get("cantrips", [])]
            s_avail = [s["id"] for s in sp_cat.get("spells_level_1", [])]
            cantrips = c_avail[: cls_def.get("cantrips_count", 0)]
            spells = s_avail[: cls_def.get("spells_count", 0)]

        appearance = None
        personality = None
        backstory = None

        armor, has_shield = _detect_armor_and_shield(equipment_choices)
        derived = calculate_derived_stats(
            character_class=character_class,
            species=species,
            final_scores=final_ability_scores,
            chosen_feat=origin_feat,
            fighting_style=fighting_style,
            equipped_armor=armor,
            has_shield=has_shield,
        )

    else:
        # CUSTOM MODE: FAIL-CLOSED (NO SILENT ENGINE DEFAULTS)
        name = name.strip() if isinstance(name, str) else ""
        if not name or len(name) > 40:
            raise CharacterCreationError("Character name must be 1–40 characters.")

        chosen_species = species or race
        if not chosen_species:
            raise CharacterCreationError("Species must be chosen.")
        if chosen_species not in SPECIES_DEFINITIONS and chosen_species not in game.RACES:
            raise CharacterCreationError("Choose a race or species supported by the rules.")
        species = chosen_species
        race = chosen_species

        if not character_class:
            raise CharacterCreationError("Class must be chosen.")
        if character_class not in CLASS_DEFINITIONS and character_class not in game.CLASSES:
            raise CharacterCreationError("Choose a class supported by the rules.")
        cls_def = CLASS_DEFINITIONS.get(character_class)
        if not cls_def:
            raise CharacterCreationError(f"Unsupported class: {character_class}")

        if not background:
            raise CharacterCreationError("Background must be chosen.")
        if background not in BACKGROUND_DEFINITIONS:
            raise CharacterCreationError("Choose a valid background from the rules.")
        bg_def = BACKGROUND_DEFINITIONS[background]

        if not alignment:
            raise CharacterCreationError("Alignment must be explicitly selected.")
        if alignment not in [a["id"] for a in ALIGNMENTS]:
            raise CharacterCreationError(f"Choose a valid alignment from the rules (received '{alignment}').")

        if languages is None:
            raise CharacterCreationError("Languages must be explicitly chosen (exactly 2 standard languages besides Common).")
        if not isinstance(languages, list):
            raise CharacterCreationError("Languages must be provided as a list.")
        if len(languages) != len(set(languages)):
            raise CharacterCreationError("Languages cannot contain duplicates.")
        for lang in languages:
            if not isinstance(lang, str) or not lang.strip():
                raise CharacterCreationError("Invalid language name.")

        chosen_langs = [l for l in languages if l != "Common"]
        allowed_rare = set()
        if character_class == "Druid":
            allowed_rare.add("Druidic")
        if character_class == "Rogue":
            allowed_rare.add("Thieves' Cant")

        for lang in chosen_langs:
            if lang not in STANDARD_LANGUAGES and lang not in allowed_rare:
                raise CharacterCreationError(
                    f"Language '{lang}' is not an available standard language or granted rare language."
                )
        if len(chosen_langs) != 2:
            raise CharacterCreationError(
                f"Character creation requires exactly 2 player-selected standard languages besides Common (chose {len(chosen_langs)})."
            )
        final_languages = ["Common"] + sorted(chosen_langs)
        if character_class == "Druid" and "Druidic" not in final_languages:
            final_languages.append("Druidic")
        if character_class == "Rogue" and "Thieves' Cant" not in final_languages:
            final_languages.append("Thieves' Cant")
        languages = final_languages

        if not ability_score_method:
            raise CharacterCreationError("Ability score generation method must be chosen.")
        if ability_score_method == "rolled":
            raise CharacterCreationError(
                "Rolled ability scores require game engine authority in random character mode; client-rolled scores cannot be submitted in custom mode."
            )
        if ability_score_method not in ("standard_array", "point_buy", "manual"):
            raise CharacterCreationError(f"Unsupported ability score method: {ability_score_method}")
        method = ability_score_method

        if not ability_scores or not isinstance(ability_scores, dict):
            raise CharacterCreationError("Ability scores must be specified.")
        validate_ability_scores(method, ability_scores)
        base_ability_scores = dict(ability_scores)

        if not background_ability_bonuses or not isinstance(background_ability_bonuses, dict):
            raise CharacterCreationError("Background ability score bonuses must be explicitly selected.")
        validate_background_bonuses(background, background_ability_bonuses, base_ability_scores)
        final_ability_scores = {
            k: base_ability_scores[k] + background_ability_bonuses.get(k, 0) for k in ABILITY_KEYS
        }
        for k, val in final_ability_scores.items():
            if val > 20:
                raise CharacterCreationError(
                    f"Final ability score for '{k}' cannot exceed 20 (got {val})."
                )

        bg_skills = set(bg_def["skills"])
        if proficient_skills is None:
            raise CharacterCreationError("Skill choices are required.")
        chosen_skills_set = set(proficient_skills)

        for s in chosen_skills_set:
            if s not in SKILL_DEFINITIONS:
                raise CharacterCreationError(f"Unknown skill: {s}")

        if not bg_skills.issubset(chosen_skills_set):
            raise CharacterCreationError(
                f"Selected skills must include the background skills: {bg_def['skills']}."
            )

        class_skills_chosen = chosen_skills_set - bg_skills
        allowed_class_skill_count = cls_def["skill_count"]
        if species == "Human":
            allowed_class_skill_count += 1

        valid_class_options = set(cls_def["skill_options"])
        for s in class_skills_chosen:
            if s not in valid_class_options and species != "Human":
                raise CharacterCreationError(
                    f"Skill '{s}' is not available for class '{character_class}'."
                )

        if len(class_skills_chosen) != allowed_class_skill_count:
            raise CharacterCreationError(
                f"Class '{character_class}' requires exactly {cls_def['skill_count']} skills "
                f"(chose {len(class_skills_chosen)})."
            )

        proficient_tools = proficient_tools or [bg_def["tool"]]
        origin_feat = origin_feat or bg_def["feat"]

        if character_class == "Fighter":
            valid_styles = [f["id"] for f in cls_def.get("fighting_styles", [])]
            if not fighting_style:
                raise CharacterCreationError("Fighter requires explicitly choosing a fighting style.")
            if fighting_style not in valid_styles:
                raise CharacterCreationError(
                    f"Invalid fighting style for Fighter: {fighting_style}"
                )
        else:
            fighting_style = None

        if not background_equipment_option:
            raise CharacterCreationError("Background equipment option must be explicitly selected ('A' or 'B').")
        if background_equipment_option not in ("A", "B"):
            raise CharacterCreationError("Background equipment option must be 'A' (package) or 'B' (50 GP).")
        bg_eq_opt = background_equipment_option
        if bg_eq_opt == "B":
            bg_items = ["50 Altın"]
        else:
            bg_items = list(bg_def["equipment"])

        if equipment_package:
            pkg_match = next(
                (p for p in cls_def.get("equipment_packages", []) if p["id"] == equipment_package),
                None,
            )
            if not pkg_match:
                raise CharacterCreationError(
                    f"Invalid equipment package: {equipment_package}"
                )
            class_items = list(pkg_match["items"])
            if equipment_choices is not None:
                unauthorized = [it for it in equipment_choices if it not in class_items]
                if unauthorized:
                    raise CharacterCreationError(
                        f"Equipment choices contain unauthorized items for package {equipment_package}: {unauthorized}"
                    )
        elif equipment_choices is not None:
            if not isinstance(equipment_choices, list) or not equipment_choices:
                raise CharacterCreationError("Equipment choices must be a non-empty list of items.")
            all_legal_items = {
                item for pkg in cls_def.get("equipment_packages", []) for item in pkg.get("items", [])
            }
            unauthorized = [it for it in equipment_choices if it not in all_legal_items]
            if unauthorized:
                raise CharacterCreationError(
                    f"Unauthorized equipment for {character_class}: {unauthorized}"
                )
            matching_pkg = next(
                (pkg for pkg in cls_def.get("equipment_packages", []) if set(equipment_choices) == set(pkg.get("items", []))),
                None,
            )
            if not matching_pkg:
                raise CharacterCreationError(
                    f"Equipment choices do not form a legal starting equipment package for {character_class}."
                )
            equipment_package = matching_pkg["id"]
            class_items = list(matching_pkg["items"])
        elif cls_def.get("equipment_packages"):
            raise CharacterCreationError("Class equipment package must be explicitly selected.")
        else:
            class_items = []

        combined_items: list[str] = []
        for item in class_items + bg_items:
            if item not in combined_items or item.endswith("Altın") or item.endswith("GP"):
                combined_items.append(item)
        equipment_choices = combined_items

        if cls_def.get("is_spellcaster"):
            sp_cat = SPELLS_CATALOG.get(character_class, {})
            valid_cantrips = {c["id"] for c in sp_cat.get("cantrips", [])}
            valid_spells = {s["id"] for s in sp_cat.get("spells_level_1", [])}
            req_cantrips = cls_def.get("cantrips_count", 0)
            req_spells = cls_def.get("spells_count", 0)

            if req_cantrips > 0 and cantrips is None:
                raise CharacterCreationError(
                    f"{character_class} requires choosing {req_cantrips} cantrips."
                )
            if req_spells > 0 and spells is None:
                raise CharacterCreationError(
                    f"{character_class} requires choosing {req_spells} 1st-level spells."
                )

            cantrips = cantrips or []
            spells = spells or []

            for c in cantrips:
                if c not in valid_cantrips:
                    raise CharacterCreationError(
                        f"Invalid cantrip '{c}' for {character_class}."
                    )
            for s in spells:
                if s not in valid_spells:
                    raise CharacterCreationError(
                        f"Invalid 1st-level spell '{s}' for {character_class}."
                    )

            if len(cantrips) != req_cantrips:
                raise CharacterCreationError(
                    f"{character_class} must choose exactly {req_cantrips} cantrips "
                    f"(chose {len(cantrips)})."
                )
            if len(spells) != req_spells:
                raise CharacterCreationError(
                    f"{character_class} must choose exactly {req_spells} 1st-level spells "
                    f"(chose {len(spells)})."
                )
        else:
            cantrips = []
            spells = []

        # Roleplay non-mechanical identity fields validation
        if appearance is not None:
            if not isinstance(appearance, str) or len(appearance) > 1000:
                raise CharacterCreationError("Appearance must be a text string up to 1000 characters.")
        if personality is not None:
            if not isinstance(personality, str) or len(personality) > 1000:
                raise CharacterCreationError("Personality must be a text string up to 1000 characters.")
        if backstory is not None:
            if not isinstance(backstory, str) or len(backstory) > 2000:
                raise CharacterCreationError("Backstory must be a text string up to 2000 characters.")

        armor, has_shield = _detect_armor_and_shield(equipment_choices)
        derived = calculate_derived_stats(
            character_class=character_class,
            species=species,
            final_scores=final_ability_scores,
            chosen_feat=origin_feat,
            fighting_style=fighting_style,
            equipped_armor=armor,
            has_shield=has_shield,
        )

    modifiers = derived["modifiers"]
    level = 1
    proficiency_bonus = 2
    max_hp = derived["max_hp"]
    current_hp = derived["current_hp"]
    armor_class = derived["armor_class"]

    session.character.update(
        {
            "name": name,
            "race": race,
            "species": species,
            "class": character_class,
            "background": background,
            "alignment": alignment,
            "languages": list(languages),
            "background_equipment_option": bg_eq_opt,
            "ability_score_method": ability_score_method,
            "base_ability_scores": base_ability_scores,
            "background_ability_bonuses": background_ability_bonuses,
            "final_ability_scores": final_ability_scores,
            **final_ability_scores,
            "proficient_skills": list(proficient_skills),
            "proficient_tools": list(proficient_tools),
            "origin_feat": origin_feat,
            "fighting_style": fighting_style,
            "equipment_package": equipment_package,
            "equipment_choices": list(equipment_choices),
            "inventory": list(equipment_choices),
            "cantrips": list(cantrips),
            "spells": list(spells),
            "spell_slots_remaining": spell_rules.initial_slots(character_class),
            "appearance": appearance,
            "personality": personality,
            "backstory": backstory,
            "level": level,
            "xp": 0,
            "proficiency_bonus": proficiency_bonus,
            "max_hp": max_hp,
            "current_hp": current_hp,
            "armor_class": armor_class,
            "saving_throws": derived["saving_throws"],
            "saving_throw_mods": derived["saving_throw_mods"],
            "initiative": derived["initiative"],
            "spell_save_dc": derived["spell_save_dc"],
            "spell_attack_bonus": derived["spell_attack_bonus"],
            "passive_perception": derived["passive_perception"],
            **{f"{ability}_mod": modifier for ability, modifier in modifiers.items()},
            "modifiers": modifiers,
        }
    )

    # Transfer verified starting equipment to canonical gameplay inventory
    if hasattr(session, "world_state") and isinstance(session.world_state, dict):
        session.world_state["inventory"] = list(equipment_choices)
    if hasattr(session, "inventory") and isinstance(session.inventory, list):
        session.inventory = list(equipment_choices)