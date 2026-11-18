import game


def run(input_fn, print_fn):
    """Run the terminal game on the engine that is already imported; return the process exit code."""
    if not game.start_terminal_game(input_fn=input_fn, print_fn=print_fn):
        return 0
    print_fn("\nMacera başlıyor...\n")


# ---------------------------------------------------------
# ANA OYUN DÖNGÜSÜ
# ---------------------------------------------------------

    while True:

        player_input = input_fn("Sen: ").strip()


        # -----------------------------------------------------
        # BOŞ INPUT
        # -----------------------------------------------------

        if not player_input:

            continue


        command = player_input.lower()

        if command.split(maxsplit=1)[0] in ("/save", "/kaydet", "/load", "/yükle"):
            parts = player_input.split(maxsplit=1)
            save_path = parts[1] if len(parts) == 2 else game.DEFAULT_SAVE_PATH
            try:
                if parts[0].lower() in ("/save", "/kaydet"):
                    game.save_game(save_path)
                    print_fn(f"Oyun kaydedildi: {save_path}")
                else:
                    game.load_game(save_path)
                    print_fn(f"Oyun yüklendi: {save_path}")
            except (OSError, ValueError, TypeError) as error:
                print_fn(f"Kayıt işlemi başarısız: {error}")
            continue


        # -----------------------------------------------------
        # ÇIKIŞ
        # -----------------------------------------------------

        if command == "çık" or command == "exit":

            print_fn("\nOyun kapatılıyor...")

            break


        # -----------------------------------------------------
        # NORMAL D20
        # -----------------------------------------------------

        if command == "zar at":

            dice = game.roll_d20()

            print_fn()
            print_fn("🎲 D20 sonucu:", dice)
            print_fn()

            continue


        # -----------------------------------------------------
        # MANUEL SKILL
        # -----------------------------------------------------

        if command.startswith("/skill"):

            parts = command.split()

            if len(parts) != 3:

                print_fn()
                print_fn("❌ Kullanım:")
                print_fn("/skill stealth 15")
                print_fn()

                continue


            skill_name_input = parts[1]


            try:

                dc = int(parts[2])

            except ValueError:

                print_fn()
                print_fn("❌ DC bir sayı olmalı.")
                print_fn()

                continue


            matched_skill = None

            for skill in game.SKILLS:

                if skill.lower() == skill_name_input:

                    matched_skill = skill

                    break


            if matched_skill is None:

                print_fn()
                print_fn("❌ Geçersiz skill.")
                print_fn()

                continue


            character = game._session().character
            result = game.perform_skill_check(
                matched_skill,
                dc,
                character["modifiers"],
                character["proficient_skills"],
                character["proficiency_bonus"]
            )


            print_fn()
            print_fn("=" * 35)
            print_fn("🎲 SKILL CHECK")
            print_fn("=" * 35)

            print_fn("Skill:", result["skill"])
            print_fn("Ability:", result["ability"].upper())
            print_fn("D20:", result["dice"])

            print_fn(
                "Ability Modifier:",
                f"+{result['modifier']}"
                if result["modifier"] >= 0
                else result["modifier"]
            )

            print_fn(
                "Proficiency:",
                f"+{result['proficiency_bonus']}"
            )

            print_fn(
                "Proficient:",
                "EVET"
                if result["proficient"]
                else "HAYIR"
            )

            print_fn(
                "Toplam Bonus:",
                f"+{result['total_bonus']}"
                if result["total_bonus"] >= 0
                else result["total_bonus"]
            )

            print_fn("Toplam:", result["total"])
            print_fn("DC:", result["dc"])
            print_fn("Sonuç:", result["result"])

            print_fn("=" * 35)
            print_fn()

            continue


        # -----------------------------------------------------
        turn_result = game.run_player_turn(player_input, game.messages)
        print_fn()
        print_fn("Dungeon Master:")
        print_fn(turn_result["narration"])
        print_fn()
    return 0
