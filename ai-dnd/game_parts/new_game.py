import game


def initialize_game(creation_choice=None, input_fn=input, print_fn=print):
    """Create or reset the player state without running the game loop.

    Importing this module is intentionally side-effect free.  The terminal
    entry point calls this function interactively, while tests and other
    callers can pass a choice and receive a ready-to-use rules engine.
    """
    world_state = game._session().world_state
    interactive = creation_choice is None
    if interactive:
        print_fn("=" * 35)
        print_fn("       UNWRITTEN")
        print_fn("=" * 35)
        print_fn("Oyuna hoş geldin.\n")
        print_fn("=== KARAKTER OLUŞTURMA ===")
        print_fn("---------------------------")
        print_fn("1. Normal karakter oluştur")
        print_fn("2. 🎲 Tamamen random karakter")
        while True:
            creation_choice = input_fn("\nSeçimin: ").strip()
            if creation_choice in ("1", "2"):
                break
            print_fn("❌ Lütfen 1 veya 2 seç.")
    else:
        creation_choice = str(creation_choice)

    if creation_choice == "2":
        if interactive:
            (
                character_name,
                character_race,
                character_class,
                strength,
                dexterity,
                constitution,
                intelligence,
                wisdom,
                charisma,
                proficient_skills
            ) = game.create_random_character()
        else:
            # Stable, quiet defaults give imported callers a valid game state.
            (
                character_name,
                character_race,
                character_class,
                strength,
                dexterity,
                constitution,
                intelligence,
                wisdom,
                charisma,
                proficient_skills
            ) = (
                "TestHero",
                "Human",
                "Fighter",
                16,
                14,
                14,
                10,
                12,
                10,
                ["Athletics", "Perception"],
            )
    else:
        character_name = input_fn("\nKarakterinin adı: ") if interactive else "TestHero"
        character_race = game.choose_option("=== IRK SEÇ ===", game.RACES) if interactive else "Human"
        character_class = game.choose_option("=== SINIF SEÇ ===", game.CLASSES) if interactive else "Fighter"
        if interactive:
            (
                strength,
                dexterity,
                constitution,
                intelligence,
                wisdom,
                charisma
            ) = game.assign_stats()
            proficient_skills = game.choose_skill_proficiencies(character_class)
        else:
            strength, dexterity, constitution = 16, 14, 14
            intelligence, wisdom, charisma = 10, 12, 10
            proficient_skills = ["Athletics", "Perception"]

    strength_mod = game.get_modifier(strength)
    dexterity_mod = game.get_modifier(dexterity)
    constitution_mod = game.get_modifier(constitution)
    intelligence_mod = game.get_modifier(intelligence)
    wisdom_mod = game.get_modifier(wisdom)
    charisma_mod = game.get_modifier(charisma)
    modifiers = {
        "strength": strength_mod,
        "dexterity": dexterity_mod,
        "constitution": constitution_mod,
        "intelligence": intelligence_mod,
        "wisdom": wisdom_mod,
        "charisma": charisma_mod,
    }
    level = 1
    proficiency_bonus = 2
    max_hp = game.calculate_hp(character_class, constitution_mod)
    current_hp = max_hp
    armor_class = game.calculate_ac(
        character_class,
        dexterity_mod,
        constitution_mod,
        wisdom_mod,
    )
    game._session().character.update({
        "name": character_name, "race": character_race, "class": character_class,
        "strength": strength, "dexterity": dexterity, "constitution": constitution,
        "intelligence": intelligence, "wisdom": wisdom, "charisma": charisma,
        "proficient_skills": proficient_skills, "level": level,
        "proficiency_bonus": proficiency_bonus, "max_hp": max_hp,
        "current_hp": current_hp, "armor_class": armor_class,
        "strength_mod": strength_mod, "dexterity_mod": dexterity_mod,
        "constitution_mod": constitution_mod, "intelligence_mod": intelligence_mod,
        "wisdom_mod": wisdom_mod, "charisma_mod": charisma_mod, "modifiers": modifiers,
    })

    if interactive:
        print_fn()
        print_fn("=" * 35)
        print_fn("       KARAKTERİN OLUŞTURULDU")
        print_fn("=" * 35)
        print_fn("İsim:", character_name)
        print_fn("Irk:", character_race)
        print_fn("Sınıf:", character_class)
        print_fn()
        print_fn("LEVEL:", level)
        print_fn("HP:", current_hp, "/", max_hp)
        print_fn("AC:", armor_class)
        print_fn("Proficiency Bonus: +", proficiency_bonus)
        print_fn()
        print_fn("IRK ÖZELLİKLERİ")
        print_fn("---------------------------")
        for feature in game.RACE_FEATURES[character_race]:
            print_fn("-", feature)
        print_fn()
        print_fn("SINIF ÖZELLİKLERİ")
        print_fn("---------------------------")
        for feature in game.CLASS_FEATURES[character_class]:
            print_fn("-", feature)
        print_fn()
        print_fn("SKILL PROFICIENCIES")
        print_fn("---------------------------")
        for skill in proficient_skills:
            print_fn("-", skill, "(" + game.SKILLS[skill].upper() + ")")
        print_fn()
        print_fn("INVENTORY")
        print_fn("---------------------------")
        for item in world_state["inventory"]:
            print_fn("-", item)
        print_fn()
        print_fn("STATLAR")
        print_fn("---------------------------")
        for label, value in (
            ("STR", strength),
            ("DEX", dexterity),
            ("CON", constitution),
            ("INT", intelligence),
            ("WIS", wisdom),
            ("CHA", charisma),
        ):
            print_fn(f"{label}:", value)
        print_fn()
        print_fn("MODIFIERLAR")
        print_fn("---------------------------")
        for label, value in (
            ("STR", strength_mod),
            ("DEX", dexterity_mod),
            ("CON", constitution_mod),
            ("INT", intelligence_mod),
            ("WIS", wisdom_mod),
            ("CHA", charisma_mod),
        ):
            print_fn(f"{label}:", value)
        print_fn()
        print_fn("SAVAŞ BİLGİLERİ")
        print_fn("---------------------------")
        print_fn("Level:", level)
        print_fn("HP:", current_hp, "/", max_hp)
        print_fn("AC:", armor_class)
        print_fn("Proficiency Bonus: +", proficiency_bonus)
        print_fn("=" * 35)

    return {
        "name": character_name,
        "race": character_race,
        "class": character_class,
        "level": level,
        "current_hp": current_hp,
        "max_hp": max_hp,
        "armor_class": armor_class,
        "modifiers": modifiers.copy(),
        "proficient_skills": list(proficient_skills),
    }
