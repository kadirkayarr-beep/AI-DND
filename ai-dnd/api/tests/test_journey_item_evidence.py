"""Evidence behind the item, weapon and starting-purse journeys (04_consume, 05_greatsword, 14_start_purse),
kept as tests so it can be re-checked.

The scenario files say what each step must leave behind. These tests replay the files themselves and pin
why each marked step breaks today and what the setup really puts in the world:

- a step whose turn is refused with HTTP 400 is a failure of that step (the runner records the status),
  not a trivial pass of its ``yasak_metin`` check on an empty narration (05 steps 2-3, 04 step 3);
- setup ``inventory`` and ``ammunition`` replace what character creation gave, they are not merged;
- 04 step 3 breaks only because the arrow counter is never seeded from the pack (item 56): with the
  counter given in setup the same step passes;
- 14: the creation response shows 6000 cp (the written "10 Altın" counted), the live purse holds 5000.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, apply_setup, read_observed
from api.tests.journeys.schema import load_scenario

CONSUME = SCENARIO_DIR / "04_consume.json"
GREATSWORD = SCENARIO_DIR / "05_greatsword.json"
START_PURSE = SCENARIO_DIR / "14_start_purse.json"


def scenario_variant(path: Path, change):
    """The scenario file with ``change`` applied to its data, loaded through the strict loader."""
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    folder = Path(tempfile.mkdtemp())
    variant = folder / f"{data['id']}.json"  # the loader holds the id and the file name equal
    variant.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        return load_scenario(variant)
    finally:
        variant.unlink()
        folder.rmdir()


class ItemJourneyEvidence(JourneyCase):
    async def play(self, scenario):
        """Run one scenario; return its step results and every turn's (status code, body)."""
        scenario = load_scenario(scenario) if isinstance(scenario, Path) else scenario
        turns: list[tuple[int, dict]] = []
        post = self.http.post

        async def recording_post(url, *args, **kwargs):
            response = await post(url, *args, **kwargs)
            if str(url).endswith("/turn"):
                turns.append((response.status_code, response.json()))
            return response

        with patch.object(self.http, "post", recording_post):
            results = await self.run_scenario(scenario)
        return results, turns

    def assert_refused(self, result, code: str):
        """The step's first failure is the turn's HTTP 400 with the engine's refusal code."""
        self.assertTrue(result.failures, result)
        failure = result.failures[0]
        self.assertTrue(failure.startswith("HTTP 400: "), failure)
        self.assertIn(f'"code":"{code}"', failure)

    async def test_a_refused_greatsword_attack_is_a_failed_step_not_an_empty_pass(self):
        """05 steps 2-3 (item 39): the panel attack and the Ready attack are refused with no_weapon. The
        refusal itself fails the step; the yasak_metin needles are never the reason (no narration)."""
        results, turns = await self.play(GREATSWORD)
        self.assertEqual([result.status for result in results],
                         ["pass", "known_broken", "known_broken", "pass"], results)
        self.assertEqual([status for status, _ in turns], [200, 400, 400, 200])
        for result in results[1:3]:
            # The refusal is the only failure: savas stays true and the needles find no narration, so
            # without the HTTP failure the step would pass on an empty text.
            self.assertEqual(len(result.failures), 1, result)
            self.assert_refused(result, "no_weapon")
            self.assertEqual(result.narration, "")
        # The spoken attack draws the Greatsword and hits: the conversation path is green today.
        self.assertTrue(self.last_observations[3]["savas"])
        self.assertNotIn("no_weapon", json.dumps(turns[3][1], ensure_ascii=False))

    async def test_the_bow_shot_is_refused_for_want_of_arrows(self):
        """04 (items 54, 56): eating and drinking change nothing; the bow shot is refused with
        no_ammunition, because the pack's '20 Ok' never reaches the arrow counter."""
        results, turns = await self.play(CONSUME)
        self.assertEqual([result.status for result in results], ["known_broken"] * 3, results)
        self.assertEqual([status for status, _ in turns], [200, 200, 400])
        unchanged = {"Greatsword": 1, "Uzun Yay & 20 Ok": 1, "Macera Çantası": 1, "Tabak yemek": 1, "Bira": 2}
        self.assertEqual(self.last_observations[0]["envanter"], unchanged)
        self.assertEqual(self.last_observations[1]["envanter"], unchanged)
        self.assert_refused(results[2], "no_ammunition")
        self.assertEqual(results[2].failures[1:],
                         ("savas: beklenen True, gözlenen False", "cephane: beklenen {'arrow': 19}, gözlenen {}"))
        self.assertEqual(self.last_observations[2]["cephane"], {})

    async def test_the_bow_shot_hits_once_the_counter_holds_arrows(self):
        """04 step 3 breaks only for item 56: given ``ammunition {"arrow": 20}`` in setup, the same shot is
        made and spends one arrow (the step's own expectation, so it passes)."""
        def seeded(data):
            data["setup"]["ammunition"] = {"arrow": 20}
            data["steps"] = [{key: value for key, value in data["steps"][2].items()
                              if key not in {"known_broken", "broken_because"}}]
            data["steps"][0].pop("independent", None)

        results, turns = await self.play(scenario_variant(CONSUME, seeded))
        self.assertEqual([result.status for result in results], ["pass"], results)
        self.assertEqual(turns[0][0], 200)
        self.assertEqual(self.last_observations[0]["cephane"], {"arrow": 19})

    async def test_setup_inventory_and_ammunition_replace_what_creation_gave(self):
        """apply_setup puts the scenario's items and counter in place of the created character's: the pack's
        own items are gone, nothing is merged."""
        setup = load_scenario(CONSUME).setup
        campaign = await self._journey_campaign(setup)
        world = self.manager.get(campaign["session_id"]).game_session.world_state
        created = read_observed(self, campaign["session_id"])["envanter"]
        self.assertIn("Ağır Tatar Yayı & 20 Ok", created, "creation gives pack C's own bow")
        world["ammunition"] = {"bolt": 7}  # stands in for any counter creation might give
        apply_setup(self, campaign, {**setup, "ammunition": {"arrow": 20}})
        observed = read_observed(self, campaign["session_id"])
        self.assertEqual(observed["envanter"], {"Greatsword": 1, "Uzun Yay & 20 Ok": 1, "Macera Çantası": 1,
                                                "Tabak yemek": 1, "Bira": 2})
        self.assertEqual(observed["cephane"], {"arrow": 20})
        self.assertEqual(observed["kese"], 100)

    async def test_the_creation_purse_and_the_live_purse_agree(self):
        """14 (item 34): Fighter pack C with Soldier option B. The creation response shows 6000 cp (50 gp plus
        the written '10 Altın'); the game starts with the same 6000 cp and no '10 Altın' left as an item."""
        setup = load_scenario(START_PURSE).setup
        campaign = await self._journey_campaign(setup)
        self.assertEqual(campaign["state"]["wallet"]["total_cp"], 6000)
        observed = read_observed(self, campaign["session_id"])
        self.assertEqual(observed["kese"], 6000)
        self.assertNotIn("10 Altın", observed["envanter"])

        results, _ = await self.play(START_PURSE)
        self.assertEqual([result.status for result in results], ["pass", "pass", "pass"], results)
        self.assertEqual(tuple(results[0].failures), ())
        # The first coin trade spends from the purse: 6000 - 4 = 5996, the barman holds the 4.
        self.assertEqual(self.last_observations[2]["kese"], 5996)
        self.assertEqual(self.last_observations[2]["kisi_kese"], {"barman": 4})


if __name__ == "__main__":
    import unittest

    unittest.main()
