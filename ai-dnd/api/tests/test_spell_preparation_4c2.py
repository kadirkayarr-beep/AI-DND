"""4C.2: spell preparation window; `spellcasting_v1` state version 1 -> 2 (`spellbook`, `prepare_window`).

Every new saved key: validated on load, inside the Undo snapshot, replay-safe; an old version-1 save loads into
version 2 and behaves as before (the migration never chooses a spell).
"""
import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx

import campaign_time
import game
import spell_preparation
import spell_scope
from api.auth import FixedAuthenticator
from api.dnd_2024_rules import CLASS_DEFINITIONS, SPELLS_CATALOG
from api.main import _capture_session, _restore_session, create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api as campaign_fixtures
from api.tests import test_death_system as fixtures
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_time import scene
from api.tests.test_spell_scope import caster
from api.tests.town_seed import fixed_town

BOOK = ["Magic Missile", "Shield", "Mage Armor", "Detect Magic", "Sleep", "Burning Hands"]


def prepper(cls="Wizard", session=None):
    """A level-1 caster created through the real initializer, out of combat, in a tavern with a started clock."""
    s = session or scene()
    s.character.update({"class": cls, "level": 1, "proficiency_bonus": 2,
                        "charisma": 16, "intelligence": 16, "wisdom": 16})
    catalog, definition = SPELLS_CATALOG[cls], CLASS_DEFINITIONS[cls]
    s.character["cantrips"] = [v["id"] for v in catalog["cantrips"]][:definition["cantrips_count"]]
    s.character["spells"] = [v["id"] for v in catalog["spells_level_1"]][:definition["spells_count"]]
    if cls == "Sorcerer":
        s.character["spells"] = ["Magic Missile", "Shield"]
    if s.world_state.get("combat", {}).get("active"):
        s.end_combat("fixture_setup")
    spell_scope.initialize(s)
    return s


def now(s):
    return s.world_state.get("campaign_time", {}).get("elapsed_seconds", 0)


def v1_of(state):
    """The exact shape the pre-4C.2 initializer wrote."""
    return {key: copy.deepcopy(state[key]) for key in ("class", "cantrips", "prepared", "slots", "slot_turn")} | {"version": 1}


class CreationAndShape(unittest.TestCase):
    def test_creation_writes_version_two(self):
        w = prepper("Wizard")
        state = w.world_state["spellcasting_v1"]
        self.assertEqual(state["version"], 2)
        self.assertEqual(state["spellbook"], BOOK)
        self.assertEqual(state["prepared"], [])
        self.assertEqual(state["prepare_window"], {"opened_second": now(w), "reason": "creation"})
        c = prepper("Cleric")
        self.assertEqual((c.world_state["spellcasting_v1"]["spellbook"], c.world_state["spellcasting_v1"]["prepare_window"]),
                         (None, {"opened_second": now(c), "reason": "creation"}))
        for cls in ("Sorcerer", "Bard", "Druid"):
            with self.subTest(cls=cls):
                state = prepper(cls).world_state["spellcasting_v1"]
                self.assertEqual((state["version"], state["spellbook"], state["prepare_window"]), (2, None, None))
        self.assertEqual(prepper("Sorcerer").world_state["spellcasting_v1"]["prepared"], ["Magic Missile", "Shield"])

    def test_validate_rejects_every_malformed_new_key(self):
        w = prepper("Wizard")
        good = w.world_state["spellcasting_v1"]
        spell_scope.validate(good, w.character)
        bad = {
            "missing spellbook": {k: v for k, v in good.items() if k != "spellbook"},
            "missing window": {k: v for k, v in good.items() if k != "prepare_window"},
            "extra key": {**good, "concentration": None},
            "v1 keys under version 2": v1_of(good) | {"version": 2},
            "v2 keys under version 1": {**good, "version": 1},
            "version 3": {**good, "version": 3},
            "spellbook not a list": {**good, "spellbook": "Magic Missile"},
            "spellbook unknown spell": {**good, "spellbook": [*BOOK[:5], "Cure Wounds"]},
            "spellbook duplicate": {**good, "spellbook": [*BOOK[:5], "Shield"]},
            "spellbook non-string": {**good, "spellbook": [*BOOK[:5], 7]},
            "prepared outside spellbook": {**good, "spellbook": BOOK[:5], "prepared": ["Burning Hands"]},
            "prepared over the limit": {**good, "spellbook": BOOK, "prepared": BOOK[:5]},
            "window not a dict": {**good, "prepare_window": 5},
            "window extra key": {**good, "prepare_window": {"opened_second": 0, "reason": "creation", "x": 1}},
            "window bad reason": {**good, "prepare_window": {"opened_second": 0, "reason": "short_rest"}},
            "window negative second": {**good, "prepare_window": {"opened_second": -1, "reason": "creation"}},
            "window bool second": {**good, "prepare_window": {"opened_second": True, "reason": "creation"}},
        }
        for name, state in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                spell_scope.validate(state, w.character)
        c = prepper("Cleric")
        cleric = c.world_state["spellcasting_v1"]
        for name, state in {"cleric spellbook": {**cleric, "spellbook": []},
                            "cleric prepared outside class list": {**cleric, "prepared": ["Magic Missile"]}}.items():
            with self.subTest(name), self.assertRaises(ValueError):
                spell_scope.validate(state, c.character)
        s = prepper("Sorcerer")
        sorcerer = s.world_state["spellcasting_v1"]
        for name, state in {"sorcerer spellbook": {**sorcerer, "spellbook": ["Magic Missile"]},
                            "sorcerer window": {**sorcerer, "prepare_window": {"opened_second": 0, "reason": "long_rest"}}}.items():
            with self.subTest(name), self.assertRaises(ValueError):
                spell_scope.validate(state, s.character)

    def test_version_one_is_still_read_exactly_as_before(self):
        for cls in ("Wizard", "Cleric", "Sorcerer"):
            with self.subTest(cls=cls):
                s = prepper(cls)
                old = v1_of(s.world_state["spellcasting_v1"])
                spell_scope.validate(old, s.character)
        w = prepper("Wizard")
        with self.assertRaises(ValueError):  # version 1 never allowed a Wizard prepared list; it still does not
            spell_scope.validate(v1_of(w.world_state["spellcasting_v1"]) | {"prepared": ["Magic Missile"]}, w.character)


class PrepareWindow(unittest.TestCase):
    def test_window_is_open_at_creation_and_closes_when_the_clock_moves(self):
        w = prepper("Wizard")
        self.assertTrue(spell_preparation.window_open(w))
        w.advance_campaign_time(60, "wait")
        self.assertFalse(spell_preparation.window_open(w))
        with self.assertRaises(ValueError):
            spell_preparation.prepare(w, ["Magic Missile"])
        self.assertEqual(w.world_state["spellcasting_v1"]["prepared"], [])

    def test_combat_start_closes_the_window_for_good(self):
        w = prepper("Wizard")
        fixtures.start_test_combat(w)
        self.assertIsNone(w.world_state["spellcasting_v1"]["prepare_window"])
        self.assertFalse(spell_preparation.window_open(w))
        w.end_combat("test")
        self.assertFalse(spell_preparation.window_open(w))

    def test_prepare_keeps_the_valid_ones_and_names_why_the_rest_fell(self):
        w = prepper("Wizard")
        before = copy.deepcopy(w.world_state["spellcasting_v1"])
        result = spell_preparation.prepare(w, ["Magic Missile", "Cure Wounds", "Shield", "Magic Missile", "Fire Bolt"])
        self.assertEqual(result["status"], "prepared")
        self.assertEqual(result["prepared"], ["Magic Missile", "Shield"])
        self.assertEqual(result["dropped"], [{"spell_id": "Cure Wounds", "reason": "not_in_spellbook"},
                                             {"spell_id": "Magic Missile", "reason": "duplicate"},
                                             {"spell_id": "Fire Bolt", "reason": "cantrip"}])
        self.assertEqual((result["limit"], result["open"]), (4, True))
        state = w.world_state["spellcasting_v1"]
        self.assertEqual(state, {**before, "prepared": ["Magic Missile", "Shield"]})
        c = prepper("Cleric")
        result = spell_preparation.prepare(c, ["Cure Wounds", "Magic Missile", "Bless"])
        self.assertEqual(result["prepared"], ["Cure Wounds", "Bless"])
        self.assertEqual(result["dropped"], [{"spell_id": "Magic Missile", "reason": "not_on_class_list"}])

    def test_too_many_saves_nothing_and_asks(self):
        w = prepper("Wizard")
        before = copy.deepcopy(w.world_state)
        result = spell_preparation.prepare(w, BOOK[:5])
        self.assertEqual((result["status"], result["limit"], result["excess"]), ("too_many", 4, 1))
        self.assertIn("Hangisini bırakıyorsun?", result["message"])
        self.assertEqual(w.world_state, before)

    def test_fewer_than_the_limit_is_kept_with_a_note(self):
        w = prepper("Wizard")
        result = spell_preparation.prepare(w, ["Shield"])
        self.assertEqual((result["status"], result["prepared"]), ("prepared", ["Shield"]))
        self.assertIn("3", result["message"])

    def test_close_ends_the_window_and_the_same_request_is_idempotent(self):
        w = prepper("Wizard")
        first = spell_preparation.prepare(w, ["Magic Missile"])
        state = copy.deepcopy(w.world_state["spellcasting_v1"])
        self.assertEqual(spell_preparation.prepare(w, ["Magic Missile"]), first)
        self.assertEqual(w.world_state["spellcasting_v1"], state)
        closed = spell_preparation.prepare(w, ["Magic Missile"], close=True)
        self.assertEqual((closed["open"], w.world_state["spellcasting_v1"]["prepare_window"]), (False, None))
        with self.assertRaises(ValueError):
            spell_preparation.prepare(w, ["Shield"])

    def test_classes_that_do_not_prepare_are_refused_without_a_change(self):
        for cls in ("Sorcerer", "Druid", "Bard"):
            with self.subTest(cls=cls):
                s = prepper(cls)
                before = copy.deepcopy(s.world_state)
                with self.assertRaises(ValueError):
                    spell_preparation.prepare(s, ["Cure Wounds"])
                self.assertEqual(s.world_state, before)
                self.assertFalse(spell_preparation.view(s)["supported"])

    def test_a_prepared_spell_can_be_cast_and_an_unprepared_one_cannot(self):
        s, e = caster(cls="Wizard")
        with self.assertRaises(ValueError):
            spell_scope.cast(s, "Magic Missile", e["id"])
        w = prepper("Wizard")
        spell_preparation.prepare(w, ["Magic Missile"])
        with patch.object(spell_scope, "initialize"):  # keep the state the window saved; caster() only sets the fight
            s, e = caster(session=w, cls="Wizard")
        self.assertEqual(s.world_state["spellcasting_v1"]["prepared"], ["Magic Missile"])
        result = spell_scope.cast(s, "Magic Missile", e["id"])
        self.assertGreater(result["damage"], 0)
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 1})

    def test_long_rest_opens_the_window_only_for_preparing_classes(self):
        w = prepper("Wizard")
        spell_preparation.prepare(w, ["Shield"], close=True)
        w.resolve_species_trait_action("long_rest")
        self.assertEqual(w.world_state["spellcasting_v1"]["prepare_window"],
                         {"opened_second": now(w), "reason": "long_rest"})
        self.assertTrue(spell_preparation.window_open(w))
        self.assertEqual(w.world_state["spellcasting_v1"]["prepared"], ["Shield"])  # a rest never chooses
        s = prepper("Sorcerer")
        s.resolve_species_trait_action("long_rest")
        self.assertIsNone(s.world_state["spellcasting_v1"]["prepare_window"])

    def test_a_wizard_long_rest_changes_only_the_window_in_the_spell_state(self):
        w = prepper("Wizard")
        spell_preparation.prepare(w, ["Shield"], close=True)
        w.world_state["spellcasting_v1"]["slots"] = {"1": 0}
        before = copy.deepcopy(w.world_state["spellcasting_v1"])
        w.resolve_species_trait_action("long_rest")
        self.assertEqual(w.world_state["spellcasting_v1"], {
            **before, "slots": {"1": 2}, "prepare_window": {"opened_second": now(w), "reason": "long_rest"}})

    def test_short_rest_does_not_open_the_window(self):
        w = prepper("Wizard")
        spell_preparation.prepare(w, [], close=True)
        w.resolve_species_trait_action("short_rest")
        self.assertIsNone(w.world_state["spellcasting_v1"]["prepare_window"])

    def test_view_lists_candidates_and_limit(self):
        w = prepper("Wizard")
        view = spell_preparation.view(w)
        self.assertEqual(view, {"supported": True, "class_name": "Wizard", "open": True, "reason": "creation",
                                "limit": 4, "candidates": BOOK, "prepared": [], "spellbook": BOOK})
        c = prepper("Cleric")
        self.assertEqual(spell_preparation.view(c)["candidates"], [s["id"] for s in SPELLS_CATALOG["Cleric"]["spells_level_1"]])


class SaveUndoReplay(unittest.TestCase):
    def save_and_load(self, s):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "save.json"
            s.save_game(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            fresh = game.GameSession()
            fresh.load_game(path)
        return payload, fresh

    def test_save_then_load_is_equal(self):
        for cls in ("Wizard", "Cleric", "Sorcerer"):
            with self.subTest(cls=cls):
                s = prepper(cls)
                if cls != "Sorcerer":
                    spell_preparation.prepare(s, spell_preparation.view(s)["candidates"][:2])
                payload, fresh = self.save_and_load(s)
                self.assertEqual(payload["world_state"]["spellcasting_v1"], s.world_state["spellcasting_v1"])
                self.assertEqual(fresh.world_state["spellcasting_v1"], s.world_state["spellcasting_v1"])
                self.assertEqual(fresh.serialize_game_state(), s.serialize_game_state())

    def test_a_tampered_new_key_fails_the_load_and_leaves_the_session(self):
        s = prepper("Wizard")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "save.json"
            s.save_game(path)
            for field, value in (("spellbook", ["Cure Wounds"]), ("prepare_window", {"opened_second": "x", "reason": "creation"})):
                with self.subTest(field=field):
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload["world_state"]["spellcasting_v1"][field] = value
                    bad = Path(folder) / "bad.json"
                    bad.write_text(json.dumps(payload), encoding="utf-8")
                    other = prepper("Sorcerer")
                    before = other.serialize_game_state()
                    with self.assertRaises(ValueError):
                        other.load_game(bad)
                    self.assertEqual(other.serialize_game_state(), before)

    def test_undo_snapshot_restores_the_window_and_the_prepared_list(self):
        w = prepper("Wizard")
        spell_preparation.prepare(w, ["Shield"], close=True)
        w.advance_campaign_time(16 * 3600, "wait")
        snapshot = _capture_session(w)
        before = copy.deepcopy(w.world_state["spellcasting_v1"])
        w.resolve_species_trait_action("long_rest")
        spell_preparation.prepare(w, ["Magic Missile", "Sleep"])
        self.assertNotEqual(w.world_state["spellcasting_v1"], before)
        _restore_session(w, snapshot)
        self.assertEqual(w.world_state["spellcasting_v1"], before)
        self.assertFalse(spell_preparation.window_open(w))

    def test_undo_snapshot_restores_the_window_combat_closed(self):
        w = prepper("Wizard")
        snapshot = _capture_session(w)
        before = copy.deepcopy(w.world_state["spellcasting_v1"])
        fixtures.start_test_combat(w)
        self.assertIsNone(w.world_state["spellcasting_v1"]["prepare_window"])
        _restore_session(w, snapshot)
        self.assertEqual(w.world_state["spellcasting_v1"], before)


class OldSaveMigration(unittest.TestCase):
    def old_save(self, cls, folder):
        """A real version-1 file: today's save with the spell state written in the pre-4C.2 shape."""
        s = prepper(cls)
        path = Path(folder) / f"{cls}.json"
        s.save_game(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["world_state"]["spellcasting_v1"] = v1_of(payload["world_state"]["spellcasting_v1"])
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path, payload

    def test_old_saves_load_into_version_two_without_choosing_spells(self):
        with tempfile.TemporaryDirectory() as folder:
            for cls, spellbook in (("Wizard", BOOK), ("Cleric", None)):
                with self.subTest(cls=cls):
                    path, payload = self.old_save(cls, folder)
                    old = payload["world_state"]["spellcasting_v1"]
                    fresh = game.GameSession()
                    fresh.load_game(path)
                    state = fresh.world_state["spellcasting_v1"]
                    self.assertEqual(state, {**old, "version": 2, "spellbook": spellbook,
                                             "prepare_window": {"opened_second": now(fresh), "reason": "migration"}})
                    self.assertEqual(state["prepared"], [])
                    # loading again from the same old file is deterministic
                    again = game.GameSession()
                    again.load_game(path)
                    self.assertEqual(again.world_state["spellcasting_v1"], state)
                    # the migrated state saves and loads as itself
                    with tempfile.TemporaryDirectory() as inner:
                        resaved = Path(inner) / "resaved.json"
                        fresh.save_game(resaved)
                        third = game.GameSession()
                        third.load_game(resaved)
                        self.assertEqual(third.world_state["spellcasting_v1"], state)

    def test_other_classes_resume_their_old_state_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as folder:
            for cls in ("Sorcerer", "Druid", "Bard"):
                with self.subTest(cls=cls):
                    path, payload = self.old_save(cls, folder)
                    fresh = game.GameSession()
                    fresh.load_game(path)
                    self.assertEqual(fresh.world_state["spellcasting_v1"], payload["world_state"]["spellcasting_v1"])
                    self.assertEqual(fresh.world_state["spellcasting_v1"]["version"], 1)
                    self.assertFalse(spell_preparation.view(fresh)["supported"])
                    self.assertEqual(fresh.world_state["spellcasting_v1"], payload["world_state"]["spellcasting_v1"])

    def test_old_and_migrated_states_cast_identically(self):
        for cls, spell in (("Sorcerer", "Magic Missile"), ("Sorcerer", "Fire Bolt"), ("Wizard", "Fire Bolt"),
                           ("Cleric", "Sacred Flame"), ("Wizard", "Magic Missile"), ("Cleric", "Cure Wounds")):
            with self.subTest(cls=cls, spell=spell):
                results = []
                for shape in ("v1", "migrated"):
                    s, e = caster(cls=cls)
                    s.character["current_hp"] = 1
                    state = s.world_state["spellcasting_v1"]
                    old = v1_of(state)
                    if shape == "v1":
                        s.world_state["spellcasting_v1"] = old
                    else:
                        s.world_state["spellcasting_v1"] = old
                        spell_scope.upgrade(s.world_state, s.character)
                    s.rng.seed(5)
                    target = "player" if spell == "Cure Wounds" else e["id"]
                    with patch("game.roll_d20", return_value=1 if spell == "Sacred Flame" else 12):
                        try:
                            outcome = spell_scope.cast(s, spell, target)
                        except ValueError as error:
                            outcome = ("refused", getattr(error, "code", str(error)))
                    after = {k: copy.deepcopy(s.world_state["spellcasting_v1"][k])
                             for k in ("cantrips", "prepared", "slots", "slot_turn")}
                    if after["slot_turn"]:  # the fight's own random id; round and turn stay compared
                        after["slot_turn"][0] = after["slot_turn"][0] == s.world_state["combat"]["combat_id"]
                    if isinstance(outcome, dict) and isinstance(outcome.get("resolution"), dict):
                        outcome = {**outcome, "resolution": {k: v for k, v in outcome["resolution"].items() if k != "combat_id"}}
                    results.append((outcome, after))
                self.assertEqual(results[0], results[1])

    def test_upgrade_is_idempotent_and_leaves_version_two_alone(self):
        w = prepper("Wizard")
        spell_preparation.prepare(w, ["Shield"])
        state = copy.deepcopy(w.world_state["spellcasting_v1"])
        spell_scope.upgrade(w.world_state, w.character)
        self.assertEqual(w.world_state["spellcasting_v1"], state)
        w.world_state["spellcasting_v1"] = v1_of(state) | {"prepared": []}
        spell_scope.upgrade(w.world_state, w.character)
        once = copy.deepcopy(w.world_state["spellcasting_v1"])
        spell_scope.upgrade(w.world_state, w.character)
        self.assertEqual(w.world_state["spellcasting_v1"], once)

    def test_migration_keeps_only_wizard_spells_the_book_can_hold(self):
        w = prepper("Wizard")
        w.character["spells"] = ["Shield", "Shield", "Cure Wounds", "Sleep"]
        w.world_state["spellcasting_v1"] = v1_of(w.world_state["spellcasting_v1"])
        spell_scope.upgrade(w.world_state, w.character)
        self.assertEqual(w.world_state["spellcasting_v1"]["spellbook"], ["Shield", "Sleep"])
        spell_scope.validate(w.world_state["spellcasting_v1"], w.character)

    def test_migration_during_a_fight_opens_no_window(self):
        s, _ = caster(cls="Cleric")
        s.world_state["spellcasting_v1"] = v1_of(s.world_state["spellcasting_v1"])
        spell_scope.upgrade(s.world_state, s.character)
        self.assertIsNone(s.world_state["spellcasting_v1"]["prepare_window"])


class PrepareApi(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaign_fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_fixtures.CampaignApiTests.asyncTearDown

    async def campaign(self):
        with fixed_town(self, 4201):
            response = await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_get_post_replay_reload(self):
        created = await self.campaign()
        sid = created["session_id"]
        session = self.manager.get(sid).game_session
        campaign_time.initialize(session.world_state)  # the first scene's clock, so the test can move time
        s = prepper("Wizard", session)
        url = f"/api/game/sessions/{sid}/spellcasting/prepare"
        view = await self.http.get(url)
        self.assertEqual(view.status_code, 200, view.text)
        self.assertEqual(view.json()["candidates"], BOOK)
        self.assertTrue(view.json()["open"])
        request = {"action_id": str(uuid.uuid4()), "prepared": ["Magic Missile", "Cure Wounds"]}
        first = await self.http.post(url, json=request)
        self.assertEqual(first.status_code, 200, first.text)
        body = first.json()
        self.assertEqual(body["result"]["prepared"], ["Magic Missile"])
        self.assertEqual(body["result"]["dropped"], [{"spell_id": "Cure Wounds", "reason": "not_in_spellbook"}])
        self.assertEqual(s.world_state["spellcasting_v1"]["prepared"], ["Magic Missile"])
        stored = self.store.get_campaign(created["campaign_id"])
        saved_state = copy.deepcopy(s.serialize_game_state())
        # The clock moves: the window is closed, yet the same action replays its stored answer and changes nothing.
        s.advance_campaign_time(60, "wait")
        moved = copy.deepcopy(s.serialize_game_state())
        retry = await self.http.post(url, json=request)
        self.assertEqual((retry.status_code, retry.json()), (200, body))
        self.assertEqual(s.serialize_game_state(), moved)
        conflict = await self.http.post(url, json={**request, "prepared": ["Shield"]})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"]["code"], "action_id_conflict")
        closed = await self.http.post(url, json={"action_id": str(uuid.uuid4()), "prepared": ["Shield"]})
        self.assertEqual(closed.status_code, 409, closed.text)
        self.assertEqual(closed.json()["detail"]["code"], "prepare_window_closed")
        self.assertEqual(s.serialize_game_state(), moved)
        # Reload from the store: the saved preparation is what the database holds.
        manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        sid2, record, *_ = manager.resume_campaign(created["campaign_id"])
        self.assertEqual(record.game_session.world_state["spellcasting_v1"], saved_state["world_state"]["spellcasting_v1"])
        self.assertEqual(self.store.get_campaign(created["campaign_id"]).payload["engine_save"]["world_state"]["spellcasting_v1"],
                         stored.payload["engine_save"]["world_state"]["spellcasting_v1"])
        restarted = create_app(session_manager=manager, authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url="http://testserver") as http:
            replay = await http.post(f"/api/game/sessions/{sid2}/spellcasting/prepare", json=request)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["result"], body["result"])

    async def test_too_many_is_a_question_not_a_save(self):
        created = await self.campaign()
        sid = created["session_id"]
        s = prepper("Wizard", self.manager.get(sid).game_session)
        before = copy.deepcopy(s.serialize_game_state())
        response = await self.http.post(f"/api/game/sessions/{sid}/spellcasting/prepare",
                                        json={"action_id": str(uuid.uuid4()), "prepared": BOOK[:5]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["result"]["status"], "too_many")
        self.assertEqual(s.serialize_game_state(), before)

    async def test_non_preparing_class_is_refused(self):
        created = await self.campaign()
        sid = created["session_id"]
        s = prepper("Sorcerer", self.manager.get(sid).game_session)
        before = copy.deepcopy(s.serialize_game_state())
        response = await self.http.post(f"/api/game/sessions/{sid}/spellcasting/prepare",
                                        json={"action_id": str(uuid.uuid4()), "prepared": ["Shield"]})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "prepare_not_supported")
        self.assertEqual(s.serialize_game_state(), before)
        view = await self.http.get(f"/api/game/sessions/{sid}/spellcasting/prepare")
        self.assertEqual((view.status_code, view.json()["supported"]), (200, False))


if __name__ == "__main__":
    unittest.main()
