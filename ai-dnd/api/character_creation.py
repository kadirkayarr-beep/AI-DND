"""HTTP-facing character setup composed from the frozen game engine and D&D 2024 rules."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import game
import spells as spell_rules
from weapon_catalog import lookup as lookup_weapon
from api.dnd_2024_rules import (
    ABILITY_KEYS,
    BACKGROUND_DEFINITIONS,
    BACKGROUND_OPTION_B_GP,
    CLASS_DEFINITIONS,
    ORIGIN_FEATS,
    ALIGNMENTS,
    ARTISAN_TOOLS,
    STANDARD_LANGUAGES,
    SKILL_DEFINITIONS,
    SPECIES_DEFINITIONS,
    SPELLS_CATALOG,
    CharacterCreationError,
    canonical_origin_feat_name,
    calculate_derived_stats,
    get_equipment_armor_and_shield,
    get_expertise_choice_count,
    roll_4d6_drop_lowest,
    validate_ability_scores,
    validate_background_bonuses,
)

_FIGHTER_PACKAGE_C_WEAPON_LABELS = {
    "Büyük Kılıç (Greatsword)": "Greatsword",
}


def _settle_new_character_coin(session: Any) -> None:
    """New creation only: the coin written in the starting pack becomes the purse, once (never on load/resume)."""
    import bold_acts
    bold_acts.settle_coin_labels(session.world_state)
    if hasattr(session, "inventory") and isinstance(session.inventory, list):
        session.inventory = list(session.world_state["inventory"])


def _detect_armor_and_shield(equipment_choices: list[str] | None) -> tuple[str | None, bool]:
    return get_equipment_armor_and_shield(equipment_choices)


def _class_weapon_proficiencies(character_class: str, raw_level: int, applied_level: int) -> list[str]:
    """Selected new-character grant, not load-time class inference or mastery."""
    if (type(raw_level) is not int or type(applied_level) is not int
            or applied_level not in (1, 2) or not applied_level <= raw_level <= 20):
        raise CharacterCreationError("Weapon proficiency level is invalid.")
    if character_class == "Rogue":
        import character_progression
        return list(character_progression.for_class("Rogue").class_weapon_proficiencies)
    categories = {"Simple": "simple", "Martial": "martial"}
    source = CLASS_DEFINITIONS[character_class]["weapon_proficiencies"]
    if source != ["Simple", "Martial"]:
        raise CharacterCreationError("Unsupported weapon proficiency source.")
    return [categories[value] for value in source]


_DEFAULT_BACKGROUND_BY_CLASS = {
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


# The rare language a class is granted on top of the two it chooses.
_CLASS_CANT = {"Druid": "Druidic", "Rogue": "Thieves' Cant"}


def _combined_items(class_items: list[str], bg_items: list[str]) -> list[str]:
    """Class and background items in order; a repeated item is listed once, except written coin."""
    combined: list[str] = []
    for item in class_items + bg_items:
        if item not in combined or item.endswith("Altın") or item.endswith("GP"):
            combined.append(item)
    return combined


def _attach_derived(plan: SimpleNamespace) -> None:
    """Armor, shield and the derived numbers, from what both modes have settled by now."""
    plan.armor, plan.has_shield = _detect_armor_and_shield(plan.equipment_choices)
    plan.derived = calculate_derived_stats(
        character_class=plan.character_class,
        species=plan.species,
        final_scores=plan.final_ability_scores,
        chosen_feat=plan.origin_feat,
        chosen_feats=plan.origin_feats,
        fighting_style=plan.fighting_style,
        equipped_armor=plan.armor,
        has_shield=plan.has_shield,
    )


def _random_identity(session: game.GameSession, plan: SimpleNamespace) -> None:
    """Random mode: name, species and class are drawn first, then the background that goes with the class."""
    plan.name = session.rng.choice(game.RANDOM_NAMES)
    plan.race = session.rng.choice(game.RACES)
    plan.character_class = session.rng.choice(game.CLASSES)
    plan.species = plan.race
    giant_ancestry_options = SPECIES_DEFINITIONS.get(plan.species, {}).get(
        "giant_ancestry_options", [],
    )
    plan.giant_ancestry = (
        session.rng.choice(giant_ancestry_options)["id"]
        if giant_ancestry_options
        else None
    )
    plan.background = _DEFAULT_BACKGROUND_BY_CLASS.get(plan.character_class, "Soldier")
    plan.bg_def = BACKGROUND_DEFINITIONS[plan.background]
    plan.cls_def = CLASS_DEFINITIONS[plan.character_class]
    plan.alignment = "Neutral Good"


def _random_scores(session: game.GameSession, plan: SimpleNamespace) -> None:
    """Random mode: six engine-rolled scores, the best on the class's main ability, plus the background's +2/+1."""
    primary = plan.cls_def["primary_ability"]
    rolled_pool = [roll_4d6_drop_lowest(session.rng) for _ in range(6)]
    rolled_pool.sort(reverse=True)
    assigned_scores = {primary: rolled_pool[0]}
    rem = [a for a in ABILITY_KEYS if a != primary]
    session.rng.shuffle(rem)
    for a, s in zip(rem, rolled_pool[1:]):
        assigned_scores[a] = s
    plan.ability_score_method = "rolled"
    plan.base_ability_scores = assigned_scores
    bg_abilities = list(plan.bg_def["abilities"])
    plus_two = primary if primary in bg_abilities else bg_abilities[0]
    plus_one = next(a for a in bg_abilities if a != plus_two)
    plan.background_ability_bonuses = {plus_two: 2, plus_one: 1}
    plan.final_ability_scores = {
        k: assigned_scores[k] + plan.background_ability_bonuses.get(k, 0)
        for k in ABILITY_KEYS
    }


def _random_skills(
    session: game.GameSession, plan: SimpleNamespace, character_level: int,
) -> None:
    """Random mode: class skills, species bonus skills and expertise."""
    skill_options = game.CLASS_SKILL_OPTIONS.get(
        plan.character_class, plan.cls_def["skill_options"],
    )
    skill_count = 4 if plan.character_class == "Rogue" else 2
    plan.proficient_skills = session.rng.sample(skill_options, skill_count)
    species_bonus_skill_count = SPECIES_DEFINITIONS.get(plan.species, {}).get(
        "skill_bonus_count", 0,
    )
    plan.species_bonus_skills = session.rng.sample(
        [skill for skill in SKILL_DEFINITIONS if skill not in plan.proficient_skills],
        min(species_bonus_skill_count, len(SKILL_DEFINITIONS)),
    )
    plan.proficient_skills.extend(plan.species_bonus_skills)
    plan.expertise_skills = session.rng.sample(
        list(dict.fromkeys(plan.proficient_skills)),
        get_expertise_choice_count(plan.character_class, character_level),
    )
    plan.proficient_tools = [plan.bg_def["tool"]]


def _random_feats(session: game.GameSession, plan: SimpleNamespace) -> None:
    """Random mode: the background feat, and a second origin feat for species that get one."""
    plan.origin_feat = plan.bg_def["feat"]
    plan.species_bonus_feat = None
    if SPECIES_DEFINITIONS.get(plan.species, {}).get("origin_feat_bonus_count", 0):
        feat_options = [
            feat
            for feat in ORIGIN_FEATS
            if canonical_origin_feat_name(feat)
            != canonical_origin_feat_name(plan.origin_feat)
        ]
        if feat_options:
            plan.species_bonus_feat = session.rng.choice(feat_options)
    plan.origin_feats = [
        plan.origin_feat,
        *([plan.species_bonus_feat] if plan.species_bonus_feat else []),
    ]
    plan.fighting_style = (
        plan.cls_def["fighting_styles"][0]["id"]
        if plan.character_class == "Fighter" and plan.cls_def.get("fighting_styles")
        else None
    )


def _random_languages(session: game.GameSession, plan: SimpleNamespace) -> None:
    """Draw two standard languages besides Common, plus the class's own cant."""
    avail_langs = [lang for lang in STANDARD_LANGUAGES if lang != "Common"]
    random_langs = ["Common"] + sorted(session.rng.sample(avail_langs, 2))
    cant = _CLASS_CANT.get(plan.character_class)
    if cant and cant not in random_langs:
        random_langs.append(cant)
    plan.languages = random_langs


def _random_gear_and_spells(plan: SimpleNamespace) -> None:
    """Take the first equipment package, the background items and the first spells of the class."""
    packages = plan.cls_def.get("equipment_packages")
    plan.equipment_package = packages[0]["id"] if packages else None
    plan.bg_eq_opt = "A"
    class_items = list(packages[0]["items"]) if packages else []
    plan.equipment_choices = _combined_items(
        class_items, list(plan.bg_def["equipment"]),
    )
    plan.cantrips = []
    plan.spells = []
    if plan.cls_def.get("is_spellcaster"):
        sp_cat = SPELLS_CATALOG.get(plan.character_class, {})
        c_avail = [c["id"] for c in sp_cat.get("cantrips", [])]
        s_avail = [s["id"] for s in sp_cat.get("spells_level_1", [])]
        plan.cantrips = c_avail[: plan.cls_def.get("cantrips_count", 0)]
        plan.spells = s_avail[: plan.cls_def.get("spells_count", 0)]
    plan.origin = None
    plan.appearance = None
    plan.personality = None
    plan.backstory = None


def _random_plan(session: game.GameSession, character_level: int) -> SimpleNamespace:
    """Everything a random character needs, drawn from the session's own random stream in a fixed order."""
    plan = SimpleNamespace()
    _random_identity(session, plan)
    _random_scores(session, plan)
    _random_skills(session, plan, character_level)
    _random_feats(session, plan)
    _random_languages(session, plan)
    _random_gear_and_spells(plan)
    _attach_derived(plan)
    return plan


def _custom_name(plan: SimpleNamespace, inputs: dict[str, Any]) -> None:
    """Check the name: 1 to 40 characters once trimmed."""
    name = inputs["name"]
    name = name.strip() if isinstance(name, str) else ""
    if not name or len(name) > 40:
        raise CharacterCreationError("Character name must be 1–40 characters.")
    plan.name = name


def _custom_species(plan: SimpleNamespace, inputs: dict[str, Any]) -> None:
    """Check the species (or race) and the giant ancestry that only Goliaths take."""
    chosen_species = inputs["species"] or inputs["race"]
    if not chosen_species:
        raise CharacterCreationError("Species must be chosen.")
    if chosen_species not in SPECIES_DEFINITIONS and chosen_species not in game.RACES:
        raise CharacterCreationError("Choose a race or species supported by the rules.")
    plan.species = chosen_species
    plan.race = chosen_species
    giant_ancestry = inputs["giant_ancestry"]
    giant_ancestry_options = SPECIES_DEFINITIONS.get(plan.species, {}).get(
        "giant_ancestry_options", [],
    )
    valid_giant_ancestries = {item["id"] for item in giant_ancestry_options}
    if plan.species == "Goliath" and giant_ancestry not in valid_giant_ancestries:
        raise CharacterCreationError(
            "Goliath characters must choose one Giant Ancestry.",
        )
    if plan.species != "Goliath" and giant_ancestry is not None:
        raise CharacterCreationError("Giant Ancestry is only available to Goliaths.")
    plan.giant_ancestry = giant_ancestry


def _custom_class(plan: SimpleNamespace, inputs: dict[str, Any]) -> None:
    """Check the class."""
    character_class = inputs["character_class"]
    if not character_class:
        raise CharacterCreationError("Class must be chosen.")
    if character_class not in CLASS_DEFINITIONS and character_class not in game.CLASSES:
        raise CharacterCreationError("Choose a class supported by the rules.")
    plan.cls_def = CLASS_DEFINITIONS.get(character_class)
    if not plan.cls_def:
        raise CharacterCreationError(f"Unsupported class: {character_class}")
    plan.character_class = character_class


def _custom_background_and_alignment(
    plan: SimpleNamespace, inputs: dict[str, Any],
) -> None:
    """Check the background and the alignment."""
    background = inputs["background"]
    if not background:
        raise CharacterCreationError("Background must be chosen.")
    if background not in BACKGROUND_DEFINITIONS:
        raise CharacterCreationError("Choose a valid background from the rules.")
    plan.background = background
    plan.bg_def = BACKGROUND_DEFINITIONS[background]

    alignment = inputs["alignment"]
    if not alignment:
        raise CharacterCreationError("Alignment must be explicitly selected.")
    if alignment not in [a["id"] for a in ALIGNMENTS]:
        raise CharacterCreationError(
            f"Choose a valid alignment from the rules (received '{alignment}').",
        )
    plan.alignment = alignment


def _chosen_languages(languages: list[str] | None) -> list[str]:
    """Return the chosen languages other than Common, once the list itself is known to be sound."""
    if languages is None:
        raise CharacterCreationError(
            "Languages must be explicitly chosen (exactly 2 standard languages besides Common).",
        )
    if not isinstance(languages, list):
        raise CharacterCreationError("Languages must be provided as a list.")
    if len(languages) != len(set(languages)):
        raise CharacterCreationError("Languages cannot contain duplicates.")
    for lang in languages:
        if not isinstance(lang, str) or not lang.strip():
            raise CharacterCreationError("Invalid language name.")
    return [lang for lang in languages if lang != "Common"]


def _custom_languages(plan: SimpleNamespace, inputs: dict[str, Any]) -> None:
    """Check the language list: Common plus exactly two chosen standard languages, and the class's own cant."""
    chosen_langs = _chosen_languages(inputs["languages"])
    cant = _CLASS_CANT.get(plan.character_class)
    for lang in chosen_langs:
        if lang not in STANDARD_LANGUAGES and lang != cant:
            raise CharacterCreationError(
                f"Language '{lang}' is not an available standard language or granted rare language.",
            )
    if len(chosen_langs) != 2:
        raise CharacterCreationError(
            f"Character creation requires exactly 2 player-selected standard languages besides Common (chose {len(chosen_langs)}).",
        )
    final_languages = ["Common"] + sorted(chosen_langs)
    if cant and cant not in final_languages:
        final_languages.append(cant)
    plan.languages = final_languages


def _custom_base_scores(plan: SimpleNamespace, inputs: dict[str, Any]) -> None:
    """Check the score method and the six scores it produced."""
    method = inputs["ability_score_method"]
    if not method:
        raise CharacterCreationError("Ability score generation method must be chosen.")
    if method == "rolled":
        raise CharacterCreationError(
            "Rolled ability scores require game engine authority in random character mode; client-rolled scores cannot be submitted in custom mode.",
        )
    if method not in ("standard_array", "point_buy", "manual"):
        raise CharacterCreationError(f"Unsupported ability score method: {method}")
    plan.ability_score_method = method

    ability_scores = inputs["ability_scores"]
    if not ability_scores or not isinstance(ability_scores, dict):
        raise CharacterCreationError("Ability scores must be specified.")
    validate_ability_scores(method, ability_scores)
    plan.base_ability_scores = dict(ability_scores)


def _custom_scores(plan: SimpleNamespace, inputs: dict[str, Any]) -> None:
    """Check the scores, the background bonus split, and that every final score lies from 3 to 20."""
    _custom_base_scores(plan, inputs)
    bonuses = inputs["background_ability_bonuses"]
    if not bonuses or not isinstance(bonuses, dict):
        raise CharacterCreationError(
            "Background ability score bonuses must be explicitly selected.",
        )
    validate_background_bonuses(plan.background, bonuses, plan.base_ability_scores)
    plan.background_ability_bonuses = bonuses
    plan.final_ability_scores = {
        k: plan.base_ability_scores[k] + bonuses.get(k, 0) for k in ABILITY_KEYS
    }
    for k, val in plan.final_ability_scores.items():
        if val > 20:
            raise CharacterCreationError(
                f"Final ability score for '{k}' cannot exceed 20 (got {val}).",
            )
        if val < 3:
            too_low = f"Final ability score for '{k}' must be at least 3 (got {val})."
            raise CharacterCreationError(too_low)


def _custom_species_bonus_skills(
    plan: SimpleNamespace, inputs: dict[str, Any], chosen: set[str], bg_skills: set[str],
) -> tuple[bool, set[str], int]:
    """Species bonus skills, when the client sends them as their own field.

    Returns whether that field was used, the class-chosen skills, and how many class skills are allowed.
    """
    species_bonus_skills = inputs["species_bonus_skills"]
    bonus_fields_provided = (
        species_bonus_skills is not None or inputs["species_bonus_feat"] is not None
    )
    if not bonus_fields_provided:
        # Older API clients submit all non-background skills in one field.
        plan.species_bonus_skills = []
        allowed = plan.cls_def["skill_count"] + (1 if plan.species == "Human" else 0)
        return False, chosen - bg_skills, allowed
    species_bonus_skills = species_bonus_skills or []
    if len(species_bonus_skills) != len(set(species_bonus_skills)):
        raise CharacterCreationError(
            "Species bonus skill choices cannot contain duplicates.",
        )
    bonus_set = set(species_bonus_skills)
    expected = SPECIES_DEFINITIONS.get(plan.species, {}).get("skill_bonus_count", 0)
    if len(bonus_set) != expected:
        raise CharacterCreationError(
            f"{plan.species} requires exactly {expected} species bonus skills.",
        )
    if bonus_set & bg_skills:
        raise CharacterCreationError(
            "Species bonus skills cannot duplicate background skills.",
        )
    if not bonus_set.issubset(chosen):
        raise CharacterCreationError(
            "Proficient skills must include all selected species bonus skills.",
        )
    plan.species_bonus_skills = species_bonus_skills
    return True, chosen - bg_skills - bonus_set, plan.cls_def["skill_count"]


def _check_class_skills(
    plan: SimpleNamespace, class_skills_chosen: set[str], allowed: int,
) -> None:
    """Check the class skills are on the class list (a Human on the old single-field form may pick any) and the count is right."""
    valid_class_options = set(plan.cls_def["skill_options"])
    anything_goes = plan.species == "Human" and not plan.bonus_fields_provided
    for s in class_skills_chosen:
        if s not in valid_class_options and not anything_goes:
            raise CharacterCreationError(
                f"Skill '{s}' is not available for class '{plan.character_class}'.",
            )
    if len(class_skills_chosen) != allowed:
        raise CharacterCreationError(
            f"Class '{plan.character_class}' requires exactly {plan.cls_def['skill_count']} skills "
            f"(chose {len(class_skills_chosen)}).",
        )


def _custom_skills(plan: SimpleNamespace, inputs: dict[str, Any]) -> set[str]:
    """Check the proficient skills (background skills included, class skills counted); return the chosen set."""
    proficient_skills = inputs["proficient_skills"]
    bg_skills = set(plan.bg_def["skills"])
    if proficient_skills is None:
        raise CharacterCreationError("Skill choices are required.")
    if len(proficient_skills) != len(set(proficient_skills)):
        raise CharacterCreationError("Skill choices cannot contain duplicates.")
    chosen_skills_set = set(proficient_skills)
    for s in chosen_skills_set:
        if s not in SKILL_DEFINITIONS:
            raise CharacterCreationError(f"Unknown skill: {s}")
    if not bg_skills.issubset(chosen_skills_set):
        raise CharacterCreationError(
            f"Selected skills must include the background skills: {plan.bg_def['skills']}.",
        )
    plan.proficient_skills = proficient_skills
    bonus_fields_provided, class_skills_chosen, allowed_class_skill_count = (
        _custom_species_bonus_skills(plan, inputs, chosen_skills_set, bg_skills)
    )
    plan.bonus_fields_provided = bonus_fields_provided
    _check_class_skills(plan, class_skills_chosen, allowed_class_skill_count)
    return chosen_skills_set


def _custom_expertise(
    plan: SimpleNamespace,
    inputs: dict[str, Any],
    chosen_skills_set: set[str],
    character_level: int,
) -> None:
    """Check the expertise skills the class grants at this level, each one already proficient."""
    expected_expertise_count = get_expertise_choice_count(
        plan.character_class, character_level,
    )
    expertise_skills = inputs["expertise_skills"]
    if expertise_skills is None:
        expertise_skills = []
    if not isinstance(expertise_skills, list) or any(
        not isinstance(skill, str) or skill not in SKILL_DEFINITIONS
        for skill in expertise_skills
    ):
        raise CharacterCreationError("Expertise choices must be valid skills.")
    if len(expertise_skills) != len(set(expertise_skills)):
        raise CharacterCreationError("Expertise choices cannot contain duplicates.")
    if len(expertise_skills) != expected_expertise_count:
        raise CharacterCreationError(
            f"Class '{plan.character_class}' at level 1 requires exactly "
            f"{expected_expertise_count} Expertise skills.",
        )
    if not set(expertise_skills).issubset(chosen_skills_set):
        raise CharacterCreationError(
            "Expertise can only be chosen for skills the character is proficient in.",
        )
    plan.expertise_skills = expertise_skills


def _custom_species_bonus_feat(
    plan: SimpleNamespace, species_bonus_feat: str | None,
) -> None:
    """Check the extra origin feat: required for species that get one, refused for the rest, never the background feat."""
    bonus_feat_count = SPECIES_DEFINITIONS.get(plan.species, {}).get(
        "origin_feat_bonus_count", 0,
    )
    if not bonus_feat_count:
        if species_bonus_feat is not None:
            raise CharacterCreationError(
                f"{plan.species} does not grant an additional Origin Feat.",
            )
        return
    if not species_bonus_feat:
        raise CharacterCreationError(
            f"{plan.species} requires choosing an additional Origin Feat.",
        )
    if species_bonus_feat not in ORIGIN_FEATS:
        raise CharacterCreationError(
            f"Invalid species bonus Origin Feat: {species_bonus_feat}.",
        )
    if canonical_origin_feat_name(species_bonus_feat) == canonical_origin_feat_name(
        plan.origin_feat,
    ):
        raise CharacterCreationError(
            "The species bonus Origin Feat must differ from the background Origin Feat.",
        )


def _custom_feats(plan: SimpleNamespace, inputs: dict[str, Any]) -> None:
    """Check tools, the background feat, the species bonus feat (when asked for) and the Fighter's fighting style."""
    plan.proficient_tools = inputs["proficient_tools"] or [plan.bg_def["tool"]]
    plan.origin_feat = inputs["origin_feat"] or plan.bg_def["feat"]
    species_bonus_feat = inputs["species_bonus_feat"]
    if plan.bonus_fields_provided:
        _custom_species_bonus_feat(plan, species_bonus_feat)
    plan.species_bonus_feat = species_bonus_feat
    plan.origin_feats = [
        plan.origin_feat,
        *([species_bonus_feat] if species_bonus_feat else []),
    ]

    fighting_style = inputs["fighting_style"]
    if plan.character_class == "Fighter":
        valid_styles = [f["id"] for f in plan.cls_def.get("fighting_styles", [])]
        if not fighting_style:
            raise CharacterCreationError(
                "Fighter requires explicitly choosing a fighting style.",
            )
        if fighting_style not in valid_styles:
            raise CharacterCreationError(
                f"Invalid fighting style for Fighter: {fighting_style}",
            )
    else:
        fighting_style = None
    plan.fighting_style = fighting_style


def _items_of_package(
    plan: SimpleNamespace, equipment_package: str, equipment_choices: list[str] | None,
) -> list[str]:
    """Return the items of the named package; chosen items must all come from it."""
    pkg_match = next(
        (
            p
            for p in plan.cls_def.get("equipment_packages", [])
            if p["id"] == equipment_package
        ),
        None,
    )
    if not pkg_match:
        raise CharacterCreationError(f"Invalid equipment package: {equipment_package}")
    class_items = list(pkg_match["items"])
    if equipment_choices is not None:
        unauthorized = [it for it in equipment_choices if it not in class_items]
        if unauthorized:
            raise CharacterCreationError(
                f"Equipment choices contain unauthorized items for package {equipment_package}: {unauthorized}",
            )
    return class_items


def _items_of_chosen_items(
    plan: SimpleNamespace, equipment_choices: list[str],
) -> list[str]:
    """Return the items of the one package the chosen items add up to, and name that package on the plan."""
    packages = plan.cls_def.get("equipment_packages", [])
    all_legal_items = {item for pkg in packages for item in pkg.get("items", [])}
    unauthorized = [it for it in equipment_choices if it not in all_legal_items]
    if unauthorized:
        raise CharacterCreationError(
            f"Unauthorized equipment for {plan.character_class}: {unauthorized}",
        )
    matching_pkg = next(
        (
            pkg
            for pkg in packages
            if set(equipment_choices) == set(pkg.get("items", []))
        ),
        None,
    )
    if not matching_pkg:
        raise CharacterCreationError(
            f"Equipment choices do not form a legal starting equipment package for {plan.character_class}.",
        )
    plan.equipment_package = matching_pkg["id"]
    return list(matching_pkg["items"])


def _custom_class_items(
    plan: SimpleNamespace,
    equipment_package: str | None,
    equipment_choices: list[str] | None,
) -> list[str]:
    """Return the class's own starting items for the chosen package, or for the package the chosen items add up to."""
    if equipment_package:
        return _items_of_package(plan, equipment_package, equipment_choices)
    if equipment_choices is not None:
        if not isinstance(equipment_choices, list) or not equipment_choices:
            raise CharacterCreationError(
                "Equipment choices must be a non-empty list of items.",
            )
        return _items_of_chosen_items(plan, equipment_choices)
    if plan.cls_def.get("equipment_packages"):
        raise CharacterCreationError(
            "Class equipment package must be explicitly selected.",
        )
    return []


def _custom_equipment(plan: SimpleNamespace, inputs: dict[str, Any]) -> None:
    """Check the background equipment option (A pack or B coin) and the class package."""
    option = inputs["background_equipment_option"]
    if not option:
        raise CharacterCreationError(
            "Background equipment option must be explicitly selected ('A' or 'B').",
        )
    if option not in ("A", "B"):
        raise CharacterCreationError(
            "Background equipment option must be 'A' (package) or 'B' (50 GP).",
        )
    plan.bg_eq_opt = option
    bg_items = (
        [f"{BACKGROUND_OPTION_B_GP} Altın"]
        if option == "B"
        else list(plan.bg_def["equipment"])
    )
    plan.equipment_package = inputs["equipment_package"]
    class_items = _custom_class_items(
        plan, plan.equipment_package, inputs["equipment_choices"],
    )
    plan.equipment_choices = _combined_items(class_items, bg_items)


def _check_spell_lists(
    character_class: str,
    cls_def: dict[str, Any],
    cantrips: list[str],
    spells: list[str],
) -> None:
    """Check each chosen spell is on the class list and the counts are exactly what the class gets."""
    sp_cat = SPELLS_CATALOG.get(character_class, {})
    valid_cantrips = {c["id"] for c in sp_cat.get("cantrips", [])}
    valid_spells = {s["id"] for s in sp_cat.get("spells_level_1", [])}
    for c in cantrips:
        if c not in valid_cantrips:
            raise CharacterCreationError(
                f"Invalid cantrip '{c}' for {character_class}.",
            )
    for s in spells:
        if s not in valid_spells:
            raise CharacterCreationError(
                f"Invalid 1st-level spell '{s}' for {character_class}.",
            )
    req_cantrips = cls_def.get("cantrips_count", 0)
    req_spells = cls_def.get("spells_count", 0)
    if len(cantrips) != req_cantrips:
        raise CharacterCreationError(
            f"{character_class} must choose exactly {req_cantrips} cantrips "
            f"(chose {len(cantrips)}).",
        )
    if len(spells) != req_spells:
        raise CharacterCreationError(
            f"{character_class} must choose exactly {req_spells} 1st-level spells "
            f"(chose {len(spells)}).",
        )


def _custom_spells(plan: SimpleNamespace, inputs: dict[str, Any]) -> None:
    """Check casters choose their cantrips and first-level spells; other classes get none."""
    plan.cantrips = []
    plan.spells = []
    if not plan.cls_def.get("is_spellcaster"):
        return
    cantrips = inputs["cantrips"]
    spells = inputs["spells"]
    req_cantrips = plan.cls_def.get("cantrips_count", 0)
    req_spells = plan.cls_def.get("spells_count", 0)
    if req_cantrips > 0 and cantrips is None:
        raise CharacterCreationError(
            f"{plan.character_class} requires choosing {req_cantrips} cantrips.",
        )
    if req_spells > 0 and spells is None:
        raise CharacterCreationError(
            f"{plan.character_class} requires choosing {req_spells} 1st-level spells.",
        )
    plan.cantrips = cantrips or []
    plan.spells = spells or []
    _check_spell_lists(plan.character_class, plan.cls_def, plan.cantrips, plan.spells)


def _custom_identity_text(plan: SimpleNamespace, inputs: dict[str, Any]) -> None:
    """Roleplay (non-mechanical) identity fields: text only, bounded."""
    origin = inputs["origin"]
    if origin is not None:
        if not isinstance(origin, str) or len(origin) > 240:
            raise CharacterCreationError(
                "Origin must be a text string up to 240 characters.",
            )
        origin = origin.strip() or None
    plan.origin = origin
    for field, limit, label in (
        ("appearance", 1000, "Appearance"),
        ("personality", 1000, "Personality"),
        ("backstory", 2000, "Backstory"),
    ):
        value = inputs[field]
        if value is not None and (not isinstance(value, str) or len(value) > limit):
            too_long = f"{label} must be a text string up to {limit} characters."
            raise CharacterCreationError(too_long)
        setattr(plan, field, value)


def _custom_plan(inputs: dict[str, Any], character_level: int) -> SimpleNamespace:
    """Check every custom input, failing closed with no silent engine defaults; the first refusal wins."""
    plan = SimpleNamespace()
    _custom_name(plan, inputs)
    _custom_species(plan, inputs)
    _custom_class(plan, inputs)
    _custom_background_and_alignment(plan, inputs)
    _custom_languages(plan, inputs)
    _custom_scores(plan, inputs)
    chosen_skills_set = _custom_skills(plan, inputs)
    _custom_expertise(plan, inputs, chosen_skills_set, character_level)
    _custom_feats(plan, inputs)
    _custom_equipment(plan, inputs)
    _custom_spells(plan, inputs)
    _custom_identity_text(plan, inputs)
    _attach_derived(plan)
    return plan


def _weapon_proficiencies_for(
    session: game.GameSession, character_class: str, level: int,
) -> list[str] | None:
    """Return the weapon proficiencies a new Barbarian, Fighter or Rogue is granted (None for other classes)."""
    persisted_format = getattr(
        session, "_persisted_engine_format", game.SAVE_FORMAT_VERSION,
    )
    if character_class == "Barbarian":
        if persisted_format not in (4, 5, 6):
            raise CharacterCreationError("Weapon proficiency requires save format4–6.")
        return _class_weapon_proficiencies(character_class, level, level)
    if character_class in ("Fighter", "Rogue") and persisted_format in (4, 5, 6):
        # A loaded older format keeps its stored shape; Fighter creation there stays as it was.
        return _class_weapon_proficiencies(character_class, level, level)
    return None


def _write_character_record(
    session: game.GameSession, plan: SimpleNamespace, level: int,
) -> None:
    """Put the new character into the session: weapon proficiencies first, then the whole record."""
    derived = plan.derived
    modifiers = derived["modifiers"]
    weapon_proficiencies = _weapon_proficiencies_for(
        session, plan.character_class, level,
    )
    # Recreation must not inherit an earlier character's weapon entitlement.
    session.character.pop("weapon_proficiencies", None)
    if weapon_proficiencies is not None:
        session.character["weapon_proficiencies"] = weapon_proficiencies

    session.character.pop("primal_knowledge_choice", None)
    session.character.pop(
        "asi_choices", None,
    )  # new creation never inherits an earned ASI claim
    session.character.update(
        {
            "name": plan.name,
            "race": plan.race,
            "species": plan.species,
            "giant_ancestry": plan.giant_ancestry,
            "class": plan.character_class,
            "background": plan.background,
            "alignment": plan.alignment,
            "languages": list(plan.languages),
            "background_equipment_option": plan.bg_eq_opt,
            "ability_score_method": plan.ability_score_method,
            "base_ability_scores": plan.base_ability_scores,
            "background_ability_bonuses": plan.background_ability_bonuses,
            "final_ability_scores": plan.final_ability_scores,
            **plan.final_ability_scores,
            "proficient_skills": list(plan.proficient_skills),
            "expertise_skills": list(plan.expertise_skills or []),
            "species_bonus_skills": list(plan.species_bonus_skills or []),
            "proficient_tools": list(
                dict.fromkeys(
                    [
                        *plan.proficient_tools,
                        *(
                            ["Thieves' Tools"]
                            if plan.character_class == "Rogue"
                            else []
                        ),
                    ],
                ),
            ),
            "origin_feat": plan.origin_feat,
            "species_bonus_feat": plan.species_bonus_feat,
            "origin_feats": plan.origin_feats,
            "fighting_style": plan.fighting_style,
            "equipment_package": plan.equipment_package,
            "equipment_choices": list(plan.equipment_choices),
            "armor_origin": {"armor": plan.armor, "shield": plan.has_shield},
            "inventory": list(plan.equipment_choices),
            "cantrips": list(plan.cantrips),
            "spells": list(plan.spells),
            "origin": plan.origin,
            "spell_slots_remaining": spell_rules.initial_slots(plan.character_class),
            "appearance": plan.appearance,
            "personality": plan.personality,
            "backstory": plan.backstory,
            "level": level,
            "xp": 0,
            "proficiency_bonus": 2,
            "max_hp": derived["max_hp"],
            "current_hp": derived["current_hp"],
            "armor_class": derived["armor_class"],
            "saving_throws": derived["saving_throws"],
            "saving_throw_mods": derived["saving_throw_mods"],
            "initiative": derived["initiative"],
            "spell_save_dc": derived["spell_save_dc"],
            "spell_attack_bonus": derived["spell_attack_bonus"],
            "passive_perception": derived["passive_perception"],
            **{f"{ability}_mod": modifier for ability, modifier in modifiers.items()},
            "modifiers": modifiers,
        },
    )
    session.initialize_species_trait_state(giant_ancestry=plan.giant_ancestry)


def _gameplay_items(
    plan: SimpleNamespace, starting_gp: int | None, coin_label: str | None,
) -> tuple[list[str], int | None]:
    """Return the pack as gameplay items, and the class's verified cash (only Barbarian packages carry one)."""
    # Only new creation: never parse historical coin labels during load/resume.
    # Other legacy class/background packages are not source-certified currency.
    gameplay_items = list(plan.equipment_choices)
    class_starting_gp = None
    if plan.character_class == "Barbarian":
        # Only this verified new-character package; never parse legacy labels.
        class_starting_gp = {"A": 15, "B": 75}[plan.equipment_package]
        gameplay_items.remove(f"{class_starting_gp} GP")  # one class occurrence
        if plan.equipment_package == "A":
            index = gameplay_items.index("4 Handaxes")
            # Expansion follows display deduplication; a background Handaxe
            # remains a fifth separately owned item. No generic quantity parser.
            gameplay_items[index : index + 1] = ["Handaxe"] * 4
    if plan.character_class == "Fighter" and plan.equipment_package == "C":
        gameplay_items = [
            _FIGHTER_PACKAGE_C_WEAPON_LABELS.get(item, item) for item in gameplay_items
        ]
    if starting_gp is not None:
        gameplay_items.remove(coin_label)
    return gameplay_items, class_starting_gp


def _drop_unowned_held_weapons(
    hands: dict[str, Any], gameplay_items: list[Any],
) -> None:
    """Empty a hand that names a weapon the new pack does not contain."""
    owned_weapon_ids = {
        weapon["weapon_id"]
        for item in gameplay_items
        if isinstance(item, str)
        for weapon in [lookup_weapon(item)]
        if weapon is not None
    }
    for hand, held in hands.items():
        held_weapon = lookup_weapon(held)
        if held_weapon and held_weapon["weapon_id"] not in owned_weapon_ids:
            hands[hand] = None


def _set_barbarian_hands(world: dict[str, Any], equipment_package: str) -> None:
    """Put the Barbarian's greataxe (package A) in the main hand."""
    # New-character package selection, not runtime equipping or a save
    # migration. Materialization binds this alias to the owned item ID;
    # the attack owner still enforces two-handed grip requirements.
    hands = world.setdefault("equipment", {})
    hands.update(
        main_hand="greataxe" if equipment_package == "A" else None, off_hand=None,
    )


def _write_world_gear(
    session: game.GameSession,
    plan: SimpleNamespace,
    gameplay_items: list[Any],
    class_starting_gp: int | None,
    starting_gp: int | None,
) -> None:
    """Inventory, the Barbarian's hands, held weapons and the starting purse, in the world state."""
    world = session.world_state
    world["inventory"] = gameplay_items
    if plan.character_class == "Barbarian":
        _set_barbarian_hands(world, plan.equipment_package)
    if plan.character_class == "Monk" or (
        plan.character_class == "Fighter" and plan.equipment_package == "C"
    ):
        hands = world.get("equipment")
        if isinstance(hands, dict) and set(hands) == {"main_hand", "off_hand"}:
            _drop_unowned_held_weapons(hands, gameplay_items)
    if class_starting_gp is not None:
        # The verified class and background cash; other written coin in the
        # pack joins this purse once, below (_settle_new_character_coin).
        verified_background_gp = starting_gp if starting_gp is not None else 0
        world.setdefault("currency", {})["player"] = (
            class_starting_gp + verified_background_gp
        ) * 100
    elif starting_gp is not None:
        world.setdefault("currency", {})["player"] = starting_gp * 100
    world["starting_equipment_source"] = "PHB2024-background-v1"


def _initialize_class_features(
    session: game.GameSession, plan: SimpleNamespace,
) -> None:
    """Spell scope, Rage and Monk features start from the armor the new character wears."""
    import spell_scope

    spell_scope.initialize(session)
    import barbarian_rage

    barbarian_rage.initialize(session, known_unarmored=plan.armor is None)
    import monk_features

    monk_features.initialize(
        session, known_unarmored=plan.armor is None and not plan.has_shield,
    )


def _name_artisan_tools(plan: SimpleNamespace) -> None:
    """Replace the generic Artisan's Tools item with the one tool the Artisan chose."""
    if plan.background != "Artisan":
        return
    selected = [tool for tool in plan.proficient_tools if tool in ARTISAN_TOOLS]
    if len(selected) != 1:
        raise CharacterCreationError(
            "Artisan requires one selected Artisan's Tools proficiency.",
        )
    plan.equipment_choices = [
        selected[0] if item == "Artisan's Tools" else item
        for item in plan.equipment_choices
    ]


def _starting_coin(plan: SimpleNamespace) -> tuple[int | None, str | None]:
    """Return the background's starting gold and the coin label written in the pack for it (None when it has none)."""
    starting_gp = (
        BACKGROUND_OPTION_B_GP
        if plan.bg_eq_opt == "B"
        else plan.bg_def.get("starting_gp")
    )
    if starting_gp is None:
        return None, None
    return (
        starting_gp,
        f"{BACKGROUND_OPTION_B_GP} Altın"
        if plan.bg_eq_opt == "B"
        else f"{starting_gp} GP",
    )


def _apply_plan(session: game.GameSession, plan: SimpleNamespace, level: int) -> None:
    """Write a settled plan into the session: record, gear, purse and class features."""
    # Validate new-character source selection before mutating the character.
    _name_artisan_tools(plan)
    starting_gp, coin_label = _starting_coin(plan)

    _write_character_record(session, plan, level)

    # Transfer verified starting equipment to canonical gameplay inventory
    gameplay_items, class_starting_gp = _gameplay_items(plan, starting_gp, coin_label)
    has_world = hasattr(session, "world_state") and isinstance(
        session.world_state, dict,
    )
    if has_world:
        _write_world_gear(session, plan, gameplay_items, class_starting_gp, starting_gp)
    if hasattr(session, "inventory") and isinstance(session.inventory, list):
        session.inventory = list(gameplay_items)
    if has_world:
        # After the purse lines: the remaining written coin moves into the purse; the total is unchanged.
        _settle_new_character_coin(session)
    if isinstance(session, game.GameSession):
        _initialize_class_features(session, plan)


def configure_character(
    session: Any,
    *,
    mode: str,
    name: str | None = None,
    race: str | None = None,
    species: str | None = None,
    giant_ancestry: str | None = None,
    character_class: str | None = None,
    background: str | None = None,
    alignment: str | None = None,
    ability_score_method: str | None = None,
    ability_scores: dict[str, int] | None = None,
    background_ability_bonuses: dict[str, int] | None = None,
    proficient_skills: list[str] | None = None,
    expertise_skills: list[str] | None = None,
    proficient_tools: list[str] | None = None,
    origin_feat: str | None = None,
    species_bonus_feat: str | None = None,
    species_bonus_skills: list[str] | None = None,
    fighting_style: str | None = None,
    equipment_package: str | None = None,
    equipment_choices: list[str] | None = None,
    background_equipment_option: str | None = None,
    languages: list[str] | None = None,
    cantrips: list[str] | None = None,
    spells: list[str] | None = None,
    origin: str | None = None,
    appearance: str | None = None,
    personality: str | None = None,
    backstory: str | None = None,
    **extra: Any,
) -> None:
    """Populate the engine's canonical character record following D&D 2024 rules."""
    if mode not in {"custom", "random"}:
        raise CharacterCreationError("Choose custom or random character creation.")
    character_level = 1

    inputs = {
        "name": name,
        "race": race,
        "species": species,
        "giant_ancestry": giant_ancestry,
        "character_class": character_class,
        "background": background,
        "alignment": alignment,
        "ability_score_method": ability_score_method,
        "ability_scores": ability_scores,
        "background_ability_bonuses": background_ability_bonuses,
        "proficient_skills": proficient_skills,
        "expertise_skills": expertise_skills,
        "proficient_tools": proficient_tools,
        "origin_feat": origin_feat,
        "species_bonus_feat": species_bonus_feat,
        "species_bonus_skills": species_bonus_skills,
        "fighting_style": fighting_style,
        "equipment_package": equipment_package,
        "equipment_choices": equipment_choices,
        "background_equipment_option": background_equipment_option,
        "languages": languages,
        "cantrips": cantrips,
        "spells": spells,
        "origin": origin,
        "appearance": appearance,
        "personality": personality,
        "backstory": backstory,
    }

    if mode == "random":
        if any(value is not None for value in inputs.values()):
            raise CharacterCreationError(
                "Random character creation does not accept custom character fields.",
            )
        plan = _random_plan(session, character_level)
    else:
        plan = _custom_plan(inputs, character_level)
    _apply_plan(session, plan, character_level)
