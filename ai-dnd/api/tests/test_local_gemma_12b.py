"""The local last link is `gemma4-12b-dm` (Gemma 4 12B IQ3_M, 12K window); `gemma4-fast` (E4B, 16K) is its fallback.

Only the local call changes: the cloud providers receive the engine's prompt as before.
"""
import os
import threading
import unittest
from unittest.mock import patch

import ollama

from api import identity_suggestion, ollama_adapter
from api.auth import FixedAuthenticator
from api.local_model_config import (
    LOCAL_FALLBACK_MODELS,
    PRODUCTION_LOCAL_MODEL,
    SUPPORTED_LOCAL_MODELS,
    validate_local_model,
)
from api.main import create_app
from api.model_phase import classifier_call, front_call
from api.ollama_adapter import (
    CONTEXT_WINDOW_TOKENS,
    LOCAL_DM_EXAMPLE,
    LOCAL_REPLY_RESERVE_TOKENS,
    LOCAL_STYLE_RULES,
    PROVIDER_TIMEOUT_SECONDS,
    AuthenticatedOllamaAdapter,
    RequiredModelUnavailableError,
    canonical_world_metadata_context,
    local_context_window,
)
from api.tests.auth_fixture import TEST_PLAYER, TestPlayerSessionManager
from api.tests.test_local_model_selection import RecordingClient

DM = 'gemma4-12b-dm'
FAST = 'gemma4-fast'
OK = {'message': {'role': 'assistant', 'content': 'ok'}}
WINDOW = 12288
BUDGET = (WINDOW - 600) * 3  # characters the 12B's prompt may take: 600 tokens kept for the reply, ~3 characters a token
ENGINE_SYSTEM = 'Sen bu oyunun anlatıcısısın.'


def dm_messages(history_lines, line_length=240, player='Barmene selam veriyorum', guidance='Konuşma turu.'):
    """The engine's narration prompt in miniature: a system text, then sections, the history block, the player last."""
    history = '\n'.join(
        f'- Anlatım {index:03d} burada başlar. ' + 'a' * (line_length - 30) for index in range(history_lines))
    user = (
        f'Yalnızca bu turu yanıtla. {guidance}\n\n'
        'KOMPAKT WORLD CONTEXT (salt okunur):\n{"yer":"taverna"}\n\n'
        f'RECENT NARRATION (yalnızca tekrar etmeme için; olgusal dayanak değil):\n{history}\n'
        'Son anlatım “Ocakta ateş çıtırdıyor” diye başladı; aynı sözlerle ya da aynı kalıpla başlama.\n\n'
        f'CURRENT PLAYER MESSAGE (doğrulanmamış yeni girdi):\n{player}'
    )
    return [{'role': 'system', 'content': ENGINE_SYSTEM}, {'role': 'user', 'content': user}]


def characters(messages):
    return sum(len(str(message.get('content', ''))) for message in messages)


def local_system():
    return f'{ENGINE_SYSTEM}\n\n{LOCAL_STYLE_RULES}\n\n{LOCAL_DM_EXAMPLE}'


class FakeChain:
    """Every cloud provider fails; records what the cloud would have received, then lets the local model answer."""

    def __init__(self):
        self.calls = []

    def model_names(self):
        return ['gemini-3.5-flash-lite', 'claude-haiku-5-5']

    def can_answer(self):
        return True

    def chat(self, call, local):
        self.calls.append(call)
        return local(), None


class FailingClient(RecordingClient):
    """Fails every request whose model is in `failing` with the given error."""

    def __init__(self, names, failing, error):
        super().__init__(names)
        self.failing = failing
        self.error = error

    def chat(self, *args, **kwargs):
        super().chat(*args, **kwargs)
        if kwargs.get('model') in self.failing:
            raise self.error
        return dict(OK)


def vram_error():
    return ollama.ResponseError('cudaMalloc failed: out of memory', 500)


class TheModelIs12B(unittest.TestCase):
    def test_the_running_game_plays_with_the_12b_and_e4b_stays_supported(self):
        self.assertEqual(PRODUCTION_LOCAL_MODEL, DM)
        self.assertEqual(validate_local_model(DM), DM)
        self.assertIn(FAST, SUPPORTED_LOCAL_MODELS)
        self.assertEqual(LOCAL_FALLBACK_MODELS, {DM: FAST})

    def test_from_environment_selects_the_12b_by_default(self):
        env = {'OLLAMA_HOST': 'http://127.0.0.1:9', 'OLLAMA_PROXY_TOKEN': 'fixture-not-secret'}
        with patch.dict(os.environ, env):
            os.environ.pop('AI_DND_OLLAMA_MODEL', None)
            with patch('ollama.Client') as client:
                adapter = AuthenticatedOllamaAdapter.from_environment()
        self.assertEqual(adapter.model_name, DM)
        self.assertGreaterEqual(client.call_args.kwargs['timeout'], 90)
        self.assertGreaterEqual(PROVIDER_TIMEOUT_SECONDS, 90)


class TheCallShape(unittest.TestCase):
    def request(self, model=DM, **extra):
        client = RecordingClient((model,))
        AuthenticatedOllamaAdapter(client, model_name=model).chat(model='qwen3:8b', messages=[], **extra)
        return client.requests[0]

    def test_the_12b_window_is_12k_and_e4b_keeps_16k(self):
        self.assertEqual(local_context_window(DM), WINDOW)
        self.assertEqual(local_context_window(FAST), 16384)
        self.assertEqual(CONTEXT_WINDOW_TOKENS, 16384)
        self.assertEqual(self.request()['options']['num_ctx'], WINDOW)

    def test_the_12b_window_cannot_be_changed_by_a_caller_because_any_other_value_reloads_or_overflows(self):
        self.assertEqual(self.request(options={'num_ctx': 16384})['options']['num_ctx'], WINDOW)

    def test_the_12b_reply_is_capped_near_300_tokens(self):
        self.assertEqual(self.request(options={'num_predict': 700})['options']['num_predict'], 300)
        self.assertEqual(self.request()['options']['num_predict'], 300)
        self.assertEqual(self.request(options={'num_predict': 60})['options']['num_predict'], 60)
        self.assertEqual(self.request(FAST, options={'num_predict': 700})['options']['num_predict'], 700)

    def test_intent_and_front_readings_keep_their_reply_budget_so_their_json_is_not_cut(self):
        for scope in (classifier_call, front_call):
            with self.subTest(scope=scope.__name__), scope():
                self.assertEqual(self.request(options={'num_predict': 400})['options']['num_predict'], 400)

    def test_think_off_and_kept_loaded_thirty_minutes(self):
        request = self.request()
        self.assertIs(request['think'], False)
        self.assertEqual(request['keep_alive'], '30m')
        self.assertEqual(request['model'], DM)


class TheHistoryFitsTheWindow(unittest.TestCase):
    def local_request(self, messages, model=DM, **options):
        client = RecordingClient((model,))
        AuthenticatedOllamaAdapter(client, model_name=model).chat(
            model='qwen3:8b', messages=messages, options=options or {'num_predict': 700})
        return client.requests[0]

    def test_a_prompt_that_fits_is_sent_whole_apart_from_the_local_rules(self):
        messages = dm_messages(8)
        sent = self.local_request(messages)['messages']
        self.assertEqual(sent[1], messages[1])

    def test_old_history_is_summarised_until_prompt_and_reply_fit_12k_and_the_system_prompt_stays_whole(self):
        messages = dm_messages(200)  # about 48 000 characters: more than (12288 - 600) * 3
        self.assertGreater(characters(messages), BUDGET)
        sent = self.local_request(messages)['messages']
        self.assertLessEqual(characters(sent), BUDGET)
        self.assertEqual(sent[0]['content'], local_system())
        user = sent[1]['content']
        self.assertNotIn('- Anlatım 000 burada başlar. aaaa', user)  # the oldest line is no longer whole
        self.assertIn('- Anlatım 199 burada başlar. ' + 'a' * 210, user)  # the newest stays whole
        summary = next(line for line in user.split('\n') if line.startswith('- (Daha eski '))
        self.assertIn('anlatımın özeti', summary)
        self.assertIn('Anlatım 000 burada başlar.', summary)  # the first sentence of a summarised line survives
        self.assertNotIn('aaaa', summary)
        self.assertTrue(user.startswith('Yalnızca bu turu yanıtla.'))
        self.assertIn('Son anlatım “Ocakta ateş çıtırdıyor” diye başladı', user)
        self.assertTrue(user.endswith('CURRENT PLAYER MESSAGE (doğrulanmamış yeni girdi):\nBarmene selam veriyorum'))

    def test_the_summary_is_the_same_for_the_same_history(self):
        first = self.local_request(dm_messages(200))['messages']
        second = self.local_request(dm_messages(200))['messages']
        self.assertEqual(first, second)

    def test_at_least_600_tokens_are_kept_for_the_reply(self):
        self.assertEqual(LOCAL_REPLY_RESERVE_TOKENS, 600)
        sent = self.local_request(dm_messages(200), num_predict=200)['messages']
        self.assertLessEqual(characters(sent), BUDGET)
        self.assertGreater(characters(sent), BUDGET - 1000)  # cut to the budget, not far below it

    def test_e4b_keeps_its_16k_budget(self):
        messages = dm_messages(150)  # about 36 000 characters: over the 12B's budget, inside the E4B's
        self.assertEqual(self.local_request(messages, FAST)['messages'][1], messages[1])

    def test_the_cloud_receives_the_whole_history_and_no_local_rule(self):
        messages = dm_messages(200)
        chain = FakeChain()
        client = RecordingClient((DM,))
        AuthenticatedOllamaAdapter(client, model_name=DM, chain=chain).chat(
            model='qwen3:8b', messages=messages, options={'num_predict': 700})
        cloud = chain.calls[0]
        self.assertEqual(cloud['messages'], messages)
        self.assertEqual(cloud['options']['num_predict'], 700)
        local = client.requests[0]['messages']
        self.assertEqual(local[0]['content'], local_system())
        self.assertLess(characters(local), characters(cloud['messages']))


class TheCacheablePrefix(unittest.TestCase):
    """Ollama reuses the cached start that a request shares with the one before it: the start must not move."""

    def turn(self, messages, weather):
        client = RecordingClient((DM,))
        adapter = AuthenticatedOllamaAdapter(client, model_name=DM)
        metadata = {'environment': 'tavern', 'time_of_day': 'evening', 'weather': weather}
        with canonical_world_metadata_context(lambda: metadata):
            adapter.chat(model='qwen3:8b', messages=messages, options={'num_predict': 700})
        return client.requests[0]['messages']

    def test_same_system_prompt_and_history_head_give_identical_leading_bytes(self):
        one = self.turn(dm_messages(6, player='Etrafıma bakıyorum'), 'clear')
        two = self.turn(dm_messages(6, player='Barmene selam veriyorum'), 'rain')
        self.assertEqual(one[0], two[0])  # the whole system text, rules and example included
        head = dm_messages(6)[1]['content'].split('CURRENT PLAYER MESSAGE')[0]
        self.assertTrue(one[1]['content'].startswith(head))
        self.assertTrue(two[1]['content'].startswith(head))
        self.assertEqual(one[0]['content'], local_system())

    def test_the_changing_world_metadata_goes_to_the_end_for_the_local_model_only(self):
        sent = self.turn(dm_messages(2), 'rain')
        self.assertNotIn('weather=', sent[0]['content'])
        self.assertIn('weather=rain', sent[-1]['content'])
        self.assertTrue(sent[-1]['content'].rstrip().endswith('Python remains authoritative.'))
        chain = FakeChain()
        adapter = AuthenticatedOllamaAdapter(RecordingClient((DM,)), model_name=DM, chain=chain)
        with canonical_world_metadata_context(lambda: {'environment': 'tavern', 'time_of_day': 'night', 'weather': 'fog'}):
            adapter.chat(model='qwen3:8b', messages=dm_messages(2))
        self.assertIn('weather=fog', chain.calls[0]['messages'][0]['content'])  # the cloud prompt is as before


class TheLocalRules(unittest.TestCase):
    def sent(self, messages, scope=None):
        client = RecordingClient((DM,))
        adapter = AuthenticatedOllamaAdapter(client, model_name=DM)
        if scope is None:
            adapter.chat(model='qwen3:8b', messages=messages)
        else:
            with scope():
                adapter.chat(model='qwen3:8b', messages=messages)
        return client.requests[0]['messages']

    def test_the_rules_say_what_the_owner_asked(self):
        for words in ('Kısa ve yalın', 'NPC ve yer adları Türkçe', 'Parantez içinde İngilizce terim yazma',
                      'beceri adlarını', 'El Çabukluğu', '"sen"',
                      'Oyuncunun eylemini onun yerine ayrıntılı anlatma: denemeyi tek cümleyle belirt, zar iste ve dur.'):
            self.assertIn(words, LOCAL_STYLE_RULES)
        self.assertNotIn('Sleight', LOCAL_DM_EXAMPLE)
        self.assertIn('zar', LOCAL_DM_EXAMPLE)

    def test_the_local_dm_system_prompt_ends_with_the_rules_and_the_example(self):
        self.assertEqual(self.sent(dm_messages(2))[0]['content'], local_system())

    def test_classifier_and_front_readings_get_no_style_rules(self):
        for scope in (classifier_call, front_call):
            with self.subTest(scope=scope.__name__):
                self.assertEqual(self.sent(dm_messages(2), scope)[0]['content'], ENGINE_SYSTEM)

    def test_a_call_without_a_system_message_gets_none_added(self):
        self.assertEqual(self.sent([{'role': 'user', 'content': 'Selam'}]), [{'role': 'user', 'content': 'Selam'}])

    def test_the_engine_messages_are_not_changed_in_place(self):
        messages = dm_messages(200)
        before = [dict(message) for message in messages]
        self.sent(messages)
        self.assertEqual(messages, before)


class TheFallback(unittest.TestCase):
    def test_a_vram_error_falls_back_to_e4b_with_its_own_window_and_is_logged(self):
        client = FailingClient((DM, FAST), {DM}, vram_error())
        adapter = AuthenticatedOllamaAdapter(client, model_name=DM)
        with self.assertLogs('ai_dnd.api.ollama', level='WARNING') as logs:
            with adapter.capture_model_calls() as calls, adapter.capture_model_failures() as failures:
                response = adapter.chat(model='qwen3:8b', messages=dm_messages(2), options={'num_predict': 700})
        self.assertEqual(response['message']['content'], 'ok')
        self.assertEqual([r['model'] for r in client.requests], [DM, FAST])
        self.assertEqual(client.requests[1]['options']['num_ctx'], 16384)
        self.assertEqual(client.requests[1]['options']['num_predict'], 700)
        self.assertEqual(client.requests[1]['keep_alive'], '30m')
        self.assertIs(client.requests[1]['think'], False)
        self.assertEqual(failures, [])
        self.assertEqual(len(calls), 1)  # one engine call, still one of the turn's two
        self.assertTrue(any('gemma4-fast' in line and 'fall' in line.lower() for line in logs.output), logs.output)

    def test_a_missing_12b_falls_back_too(self):
        client = FailingClient((FAST,), {DM}, ollama.ResponseError("model 'gemma4-12b-dm' not found", 404))
        adapter = AuthenticatedOllamaAdapter(client, model_name=DM)
        with self.assertLogs('ai_dnd.api.ollama', level='WARNING'):
            adapter.chat(model='qwen3:8b', messages=[])
        self.assertEqual([r['model'] for r in client.requests], [DM, FAST])

    def test_after_a_fallback_the_12b_rests_and_is_tried_again_later(self):
        client = FailingClient((DM, FAST), {DM}, vram_error())
        adapter = AuthenticatedOllamaAdapter(client, model_name=DM)
        moment = [1000.0]
        adapter._now = lambda: moment[0]
        with self.assertLogs('ai_dnd.api.ollama', level='WARNING'):
            adapter.chat(model='qwen3:8b', messages=[])
        adapter.chat(model='qwen3:8b', messages=[])
        self.assertEqual([r['model'] for r in client.requests], [DM, FAST, FAST])
        moment[0] += ollama_adapter.LOCAL_FALLBACK_REST_SECONDS + 1
        client.failing = set()
        adapter.chat(model='qwen3:8b', messages=[])
        self.assertEqual([r['model'] for r in client.requests][-1], DM)

    def test_a_transport_error_or_timeout_does_not_switch_models(self):
        for error in (ConnectionError('refused'), TimeoutError('slow')):
            with self.subTest(error=type(error).__name__):
                client = FailingClient((DM, FAST), {DM}, error)
                adapter = AuthenticatedOllamaAdapter(client, model_name=DM)
                with adapter.capture_model_failures() as failures:
                    with self.assertRaisesRegex(RuntimeError, 'Ollama request failed'):
                        adapter.chat(model='qwen3:8b', messages=[])
                self.assertEqual([r['model'] for r in client.requests], [DM])
                self.assertEqual([str(f) for f in failures], [type(error).__name__])

    def test_the_fallback_failing_too_fails_the_call_once(self):
        client = FailingClient((DM, FAST), {DM, FAST}, vram_error())
        adapter = AuthenticatedOllamaAdapter(client, model_name=DM)
        with self.assertLogs('ai_dnd.api.ollama', level='WARNING'):
            with adapter.capture_model_failures() as failures:
                with self.assertRaisesRegex(RuntimeError, 'Ollama request failed'):
                    adapter.chat(model='qwen3:8b', messages=[])
        self.assertEqual([r['model'] for r in client.requests], [DM, FAST])
        self.assertEqual([str(f) for f in failures], ['ResponseError'])

    def test_e4b_itself_has_no_fallback(self):
        client = FailingClient((FAST,), {FAST}, vram_error())
        adapter = AuthenticatedOllamaAdapter(client, model_name=FAST)
        with self.assertRaisesRegex(RuntimeError, 'Ollama request failed'):
            adapter.chat(model='qwen3:8b', messages=[])
        self.assertEqual([r['model'] for r in client.requests], [FAST])

    def test_the_12b_is_required_unless_its_fallback_is_installed(self):
        AuthenticatedOllamaAdapter(RecordingClient((f'{DM}:latest',)), model_name=DM).ensure_required_model()
        AuthenticatedOllamaAdapter(RecordingClient((f'{FAST}:latest',)), model_name=DM).ensure_required_model()
        with self.assertRaises(RequiredModelUnavailableError):
            AuthenticatedOllamaAdapter(RecordingClient(('qwen3:8b',)), model_name=DM).ensure_required_model()


class TheWarmUp(unittest.TestCase):
    def test_a_warm_up_is_one_tiny_request_with_the_game_window(self):
        client = RecordingClient((DM,))
        adapter = AuthenticatedOllamaAdapter(client, model_name=DM)
        adapter.warm_up()
        self.assertEqual(len(client.requests), 1)
        request = client.requests[0]
        self.assertEqual(request['model'], DM)
        self.assertEqual(request['options']['num_ctx'], WINDOW)  # another window would load the model a second time
        self.assertLessEqual(request['options']['num_predict'], 8)
        self.assertEqual(request['keep_alive'], '30m')
        self.assertIs(request['think'], False)

    def test_a_warm_up_that_cannot_load_the_12b_warms_e4b_and_never_raises(self):
        client = FailingClient((DM, FAST), {DM}, vram_error())
        adapter = AuthenticatedOllamaAdapter(client, model_name=DM)
        with self.assertLogs('ai_dnd.api.ollama', level='WARNING'):
            adapter.warm_up()
        self.assertEqual([r['model'] for r in client.requests], [DM, FAST])
        broken = AuthenticatedOllamaAdapter(FailingClient((DM,), {DM, FAST}, ConnectionError('down')), model_name=DM)
        with self.assertLogs('ai_dnd.api.ollama', level='WARNING'):
            broken.warm_up()

    def test_a_warm_up_waits_in_the_local_queue(self):
        client = RecordingClient((DM,))
        adapter = AuthenticatedOllamaAdapter(client, model_name=DM)
        with ollama_adapter._LOCAL_CALL_LOCK:
            thread = threading.Thread(target=adapter.warm_up)
            thread.start()
            thread.join(0.2)
            self.assertEqual(client.requests, [])
        thread.join(5)
        self.assertEqual(len(client.requests), 1)

    def test_only_an_environment_adapter_warms_up_and_the_app_starts_it(self):
        quiet = RecordingClient((DM,))
        adapter = AuthenticatedOllamaAdapter(quiet, model_name=DM)
        with adapter.engine_binding():
            create_app(session_manager=TestPlayerSessionManager(), authenticator=FixedAuthenticator(TEST_PLAYER),
                       ollama_adapter=adapter)
        self.assertEqual(quiet.requests, [])

        warm = RecordingClient((DM,))
        adapter = AuthenticatedOllamaAdapter(warm, model_name=DM)
        adapter.warm_up_on_start = True
        with adapter.engine_binding():
            create_app(session_manager=TestPlayerSessionManager(), authenticator=FixedAuthenticator(TEST_PLAYER),
                       ollama_adapter=adapter)
            adapter.wait_for_warm_up(5)
        self.assertEqual([r['model'] for r in warm.requests], [DM])

        env = {'OLLAMA_HOST': 'http://127.0.0.1:9', 'OLLAMA_PROXY_TOKEN': 'fixture-not-secret'}
        with patch.dict(os.environ, env), patch('ollama.Client'):
            os.environ.pop('AI_DND_OLLAMA_MODEL', None)
            self.assertTrue(AuthenticatedOllamaAdapter.from_environment().warm_up_on_start)


class TheSuggestionShares(unittest.TestCase):
    def test_the_note_uses_the_game_window_keep_alive_and_the_local_queue(self):
        client = RecordingClient()
        with patch.dict(os.environ, {}, clear=True), patch('ollama.Client', return_value=client):
            with ollama_adapter._LOCAL_CALL_LOCK:
                result = []
                thread = threading.Thread(target=lambda: result.append(identity_suggestion.local_ollama_provider('p')))
                thread.start()
                thread.join(0.2)
                self.assertEqual(client.requests, [])
            thread.join(5)
        self.assertEqual(result, ['ok'])
        request = client.requests[0]
        self.assertEqual(request['model'], DM)
        self.assertEqual(request['options']['num_ctx'], WINDOW)
        self.assertEqual(request['keep_alive'], '30m')


if __name__ == '__main__':
    unittest.main()
