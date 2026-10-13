"""Bounded spell contracts; no deferred capability is represented as supported."""
import copy
import unittest
import uuid
from unittest.mock import call, patch

from api.tests import test_death_system as fixtures
from api.tests import test_campaign_api as campaign_fixtures
from api.main import create_app
import httpx
from api.session_manager import SessionManager
from api.persistence.campaign_store import CampaignStore
from api.character_creation import configure_character
from api.dnd_2024_rules import CLASS_DEFINITIONS, SPELLS_CATALOG
import action_economy
import bounded_encounter
import game
import spell_scope


from api.auth import FixedAuthenticator
from api.tests.auth_fixture import TEST_PLAYER
def caster(session=None, cls="Sorcerer"):
    s = session or fixtures.make_session()
    s.character.update({"class": cls, "level": 1, "proficiency_bonus": 2,
                        "charisma": 16, "intelligence": 16, "wisdom": 16})
    catalog = SPELLS_CATALOG[cls]
    definition = CLASS_DEFINITIONS[cls]
    s.character["cantrips"] = [v["id"] for v in catalog["cantrips"]][:definition["cantrips_count"]]
    s.character["spells"] = [v["id"] for v in catalog["spells_level_1"]][:definition["spells_count"]]
    if cls == "Sorcerer":
        s.character["spells"] = ["Magic Missile", "Shield"]
    if cls == "Bard":
        s.character["spells"] = ["Cure Wounds", *[v["id"] for v in catalog["spells_level_1"] if v["id"] != "Cure Wounds"][:3]]
    spell_scope.initialize(s)
    if s.world_state.get("combat", {}).get("active"):
        s.end_combat("fixture_setup")
    s.world_state["npcs"] = [n for n in s.world_state["npcs"] if n["id"] != "death-save-enemy"]
    fixtures.start_test_combat(s)
    enemy = s.world_state["npcs"][-1]
    enemy.update(current_hp=100, max_hp=100, distance_ft=30,
                 monster_stat_block=copy.deepcopy(bounded_encounter.COMMONER))
    s.world_state["equipment"] = {"main_hand": None, "off_hand": None}
    s.world_state["attack_environment"] = {"pairs": {
        "player|" + enemy["id"]: {"distance_ft": 30, "attacker_sees_target": True,
                                  "target_sees_attacker": True, "cover": "none"},
    }}
    s.ensure_combat_state()
    return s, enemy


class SpellEngineTests(unittest.TestCase):
    def test_creation_records_only_selected_access(self):
        for seed in range(20):
            s = game.GameSession(seed=seed)
            configure_character(s, mode="random")
            if "spellcasting_v1" in s.world_state:
                break
        state = s.world_state["spellcasting_v1"]
        self.assertEqual(state["cantrips"], s.character["cantrips"])
        self.assertEqual(state["prepared"], [] if s.character["class"] in {"Wizard", "Cleric", "Druid"} else s.character["spells"])
        self.assertEqual(state["slots"], CLASS_DEFINITIONS[s.character["class"]]["spell_slots"])
        spell_scope.validate(state, s.character)

    def test_fire_bolt_hit_miss_critical_modifier_and_no_slot(self):
        for d20, damage, count in ((12, 4, 1), (1, 0, 0), (20, 8, 2)):
            with self.subTest(d20=d20):
                s, e = caster()
                with patch("game.roll_d20", return_value=d20), patch.object(s.rng, "randint", return_value=4) as dice:
                    result = spell_scope.cast(s, "Fire Bolt", e["id"])
                self.assertEqual(result["spell_attack_modifier"], 5)
                self.assertEqual(result["resolution"]["total_modifier"], 5)
                self.assertEqual(result["damage"], damage)
                self.assertEqual(dice.call_count, count)
                self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 2})
                self.assertTrue(action_economy.ensure(s)["player"]["base_action_spent"])

    def test_cantrip_scaling_at_source_thresholds(self):
        for level, count in ((4, 1), (5, 2), (11, 3), (17, 4)):
            for cls, spell, d20 in (("Sorcerer", "Fire Bolt", 12), ("Cleric", "Sacred Flame", 1)):
                with self.subTest(level=level, spell=spell):
                    s, e = caster(cls=cls)
                    s.character.update(level=level, proficiency_bonus=2 + (level - 1) // 4)
                    with patch("game.roll_d20", return_value=d20), patch.object(s.rng, "randint", return_value=1) as dice:
                        result = spell_scope.cast(s, spell, e["id"])
                    self.assertEqual(result["damage"], count)
                    self.assertEqual(dice.call_count, count)

    def test_sacred_flame_save_and_cover_exception(self):
        for d20, damage in ((20, 0), (1, 3)):
            s, e = caster(cls="Cleric")
            s.world_state["attack_environment"]["pairs"]["player|" + e["id"]]["cover"] = "three_quarters"
            with patch("game.roll_d20", return_value=d20), patch.object(s.rng, "randint", return_value=3) as dice:
                result = spell_scope.cast(s, "Sacred Flame", e["id"])
            self.assertEqual(result["spell_save_dc"], 13)
            self.assertEqual(result["resolution"]["dc"], 13)
            self.assertEqual(result["resolution"]["total_modifier"], 0)
            self.assertEqual(result["damage"], damage)
            self.assertEqual(dice.call_count, 1 if damage else 0)

    def test_magic_missile_auto_hit_and_single_damage_handoff(self):
        s, e = caster()
        with patch("game.roll_d20", side_effect=AssertionError("No MM attack/save roll")), patch(
            "game.apply_npc_damage", wraps=game.apply_npc_damage
        ) as owner, patch.object(s.rng, "randint", return_value=2) as dice:
            result = spell_scope.cast(s, "Magic Missile", e["id"])
        self.assertEqual(result["darts"], [3, 3, 3])
        self.assertEqual(result["damage"], 9)
        self.assertEqual(e["current_hp"], 91)
        self.assertEqual(dice.call_args_list, [call(1, 4)] * 3)
        self.assertEqual(owner.call_count, 1)
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 1})

    def test_damage_mitigation_and_policy_a(self):
        for spell, cls, die in (("Fire Bolt", "Sorcerer", 12),
                                ("Sacred Flame", "Cleric", 1),
                                ("Magic Missile", "Sorcerer", 12)):
            s, e = caster(cls=cls)
            e.update(current_hp=1, max_hp=1)
            with patch("game.roll_d20", return_value=die), patch("game.apply_npc_damage", wraps=game.apply_npc_damage) as owner:
                result = spell_scope.cast(s, spell, e["id"])
            self.assertGreater(result["damage"], 0)
            self.assertEqual(owner.call_count, 1)
            self.assertEqual(e["combat_status"], "dead")
            self.assertFalse(s.world_state["combat"]["active"])
        s, e = caster()
        e["resistances"] = ["force"]
        with patch.object(s.rng, "randint", return_value=2):
            result = spell_scope.cast(s, "Magic Missile", e["id"])
        self.assertEqual(result["damage"], 3)  # Each simultaneous 3-damage dart halves to 1.

    def test_healing_uses_existing_owner_and_hp_cap(self):
        s, _ = caster(cls="Bard")
        s.character["current_hp"] = 1
        with patch("game.heal_player", wraps=game.heal_player) as owner, patch.object(s.rng, "randint", return_value=8) as dice:
            result = spell_scope.cast(s, "Cure Wounds", "player")
        self.assertEqual(result["rolled_healing"], 19)
        self.assertEqual(result["healing"], s.character["max_hp"] - 1)
        self.assertEqual(s.character["current_hp"], s.character["max_hp"])
        self.assertEqual(owner.call_count, 1)
        self.assertEqual(dice.call_args_list, [call(1, 8)] * 2)
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["1"], 1)

    def test_no_slot_cast_rejection_is_atomic(self):
        s, enemy = caster(cls="Sorcerer")
        spell_state = s.world_state["spellcasting_v1"]
        self.assertIn("Magic Missile", spell_state["prepared"])
        self.assertEqual(spell_state["slots"], {"1": 2})

        spell_state["slots"]["1"] = 0
        before_world_state = copy.deepcopy(s.world_state)
        before_character = copy.deepcopy(s.character)
        before_spell_state = copy.deepcopy(spell_state)
        before_rng = s.rng.getstate()

        with self.assertRaises(ValueError) as raised:
            spell_scope.cast(s, "Magic Missile", enemy["id"])

        self.assertEqual(raised.exception.code, "spell_slot_unavailable")
        self.assertEqual(s.world_state, before_world_state)
        self.assertEqual(s.character, before_character)
        self.assertEqual(s.world_state["spellcasting_v1"], before_spell_state)
        self.assertEqual(s.rng.getstate(), before_rng)
        print(
            "F10_BASE_AC002_NO_SLOT "
            "error=spell_slot_unavailable; "
            "level1_slots=0->0; world_state=unchanged; "
            "character=unchanged; spell_state=unchanged; rng=unchanged"
        )

    def test_rejections_are_atomic(self):
        cases = (
            ("unsupported", "Sleep", "enemy", None), ("unprepared", "Magic Missile", "enemy", None),
            ("unknown", "Magic Missile", "forged", None), ("ambiguous", "Magic Missile", None, None),
            ("upcast", "Magic Missile", "enemy", 2), ("range", "Magic Missile", "enemy", None),
            ("invisible", "Magic Missile", "enemy", None), ("total_cover", "Magic Missile", "enemy", None),
            ("components", "Magic Missile", "enemy", None), ("no_slots", "Magic Missile", "enemy", None),
            ("out_of_turn", "Magic Missile", "enemy", None), ("action", "Magic Missile", "enemy", None),
            ("inactive", "Magic Missile", "enemy", None), ("object", "Fire Bolt", "object", None),
            ("point_blank", "Fire Bolt", "enemy", None), ("poisoned", "Fire Bolt", "enemy", None),
            ("wizard_preparation", "Magic Missile", "enemy", None),
            ("legacy_access", "Magic Missile", "enemy", None),
        )
        for mode, spell, target, slot in cases:
            with self.subTest(mode=mode):
                s, e = caster(cls="Wizard" if mode == "wizard_preparation" else "Sorcerer")
                pair = s.world_state["attack_environment"]["pairs"]["player|" + e["id"]]
                state = s.world_state["spellcasting_v1"]
                if mode == "unprepared": state["prepared"] = ["Shield"]
                if mode == "range": pair["distance_ft"] = 121
                if mode == "invisible": pair["attacker_sees_target"] = False
                if mode == "total_cover": pair["cover"] = "total"
                if mode == "components": s.world_state["equipment"] = {"main_hand": "longsword", "off_hand": "shield"}
                if mode == "no_slots": state["slots"]["1"] = 0
                if mode == "out_of_turn":
                    s.world_state["combat"]["current_turn_index"] = s.world_state["combat"]["initiative_order"].index(e["id"])
                    s.world_state["combat"]["current_actor_id"] = e["id"]
                if mode == "action": action_economy.consume_action(s, "player", "magic")
                if mode == "inactive": s.end_combat("test")
                if mode == "point_blank": pair["distance_ft"] = 5
                if mode == "poisoned": s.character["conditions"] = ["poisoned"]
                if mode == "legacy_access": s.world_state.pop("spellcasting_v1")
                before = copy.deepcopy(s.world_state), copy.deepcopy(s.character), s.rng.getstate()
                with self.assertRaises(ValueError):
                    spell_scope.cast(s, spell, e["id"] if target == "enemy" else target, slot)
                self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

    def test_zero_hp_and_dead_self_cannot_cast_or_resurrect(self):
        for dead in (False, True):
            s, _ = caster(cls="Bard")
            s.ensure_death_state()["mode"] = "PERMADEATH"
            s._apply_player_damage(s.character["current_hp"], took_damage=True)
            if dead: s.set_player_max_hp(0)
            before = copy.deepcopy(s.world_state), copy.deepcopy(s.character), s.rng.getstate()
            with self.assertRaises(ValueError):
                spell_scope.cast(s, "Cure Wounds", "player")
            self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

    def test_one_slot_per_turn_even_with_additional_magic_action(self):
        s, e = caster()
        spell_scope.cast(s, "Magic Missile", e["id"])
        action_economy.grant(s, "player", "test_additional_magic", ["magic"])
        before = copy.deepcopy(s.world_state), s.rng.getstate()
        with self.assertRaisesRegex(ValueError, "Only one spell slot"):
            spell_scope.cast(s, "Magic Missile", e["id"])
        self.assertEqual((s.world_state, s.rng.getstate()), before)

    def test_rest_slot_recovery_and_invalid_saved_state(self):
        s, e = caster()
        spell_scope.cast(s, "Magic Missile", e["id"])
        marker = copy.deepcopy(s.world_state["spellcasting_v1"]["slot_turn"])
        spell_scope.restore_slots(s)
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["1"], 2)
        self.assertEqual(s.world_state["spellcasting_v1"]["slot_turn"], marker)
        payload = s.serialize_game_state()
        payload["world_state"]["spellcasting_v1"]["slots"]["1"] = 3
        with self.assertRaisesRegex(ValueError, "Invalid saved spell slots"): game._validate_save_payload(payload)

    def test_no_target_invention_or_unsupported_mode_from_prose(self):
        for text in ("I cast Magic Missile and split darts", "I upcast Magic Missile", "I cast Sleep",
                     "I cast Fire Bolt at an object", "I cast Magic Missile at goblin and orc",
                     "I cast Magic Missile without a slot"):
            with self.assertRaises(ValueError): spell_scope.natural_command(text, "npc")
        self.assertIsNone(spell_scope.natural_command("What is Fire Bolt?", "npc"))
        self.assertIsNone(spell_scope.natural_command("Can I cast Fire Bolt?", "npc"))
        proposal = spell_scope.natural_command("I cast Fire Bolt at the goblin", None)
        self.assertIsNone(proposal["steps"][0]["target_id"])

    def test_zero_hp_npc_damage_and_deferred_defenses(self):
        for spell, cls in (("Sacred Flame", "Cleric"), ("Magic Missile", "Sorcerer")):
            s, e = caster(cls=cls)
            e.update(current_hp=0, combat_status="unconscious")
            with patch("game.apply_npc_damage", wraps=game.apply_npc_damage) as owner:
                result = spell_scope.cast(s, spell, e["id"])
            self.assertGreater(result["damage"], 0)
            self.assertEqual(owner.call_count, 1)
            self.assertEqual(e["combat_status"], "dead")
        for mode in ("restrained", "petrified", "magic_resistance", "concentration", "rider", "dodging"):
            s, e = caster(cls="Cleric" if mode != "dodging" else "Sorcerer")
            if mode in {"restrained", "petrified"}: e["conditions"] = [mode]
            if mode == "magic_resistance": e["monster_stat_block"]["traits"] = {"magic_resistance": True}
            if mode == "concentration": e["concentration"] = {"spell_id": "deferred"}
            if mode == "rider":
                s.character.update(race="Aasimar", species="Aasimar")
                s.character["species_trait_state"] = game._new_persisted_species_trait_state("Aasimar", 2)
                s.character["species_trait_state"].update(
                    celestial_revelation_turns_remaining=1, celestial_revelation_form="inner_radiance",
                )
            if mode == "dodging": action_economy.ensure(s)[e["id"]]["dodging"] = True
            before = copy.deepcopy(s.world_state), copy.deepcopy(s.character), s.rng.getstate()
            with self.assertRaises(ValueError):
                spell_scope.cast(s, "Fire Bolt" if mode == "dodging" else "Sacred Flame", e["id"])
            self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)


class SpellApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaign_fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_fixtures.CampaignApiTests.asyncTearDown
    create_campaign = campaign_fixtures.CampaignApiTests.create_campaign

    async def test_http_replay_save_restart_and_isolation_zero_models(self):
        for cls, spell, roll in (("Sorcerer", "Fire Bolt", 12), ("Sorcerer", "Magic Missile", 12),
                                 ("Cleric", "Sacred Flame", 1), ("Bard", "Cure Wounds", 12)):
            with self.subTest(spell=spell):
                a, b = await self.create_campaign(), await self.create_campaign()
                s, e = caster(self.manager.get(a["session_id"]).game_session, cls)
                other = self.manager.get(b["session_id"]).game_session
                isolated = other.serialize_game_state(), other.rng.getstate()
                if spell == "Cure Wounds": s.character["current_hp"] = 1
                target = "player" if spell == "Cure Wounds" else e["id"]
                combat = s.world_state["combat"]
                request = {"message": "Canonical spell only.", "action_id": str(uuid.uuid4()),
                           "combat_id": combat["combat_id"], "combat_round": combat["round"],
                           "combat_turn_index": combat["current_turn_index"],
                           "combat_action": {"steps": [{"kind": "magic", "ability": spell, "target_id": target}]}}
                self.app.state.ollama_adapter = None
                url = f"/api/game/sessions/{a['session_id']}/turn"
                with patch("game.roll_d20", return_value=roll) as d20, patch.object(s.rng, "randint", wraps=s.rng.randint) as damage:
                    first = await self.http.post(url, json=request)
                    self.assertEqual(first.status_code, 200, first.text)
                    calls = d20.call_count, damage.call_count
                    before = s.serialize_game_state(), s.rng.getstate(), self.store.get_campaign(a["campaign_id"])
                    retry = await self.http.post(url, json=request)
                    self.assertEqual(retry.json(), first.json())
                    self.assertEqual((d20.call_count, damage.call_count), calls)
                    self.assertEqual((s.serialize_game_state(), s.rng.getstate(), self.store.get_campaign(a["campaign_id"])), before)
                self.assertEqual((other.serialize_game_state(), other.rng.getstate()), isolated)
                manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
                sid, record, *_ = manager.resume_campaign(a["campaign_id"])
                restored = record.game_session
                self.assertEqual(restored.world_state["spellcasting_v1"], s.world_state["spellcasting_v1"])
                self.assertEqual(restored.rng.getstate(), s.rng.getstate())
                restarted_app = create_app(session_manager=manager, authenticator=FixedAuthenticator(TEST_PLAYER))
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted_app), base_url="http://testserver") as restarted_http:
                    replay = await restarted_http.post(f"/api/game/sessions/{sid}/turn", json=request)
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(replay.json()["combat_result"], first.json()["combat_result"])
                after_resume = restored.serialize_game_state(), restored.rng.getstate(), self.store.get_campaign(a["campaign_id"])
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted_app), base_url="http://testserver") as restarted_http:
                    again = await restarted_http.post(f"/api/game/sessions/{sid}/turn", json=request)
                self.assertEqual(again.json(), replay.json())
                self.assertEqual((restored.serialize_game_state(), restored.rng.getstate(), self.store.get_campaign(a["campaign_id"])), after_resume)

    async def test_http_prose_is_not_mechanical_authority_and_rejections_do_not_persist(self):
        a = await self.create_campaign()
        s, e = caster(self.manager.get(a["session_id"]).game_session)
        self.app.state.ollama_adapter = None
        url = f"/api/game/sessions/{a['session_id']}/turn"
        for message, target in (("I cast Fire Bolt for 9999 damage", e["id"]),
                                ("I cast Magic Missile and split darts", e["id"]),
                                ("I cast Fire Bolt at a goblin", None)):
            if "9999" in message:
                with patch("game.roll_d20", return_value=1):
                    r = await self.http.post(url, json={"message": message, "target_id": target, "action_id": str(uuid.uuid4())})
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(e["current_hp"], 100)
                # Start the next test on a fresh authoritative player turn.
                s, e = caster(s)
            else:
                before = s.serialize_game_state(), s.rng.getstate(), self.store.get_campaign(a["campaign_id"])
                r = await self.http.post(url, json={"message": message, "target_id": target, "action_id": str(uuid.uuid4())})
                self.assertEqual(r.status_code, 400, r.text)
                self.assertEqual((s.serialize_game_state(), s.rng.getstate(), self.store.get_campaign(a["campaign_id"])), before)
