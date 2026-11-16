"""D-193: the spell-preparation body takes only a UUIDv4 action id, like turn bodies and species actions (D-111).

`SpellPrepareRequest.action_id` was a bare UUID, so a uuid1 id was accepted and a receipt was stored under it, while
the turn and species-action routes refuse it; the published `SpellPrepareInput.action_id` had no UUIDv4 pattern either.
"""

from __future__ import annotations

import copy
import re
import unittest
import uuid

from pydantic import ValidationError

from api.schemas import SpellPrepareRequest
from api.tests import test_campaign_api as campaign_fixtures  # module import: its tests are not re-collected here
from api.tests import test_contract_parity as parity  # module import: its tests are not re-collected here
from api.tests.test_spell_preparation_4c2 import prepper
from api.tests.town_seed import fixed_town

UUID4_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"


class SpellPrepareActionIdModel(unittest.TestCase):
    def test_published_pattern_is_the_uuid4_pattern(self):
        self.assertEqual(parity._schema("SpellPrepareInput")["properties"]["action_id"].get("pattern"), UUID4_PATTERN)

    def test_only_uuid4_is_accepted(self):
        for variant in "89ab":
            action_id = f"12345678-9abc-4def-{variant}123-456789abcdef"
            with self.subTest(accepted=action_id):
                self.assertEqual(str(SpellPrepareRequest(action_id=action_id).action_id), action_id)
                self.assertIsNotNone(re.fullmatch(UUID4_PATTERN, action_id))
        rejected = [f"12345678-9abc-{version}def-8123-456789abcdef" for version in "01235678"]
        rejected += [f"12345678-9abc-4def-{variant}123-456789abcdef" for variant in "07cf"]
        rejected.append(str(uuid.uuid1()))
        for action_id in rejected:
            with self.subTest(rejected=action_id):
                with self.assertRaisesRegex(ValidationError, "Action ID must be a UUIDv4"):
                    SpellPrepareRequest(action_id=action_id, prepared=["Magic Missile"])
                self.assertIsNone(re.fullmatch(UUID4_PATTERN, action_id))


class SpellPrepareActionIdHttp(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaign_fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_fixtures.CampaignApiTests.asyncTearDown

    async def test_uuid1_is_refused_and_stores_nothing(self):
        with fixed_town(self, 4193):
            created = await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})
        self.assertEqual(created.status_code, 200, created.text)
        sid = created.json()["session_id"]
        record = self.manager.get(sid)
        s = prepper("Wizard", record.game_session)
        before = copy.deepcopy(s.serialize_game_state())
        saved = copy.deepcopy(self.store.get_campaign(created.json()["campaign_id"]).payload)
        bad = str(uuid.uuid1())
        response = await self.http.post(f"/api/game/sessions/{sid}/spellcasting/prepare",
                                        json={"action_id": bad, "prepared": ["Magic Missile"]})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIsInstance(response.json().get("detail"), list, response.text)
        self.assertEqual(s.serialize_game_state(), before)
        self.assertEqual(self.store.get_campaign(created.json()["campaign_id"]).payload, saved)
        # The same body with a UUIDv4 still saves.
        good = await self.http.post(f"/api/game/sessions/{sid}/spellcasting/prepare",
                                    json={"action_id": str(uuid.uuid4()), "prepared": ["Magic Missile"]})
        self.assertEqual(good.status_code, 200, good.text)
        self.assertEqual(s.world_state["spellcasting_v1"]["prepared"], ["Magic Missile"])


if __name__ == "__main__":
    unittest.main()
