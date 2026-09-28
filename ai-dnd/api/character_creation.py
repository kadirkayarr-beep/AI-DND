"""HTTP-facing character setup composed from the frozen game engine."""

from __future__ import annotations

from typing import Any

import game


class CharacterCreationError(ValueError):
    """A requested character choice is not supported by the game engine."""


def configure_character(
    session: Any,
    *,
    mode: str,
    name: str | None = None,
    race: str | None = None,
    character_class: str | None = None,
) -> None:
    """Populate the engine's existing character record with server-rolled values."""
    if mode not in {"custom", "random"}:
        raise CharacterCreationError("Choose custom or random character creation.")

    if mode == "custom":
        name = name.strip() if isinstance(name, str) else ""
        if not name or len(name) > 40:
            raise CharacterCreationError("Character name must be 1–40 characters.")
        if race not in game.RACES:
            raise CharacterCreationError("Choose a race supported by the game engine.")
        if character_class not in game.CLASSES:
            raise CharacterCreationError("Choose a class supported by the game engine.")
    elif any(value is not None for value in (name, race, character_class)):
        raise CharacterCreationError(
            "Random character creation does not accept custom character fields."
        )

    if mode == "random":
        name = session.rng.choice(game.RANDOM_NAMES)
        race = session.rng.choice(game.RACES)
        character_class = session.rng.choice(game.CLASSES)

    if name is None or race is None or character_class is None:
        raise CharacterCreationError("Character details are incomplete.")

    # This follows the engine's existing 4d6-drop-lowest random generation
    # without calling its console-printing wrapper from an HTTP request.
    rolled_stats = [session.roll_stat() for _ in range(6)]
    session.rng.shuffle(rolled_stats)
    (
        strength,
        dexterity,
        constitution,
        intelligence,
        wisdom,
        charisma,
    ) = rolled_stats

    available_skills = game.CLASS_SKILL_OPTIONS[character_class]
    skill_count = 4 if character_class == "Rogue" else 2
    proficient_skills = session.rng.sample(available_skills, skill_count)

    ability_scores = {
        "strength": strength,
        "dexterity": dexterity,
        "constitution": constitution,
        "intelligence": intelligence,
        "wisdom": wisdom,
        "charisma": charisma,
    }
    modifiers = {
        ability: session.get_modifier(score)
        for ability, score in ability_scores.items()
    }
    level = 1
    proficiency_bonus = 2
    max_hp = session.calculate_hp(character_class, modifiers["constitution"])
    armor_class = session.calculate_ac(
        character_class,
        modifiers["dexterity"],
        modifiers["constitution"],
        modifiers["wisdom"],
    )

    # Keep the established dictionary identity and schema; callers and the
    # persistence layer already hold references to this canonical record.
    session.character.update(
        {
            "name": name,
            "race": race,
            "class": character_class,
            **ability_scores,
            "proficient_skills": proficient_skills,
            "level": level,
            "proficiency_bonus": proficiency_bonus,
            "max_hp": max_hp,
            "current_hp": max_hp,
            "armor_class": armor_class,
            **{f"{ability}_mod": modifier for ability, modifier in modifiers.items()},
            "modifiers": modifiers,
        }
    )