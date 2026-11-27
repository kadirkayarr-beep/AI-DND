"""G2.12 / D-040: Wizard and Cleric start at level 2-5 over HTTP, with a catalog block each."""
import copy
import unittest
from pathlib import Path
from typing import Any

import httpx
import yaml

from api.dnd_2024_rules import get_character_creation_catalog
from api.tests import test_campaign_api as campaigns
from api.tests.test_wizard_cleric_4c3 import SPECS, THRESHOLDS, bundle
from api.tests.town_seed import default_town

TOWN_SEED = 8700
ROOT = Path(__file__).resolve().parents[3]


FOUR_CANTRIPS_FROM = 4
THIRD_LEVEL = 3


def request(cls: str, level: int) -> dict[str, Any]:
    """Return a custom creation request for the class at the starting level."""
    value = copy.deepcopy(SPECS[cls])
    value["class"] = value.pop("character_class")
    value.update(mode="custom", starting_level=level, level_choices=bundle(cls, level))
    return value


class WizardClericStartHttpTests(unittest.IsolatedAsyncioTestCase):
    """The HTTP creation of a Wizard or Cleric at a higher start."""

    asyncSetUp = campaigns.CampaignApiTests.asyncSetUp
    asyncTearDown = campaigns.CampaignApiTests.asyncTearDown

    def rows(self) -> list[tuple]:
        """Return every saved campaign row."""
        with self.store._connect() as connection:
            query = "SELECT * FROM campaigns ORDER BY campaign_id"
            return [tuple(row) for row in connection.execute(query)]

    async def post(self, value: dict[str, Any]) -> httpx.Response:
        """Create a campaign from the request body with the fixed town seed."""
        with default_town(self, TOWN_SEED):
            body = {"character": value}
            return await self.http.post("/api/game/campaigns", json=body)

    async def test_every_start_from_two_to_five_makes_a_valid_character(self) -> None:
        """Each class and level saves its level, XP, subclass, book and cantrips."""
        for cls in ("Wizard", "Cleric"):
            for level in (2, 3, 4, 5):
                with self.subTest(cls=cls, level=level):
                    response = await self.post(request(cls, level))
                    self.assertEqual(response.status_code, 200, response.text)
                    campaign = self.store.get_campaign(response.json()["campaign_id"])
                    saved = campaign.payload["engine_save"]
                    player = saved["player"]
                    keys = ("class", "level", "progression_level", "xp")
                    shown = tuple(player[key] for key in keys)
                    self.assertEqual(shown, (cls, level, level, THRESHOLDS[level]))
                    subclass = {"Wizard": "evoker", "Cleric": "life_domain"}[cls]
                    expected = None if level < THIRD_LEVEL else subclass
                    self.assertEqual(player.get("subclass_id"), expected)
                    state = saved["world_state"]["spellcasting_v1"]
                    if cls == "Wizard":
                        self.assertEqual(len(state["spellbook"]), 6 + 2 * (level - 1))
                    cantrips = 4 if level >= FOUR_CANTRIPS_FROM else THIRD_LEVEL
                    self.assertEqual(len(state["cantrips"]), cantrips)

    async def test_a_wrong_or_incomplete_bundle_publishes_nothing(self) -> None:
        """A wrong, missing, extra or null step is refused and nothing is saved."""
        cases = []
        wrong_class = request("Wizard", 3)
        wrong_class["level_choices"] = bundle("Cleric", 3)
        cases.append(wrong_class)
        other_wrong = request("Cleric", 3)
        other_wrong["level_choices"] = bundle("Wizard", 3)
        cases.append(other_wrong)
        for cls in ("Wizard", "Cleric"):
            missing = request(cls, 4)
            missing["level_choices"].pop("3")
            extra = request(cls, 3)
            extra["level_choices"]["4"] = bundle(cls, 4)["4"]
            nulled = request(cls, 4)
            nulled["level_choices"]["4"] = None
            cases.extend([missing, extra, nulled])
        before = self.rows()
        for value in cases:
            response = await self.post(value)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(self.rows(), before)

    async def test_the_catalog_offers_each_start_with_its_own_choices(self) -> None:
        """Each class block lists its levels, subclass, cantrip and spell choices."""
        catalog = get_character_creation_catalog()
        wizard = catalog["wizard_starting_creation"]
        cleric = catalog["cleric_starting_creation"]
        for block in (wizard, cleric):
            self.assertEqual(block["supported_starting_levels"], [1, 2, 3, 4, 5])
            pending = set(block["effects_pending_by_level"])
            self.assertEqual(pending, {"1", "2", "3", "4", "5"})
            self.assertEqual(len(block["level_3"]["subclass_options"]), 1)
            self.assertEqual(block["level_4"]["cantrip_count"], 1)
            self.assertTrue(block["level_4"]["supported_asi_choices"])
        self.assertEqual(wizard["level_3"]["subclass_options"][0]["id"], "evoker")
        self.assertEqual(cleric["level_3"]["subclass_options"][0]["id"], "life_domain")
        for level in (2, 3, 4, 5):
            self.assertEqual(wizard[f"level_{level}"]["spellbook_spell_count"], 2)
        self.assertNotIn("Fireball", wizard["level_4"]["spellbook_spell_ids"])
        self.assertIn("Fireball", wizard["level_5"]["spellbook_spell_ids"])
        self.assertIn("Thaumaturgy", cleric["level_4"]["cantrip_ids"])
        self.assertIn("Prestidigitation", wizard["level_4"]["cantrip_ids"])

    async def test_the_published_spec_matches_the_runtime_schema(self) -> None:
        """The hand-kept spec says what the runtime schema says."""
        runtime = self.app.openapi()["components"]["schemas"]
        spec = (ROOT / "lib/api-spec/openapi.yaml").read_text(encoding="utf-8")
        published = yaml.safe_load(spec)["components"]["schemas"]

        def normalized(value: object) -> object:
            """Drop the prose keys, which the two sides write differently."""
            if isinstance(value, dict):
                prose = ("title", "description")
                return {k: normalized(v) for k, v in value.items() if k not in prose}
            if isinstance(value, list):
                return [normalized(item) for item in value]
            return value

        prefixes = (
            "WizardStarting",
            "ClericStarting",
            "WizardLevelChoices",
            "ClericLevelChoices",
        )
        names = [name for name in runtime if name.startswith(prefixes)]
        self.assertGreaterEqual(len(names), 4)
        for name in names:
            ours = normalized(runtime[name])
            self.assertEqual(ours, normalized(published[name]), name)
        catalog = "CharacterCreationCatalogResponse"
        fields = (
            ("CharacterCreateInput", "level_choices"),
            (catalog, "wizard_starting_creation"),
            (catalog, "cleric_starting_creation"),
        )
        for name, field in fields:
            ours = normalized(runtime[name]["properties"][field])
            theirs = normalized(published[name]["properties"][field])
            self.assertEqual(ours, theirs, field)
