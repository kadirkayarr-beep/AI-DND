# ai-dnd/api/tests/test_dilim0_ui_sources.py
"""Dilim 0 (EK 6/2): the two fields the quest counter reads, after a town errand is accepted."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from api.serializers import serialize_session_state
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase
from api.tests.journeys.schema import load_scenario


def accept_step_only():
    """19 with its setup and only its first (accept) step, loaded through the strict loader."""
    data = json.loads((SCENARIO_DIR / "19_quest_item_no_duplicate.json").read_text(encoding="utf-8"))
    data["steps"] = data["steps"][:1]
    folder = Path(tempfile.mkdtemp())
    path = folder / f"{data['id']}.json"  # the loader holds the id and the file name equal
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        return load_scenario(path)
    finally:
        path.unlink()
        folder.rmdir()


class TheCounterSources(JourneyCase):
    async def test_an_accepted_town_errand_reaches_the_running_list_the_counter_reads(self):
        results = await self.run_scenario(accept_step_only())
        self.assertEqual([result.status for result in results], ["pass"], results)
        record = self.manager.get(self.last_session_id)
        state = serialize_session_state(record.game_session, record.journal, record.lore_authority)
        self.assertEqual(len(state["campaign_adventures"]["active"]), 1)
        # why the old counter said 0: the errand is not in state.quests
        self.assertEqual([q for q in (state.get("quests") or []) if q["status"] in {"accepted", "active"}], [])
