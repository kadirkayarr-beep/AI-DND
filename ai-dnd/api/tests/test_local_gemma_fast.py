"""The local Gemma last link: the `gemma4-fast` model, a 16K window, keep_alive, one local call at a time."""
import threading
import time
import unittest

from api import ollama_adapter
from api.local_model_config import PRODUCTION_LOCAL_MODEL, SUPPORTED_LOCAL_MODELS, validate_local_model
from api.ollama_adapter import CONTEXT_WINDOW_TOKENS, AuthenticatedOllamaAdapter
from api.tests.test_local_model_selection import RecordingClient

FAST = 'gemma4-fast'


class TheModelIsGemmaFast(unittest.TestCase):
    def test_gemma4_fast_is_the_production_model_and_the_old_tag_is_gone(self):
        self.assertEqual(PRODUCTION_LOCAL_MODEL, FAST)
        self.assertEqual(validate_local_model(FAST), FAST)
        self.assertNotIn('gemma4:e4b', SUPPORTED_LOCAL_MODELS)

    def test_ollama_lists_the_model_with_its_latest_tag_and_that_still_counts_as_present(self):
        adapter = AuthenticatedOllamaAdapter(RecordingClient((f'{FAST}:latest',)), model_name=FAST)
        adapter.ensure_required_model()  # raises RequiredModelUnavailableError when the tag is not recognised

    def test_a_different_model_is_still_not_the_required_one(self):
        adapter = AuthenticatedOllamaAdapter(RecordingClient(('qwen3:8b',)), model_name=FAST)
        with self.assertRaises(ollama_adapter.RequiredModelUnavailableError):
            adapter.ensure_required_model()


class TheCallShape(unittest.TestCase):
    def chat(self, **extra):
        client = RecordingClient((FAST,))
        AuthenticatedOllamaAdapter(client, model_name=FAST).chat(model='qwen3:8b', messages=[], **extra)
        return client.requests[0]

    def test_the_window_is_16k(self):
        self.assertEqual(CONTEXT_WINDOW_TOKENS, 16384)
        self.assertEqual(self.chat()['options']['num_ctx'], 16384)

    def test_the_model_is_kept_loaded_for_the_session_and_a_caller_may_choose_otherwise(self):
        self.assertEqual(self.chat()['keep_alive'], '30m')
        self.assertEqual(self.chat(keep_alive='5m')['keep_alive'], '5m')

    def test_think_is_explicit_off_and_a_caller_may_turn_it_on(self):
        self.assertIs(self.chat()['think'], False)
        self.assertIs(self.chat(think=True)['think'], True)

    def test_no_image_or_audio_field_is_added(self):
        request = self.chat()
        self.assertNotIn('images', request)


class OneLocalCallAtATime(unittest.TestCase):
    def test_parallel_turns_queue_on_the_local_model(self):
        running = {'now': 0, 'peak': 0}
        guard = threading.Lock()

        class SlowClient(RecordingClient):
            def chat(self, *args, **kwargs):
                with guard:
                    running['now'] += 1
                    running['peak'] = max(running['peak'], running['now'])
                time.sleep(0.05)
                with guard:
                    running['now'] -= 1
                return {'message': {'content': 'ok'}}

        adapter = AuthenticatedOllamaAdapter(SlowClient((FAST,)), model_name=FAST)
        threads = [threading.Thread(target=lambda: adapter.chat(model='qwen3:8b', messages=[])) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(running['peak'], 1)


class TheWindowIsWatched(unittest.TestCase):
    def test_a_prompt_that_cannot_leave_room_for_the_reply_is_warned_about(self):
        big = [{'role': 'user', 'content': 'a' * (3 * CONTEXT_WINDOW_TOKENS)}]  # about 1 token per 3 characters
        adapter = AuthenticatedOllamaAdapter(RecordingClient((FAST,)), model_name=FAST)
        with self.assertLogs('ai_dnd.api.ollama', level='WARNING') as logs:
            adapter.chat(model='qwen3:8b', messages=big, options={'num_predict': 700})
        self.assertTrue(any('context window' in line for line in logs.output), logs.output)

    def test_a_normal_prompt_is_not_warned_about(self):
        adapter = AuthenticatedOllamaAdapter(RecordingClient((FAST,)), model_name=FAST)
        with self.assertNoLogs('ai_dnd.api.ollama', level='WARNING'):
            adapter.chat(model='qwen3:8b', messages=[{'role': 'user', 'content': 'Selam usta' * 50}])

    def test_a_reply_that_filled_the_window_is_warned_about(self):
        class FullClient(RecordingClient):
            def chat(self, *args, **kwargs):
                return {'message': {'content': 'ok'}, 'prompt_eval_count': CONTEXT_WINDOW_TOKENS - 10, 'eval_count': 10}

        adapter = AuthenticatedOllamaAdapter(FullClient((FAST,)), model_name=FAST)
        with self.assertLogs('ai_dnd.api.ollama', level='WARNING') as logs:
            adapter.chat(model='qwen3:8b', messages=[])
        self.assertTrue(any('context window' in line for line in logs.output), logs.output)


if __name__ == '__main__':
    unittest.main()
