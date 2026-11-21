import game
from api.core_resolution import (
    resolve_skill_check,
)
import copy
import timed_gameplay
import weapon_attack


def roll_d20():
    random = game._session().rng
    return random.randint(1, 20)

def get_modifier(stat):
    return (stat - 10) // 2

def roll_stat():
    random = game._session().rng
    rolls = [random.randint(1, 6) for _ in range(4)]
    rolls.remove(min(rolls))
    return sum(rolls)

def choose_option(title, options):

    print()
    print(title)
    print("---------------------------")

    for i, option in enumerate(options, start=1):
        print(f"{i}. {option}")

    while True:

        choice = input("\nSeçimin: ").strip()

        try:

            choice = int(choice)

            if 1 <= choice <= len(options):
                return options[choice - 1]

            print("❌ Geçersiz seçim.")

        except ValueError:

            print("❌ Lütfen sadece numara gir.")

def create_random_character():
    """
    Testleri hızlandırmak için tamamen random karakter oluşturur.
    """

    random = game._session().rng
    name = random.choice(game.RANDOM_NAMES)
    race = random.choice(game.RACES)
    character_class = random.choice(game.CLASSES)

    # 4d6 drop lowest x6
    rolled_stats = [game.roll_stat() for _ in range(6)]

    # Altı stat değerini tamamen rastgele dağıt
    random.shuffle(rolled_stats)

    (
        strength,
        dexterity,
        constitution,
        intelligence,
        wisdom,
        charisma
    ) = rolled_stats

    # Sınıfa uygun rastgele proficiency
    available_skills = game.CLASS_SKILL_OPTIONS[character_class]

    if character_class == "Rogue":
        number_to_choose = 4
    else:
        number_to_choose = 2

    proficient_skills = random.sample(
        available_skills,
        number_to_choose
    )

    print("\n🎲 RANDOM KARAKTER OLUŞTURULUYOR...")
    print("-----------------------------------")
    print("İsim:", name)
    print("Irk:", race)
    print("Sınıf:", character_class)
    print("Statlar:", rolled_stats)
    print("Skilller:", ", ".join(proficient_skills))

    return (
        name,
        race,
        character_class,
        strength,
        dexterity,
        constitution,
        intelligence,
        wisdom,
        charisma,
        proficient_skills
    )

def assign_stats():

    rolled_stats = [game.roll_stat() for _ in range(6)]

    remaining_stats = rolled_stats.copy()

    stat_names = [
        ("STR", "strength"),
        ("DEX", "dexterity"),
        ("CON", "constitution"),
        ("INT", "intelligence"),
        ("WIS", "wisdom"),
        ("CHA", "charisma")
    ]

    assigned = {}

    print("\n=== STAT SONUÇLARIN ===")
    print("---------------------------")

    for i, value in enumerate(rolled_stats, start=1):
        print(f"{i}. {value}")

    print("---------------------------")

    print(
        "Bu 6 değeri STR, DEX, CON, INT, WIS ve CHA'ya dağıtacağız."
    )

    print()

    for display_name, variable_name in stat_names:

        print("Kalan değerler:", remaining_stats)

        while True:

            try:

                value = int(
                    input(f"{display_name} için değer seç: ")
                )

                if value not in remaining_stats:

                    print(
                        "❌ Bu değer mevcut değil "
                        "veya daha önce kullanıldı."
                    )

                    continue

                assigned[variable_name] = value

                remaining_stats.remove(value)

                break

            except ValueError:

                print("❌ Lütfen listedeki bir sayıyı gir.")

    return (
        assigned["strength"],
        assigned["dexterity"],
        assigned["constitution"],
        assigned["intelligence"],
        assigned["wisdom"],
        assigned["charisma"]
    )

def choose_skill_proficiencies(character_class):

    available_skills = game.CLASS_SKILL_OPTIONS[character_class]

    if character_class == "Rogue":
        number_to_choose = 4
    else:
        number_to_choose = 2

    chosen_skills = []

    print()
    print("=== SKILL PROFICIENCY ===")
    print("---------------------------")

    print(
        f"{character_class} için "
        f"{number_to_choose} skill seç."
    )

    print()

    for i, skill in enumerate(available_skills, start=1):
        print(f"{i}. {skill}")

    while len(chosen_skills) < number_to_choose:

        print()

        print(
            f"Seçim {len(chosen_skills) + 1}/"
            f"{number_to_choose}"
        )

        try:

            choice = int(input("Skill numarası: "))

        except ValueError:

            print("❌ Lütfen bir numara gir.")

            continue

        if choice < 1 or choice > len(available_skills):

            print("❌ Geçersiz seçim.")

            continue

        selected_skill = available_skills[choice - 1]

        if selected_skill in chosen_skills:

            print("❌ Bu skill zaten seçildi.")

            continue

        chosen_skills.append(selected_skill)

        print("✅ Seçildi:", selected_skill)

    return chosen_skills

def calculate_hp(character_class, constitution_mod):

    hit_die = game.CLASS_HIT_DICE[character_class]

    return hit_die + constitution_mod

def calculate_ac(
    character_class,
    dexterity_mod,
    constitution_mod,
    wisdom_mod
):

    if character_class == "Barbarian":

        return 10 + dexterity_mod + constitution_mod

    if character_class == "Monk":

        return 10 + dexterity_mod + wisdom_mod

    return 10 + dexterity_mod

def _perform_skill_check(
    skill,
    dc,
    modifiers,
    proficient_skills,
    proficiency_bonus,
    advantage=False,
    disadvantage=False,
    expertise_skills=None,
    check_feature=None,
    check_evidence=None,
):
    import barbarian_rage
    import fighter_features
    tactical = check_feature == fighter_features.TACTICAL_MIND
    primal = check_feature is not None and not tactical
    if primal:
        barbarian_rage.require_primal_knowledge(game._session(), skill, check_feature)
    elif tactical:
        fighter_features.require_tactical_mind(game._session())
    ability = "strength" if primal else game.SKILLS[skill]
    barbarian_rage.settle(game._session())
    if primal:
        barbarian_rage.require_primal_knowledge(game._session(), skill, check_feature)
    rage_advantage = barbarian_rage.strength_advantage(game._session(), "player", ability)
    athlete_advantage = fighter_features.remarkable_athlete_check(game._session().character, skill, ability)
    pace_advantage, pace_disadvantage = timed_gameplay.pace_effects(game._session().world_state, skill)
    advantage = bool(advantage or pace_advantage or rage_advantage or athlete_advantage)
    disadvantage = bool(disadvantage or pace_disadvantage)
    modifier = modifiers[ability]
    is_proficient = skill in proficient_skills
    expertise_skills = expertise_skills or ()
    has_expertise = is_proficient and skill in expertise_skills
    proficiency_modifier = (
        proficiency_bonus * (2 if has_expertise else 1)
        if is_proficient
        else 0
    )
    def resolve(roll_fn, adjustment=0):
        return resolve_skill_check(
            roll_fn=roll_fn,
            skill=skill,
            ability=ability,
            dc=dc,
            ability_modifier=modifier,
            proficiency_modifier=proficiency_modifier,
            circumstantial_modifier=adjustment - 2 * weapon_attack.exhaustion(game._session().character),
            proficient=is_proficient,
            expertise=has_expertise,
            advantage=advantage,
            disadvantage=disadvantage,
        )
    resolution = resolve(game.roll_d20)
    tactical_mind_roll = None
    if tactical and resolution["outcome"] != "SUCCESS":
        # The same d20 faces, plus the feature's d10: the use is expended only if that makes the check succeed.
        tactical_mind_roll = fighter_features.tactical_mind_roll(game._session())
        resolution = resolve(iter(resolution["raw_rolls"]).__next__, tactical_mind_roll)
        if resolution["outcome"] == "SUCCESS":
            fighter_features.spend_tactical_mind(game._session())
    dice_rolls = resolution["raw_rolls"]
    dice = resolution["selected_roll"]
    total = resolution["total"]
    result = "BAŞARILI" if resolution["outcome"] == "SUCCESS" else "BAŞARISIZ"

    result_data = {
        "skill": skill,
        "ability": ability,
        "dice": dice,
        "dice_rolls": dice_rolls,
        "advantage": advantage,
        "disadvantage": disadvantage,
        "modifier": modifier,
        "proficient": is_proficient,
        "expertise": has_expertise,
        "proficiency_bonus": proficiency_modifier,
        "total_bonus": modifier + proficiency_modifier - 2 * weapon_attack.exhaustion(game._session().character) + (tactical_mind_roll or 0),
        "total": total,
        "dc": dc,
        "result": result,
        "resolution": resolution,
    }

    if tactical:
        result_data["tactical_mind_roll"] = tactical_mind_roll
        if check_evidence is not None:
            check_evidence.append(fighter_features.record_tactical_mind(result_data))
    elif check_feature is not None and check_evidence is not None:
        check_evidence.append(barbarian_rage.record_primal_knowledge(game._session(), result_data))
    return result_data

def _new_species_trait_state(species, proficiency_bonus):
    has_aasimar_traits = species == "Aasimar"
    is_goliath = species == "Goliath"
    has_orc_endurance = species in {"Orc", "Half-Orc"}
    return {
        "healing_hands_uses_remaining": 1 if has_aasimar_traits else 0,
        "celestial_revelation_uses_remaining": 1 if has_aasimar_traits else 0,
        "active_celestial_form": None,
        "celestial_revelation_turns_remaining": 0,
        "celestial_damage_used_turn": None,
        "giant_ancestry_uses_remaining": proficiency_bonus if is_goliath else 0,
        "giant_ancestry_armed": False,
        "large_form_uses_remaining": 1 if is_goliath else 0,
        "large_form_turns_remaining": 0,
        "adrenaline_rush_uses_remaining": proficiency_bonus if species == "Orc" else 0,
        "relentless_endurance_available": has_orc_endurance,
        "temporary_hit_points": 0,
        "bonus_action_used_round": None,
        "movement_budget_ft": 0,
        "movement_effect": None,
        "player_turn_counter": 0,
    }

def _new_persisted_species_trait_state(species, proficiency_bonus):
    if species not in game.SPECIES_WITH_TRAIT_STATE:
        return None
    return game._new_species_trait_state(species, proficiency_bonus)

def initialize_species_trait_state(giant_ancestry=None):
    """Initialize persisted, server-owned species resources for a character."""
    character = game._session().character
    species = character.get("species", character.get("race"))
    proficiency_bonus = character.get("proficiency_bonus", 2)
    if type(proficiency_bonus) is not int or proficiency_bonus < 0:
        raise ValueError("Character proficiency bonus is invalid.")
    if giant_ancestry is not None and giant_ancestry not in game.GIANT_ANCESTRY_IDS:
        raise ValueError("Choose a valid Giant Ancestry.")
    if species != "Goliath" and giant_ancestry is not None:
        raise ValueError("Giant Ancestry is only available to Goliaths.")
    character["giant_ancestry"] = giant_ancestry
    character["speed_ft"] = 35 if species == "Goliath" else 30
    character["species_trait_state"] = game._new_persisted_species_trait_state(
        species, proficiency_bonus
    )
    return copy.deepcopy(character["species_trait_state"])

def calculate_attack_bonus():
    """Calculate player's melee attack bonus."""
    return game._session().character["strength_mod"] + game._session().character["proficiency_bonus"]

def roll_attack():
    """Roll d20 for attack."""
    return game.roll_d20()

def roll_damage(damage_die, damage_dice, ability_mod, *, rolls=None):
    """Roll damage dice."""
    random = game._session().rng
    total = 0
    for _ in range(damage_dice):
        value = random.randint(1, damage_die)
        if rolls is not None:
            rolls.append(value)
        total += value
    return total + ability_mod

def _species_trait_state():
    character = game._session().character
    state = character.get("species_trait_state")
    if not isinstance(state, dict):
        game.initialize_species_trait_state(
            giant_ancestry=character.get("giant_ancestry")
        )
        state = character.get("species_trait_state")
    if not isinstance(state, dict):
        # Non-trait species need neutral mechanics defaults without persisting
        # new state that would change their legacy save representation.
        state = game._new_species_trait_state(
            character.get("species", character.get("race")),
            character.get("proficiency_bonus", 2),
        )
    species = character.get("species", character.get("race"))
    if species not in game.SPECIES_WITH_TRAIT_STATE:
        temporary_hit_points = character.get(
            "temporary_hit_points",
            state.get("temporary_hit_points", 0),
        )
        if type(temporary_hit_points) is not int or temporary_hit_points < 0:
            raise ValueError("Temporary Hit Points state is invalid.")
        state["temporary_hit_points"] = temporary_hit_points
    return state

def roll_initiative(dex_mod=0):
    """Roll initiative: d20 + dexterity modifier."""
    return game.roll_d20() + dex_mod

def roll_initiative_npc():
    """Roll initiative for NPC (default modifier 0)."""
    return game.roll_d20()

def roll_initiative_player():
    """Roll initiative for player."""
    return game.roll_initiative(game._session().character["dexterity_mod"])

def perform_skill_check(
    skill, dc, modifiers, proficient_skills, proficiency_bonus,
    advantage=False, disadvantage=False, expertise_skills=None,
    check_feature=None, check_evidence=None,
):
    if check_feature is None:
        return game._perform_skill_check(skill, dc, modifiers, proficient_skills, proficiency_bonus,
                                    advantage, disadvantage, expertise_skills)
    if check_evidence is not None and type(check_evidence) is not list:
        raise ValueError('Check evidence must be a caller-owned list.')
    snapshot = game._session()._capture_runtime_snapshot()
    evidence = []
    try:
        result = game._perform_skill_check(skill, dc, modifiers, proficient_skills, proficiency_bonus,
                                      advantage, disadvantage, expertise_skills,
                                      check_feature=check_feature, check_evidence=evidence)
    except Exception:
        game._session()._restore_runtime_snapshot(snapshot)
        raise
    if check_evidence is not None:
        check_evidence.extend(evidence)
    return result
