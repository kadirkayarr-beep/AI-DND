"""A journey reload must change the manager used by later real HTTP turns."""
from contextlib import contextmanager
from api.tests.journeys.runner import JourneyCase, ScriptedModel
from api.tests import test_journey_runner as existing

class ReloadContinuation(JourneyCase):
    async def test_next_http_turn_uses_reopened_manager_and_leaves_old_runtime_untouched(self):
        seen = {}
        class Tracking(ScriptedModel):
            @contextmanager
            def bind(driver, case, step):
                if step.reload:
                    seen['old_manager'] = case.manager
                    seen['old_record'] = case.manager.get(case.last_session_id)
                else:
                    seen['next_manager'] = case.manager
                    seen['next_record'] = case.manager.get(case.last_session_id)
                    seen['next_app_manager'] = case.app.state.session_manager
                with super().bind(case, step) as client:
                    yield client
        results = await self.run_scenario(existing.beer_scenario(
            {'reload':True, 'expect':{'kese':100}},
            {'command':existing.BUY_BEER, 'expect':{'kese':96}},
        ), model=Tracking())
        self.assertEqual([r.status for r in results], ['pass','pass'], results)
        self.assertIsNot(seen['next_manager'], seen['old_manager'])
        self.assertIs(seen['next_app_manager'], seen['next_manager'])
        self.assertIsNot(seen['next_record'], seen['old_record'])
        self.assertEqual(seen['old_record'].game_session.world_state['currency']['player'],100)
        self.assertEqual(seen['next_record'].game_session.world_state['currency']['player'],96)
        saved = self.store.get_campaign(seen['next_record'].campaign_id)
        self.assertEqual(saved.payload['engine_save']['world_state']['currency']['player'],96)