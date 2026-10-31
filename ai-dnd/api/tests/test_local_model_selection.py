"""Trusted local model selection; no provider network or personal campaign data."""
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from api import identity_suggestion
from api.local_model_config import PRODUCTION_LOCAL_MODEL, SUPPORTED_LOCAL_MODELS, selected_local_model
from api.main import create_app
from api.ollama_adapter import (
    CONTEXT_WINDOW_TOKENS,
    MAX_MODEL_CALLS_PER_TURN,
    AuthenticatedOllamaAdapter,
    RequiredModelUnavailableError,
)
from api.schemas import TurnRequest

NINE = 'qwen3.5:9b-q4_K_M'
FOUR = 'qwen3.5:4b-q4_K_M'
GEMMA = 'gemma4:e4b'
START_LOCAL = Path(__file__).resolve().parents[3] / 'start_local.ps1'


class RecordingClient:
    def __init__(self, names=('qwen3:8b',)):
        self.names = names
        self.requests = []

    def list(self):
        return {'models': [{'model': name} for name in self.names]}

    def chat(self, *args, **kwargs):
        self.requests.append(kwargs)
        return {'message': {'content': 'ok'}}


class LocalModelSelectionTests(unittest.TestCase):
    def test_library_default_remains_original_model(self):
        client = RecordingClient()
        adapter = AuthenticatedOllamaAdapter(client)
        self.assertEqual(adapter.model_name, 'qwen3:8b')
        adapter.chat(model='qwen3:8b', messages=[])
        self.assertEqual(client.requests[0]['model'], 'qwen3:8b')

    def test_running_game_defaults_to_gemma(self):
        env = {'OLLAMA_HOST': 'http://127.0.0.1:9', 'OLLAMA_PROXY_TOKEN': 'fixture-not-secret'}
        with patch.dict(os.environ, env):
            os.environ.pop('AI_DND_OLLAMA_MODEL', None)
            with patch('ollama.Client'):
                adapter = AuthenticatedOllamaAdapter.from_environment()
        self.assertEqual(adapter.model_name, GEMMA)
        # The engine keeps sending its fixed 'qwen3:8b' tag; the adapter maps it.
        client = RecordingClient((GEMMA,))
        mapped = AuthenticatedOllamaAdapter(client, model_name=adapter.model_name)
        mapped.chat(model='qwen3:8b', messages=[])
        self.assertEqual(client.requests[0]['model'], GEMMA)

    def test_explicit_local_selection_is_actual_requested_tag(self):
        for model in (FOUR, NINE, GEMMA):
            with self.subTest(model=model):
                client = RecordingClient((model,))
                adapter = AuthenticatedOllamaAdapter(client, model_name=model)
                adapter.ensure_required_model()
                with adapter.capture_model_calls() as calls:
                    result = adapter.chat(model='qwen3:8b', messages=[], think=False)
                self.assertEqual(result['message']['content'], 'ok')
                self.assertEqual(calls, [model])
                # The adapter owns the context window (4096 default truncated live replies).
                self.assertEqual(client.requests, [{
                    'model': model, 'messages': [], 'think': False,
                    'options': {'num_ctx': CONTEXT_WINDOW_TOKENS},
                }])

    def test_every_model_gets_the_same_call_shape(self):
        # Capability-neutral on purpose: think off, the same window and the
        # caller's schema and sampling untouched. Nothing branches on the tag.
        schema = {'type': 'object', 'properties': {'intent': {'type': 'string'}}}
        for model in SUPPORTED_LOCAL_MODELS:
            with self.subTest(model=model):
                client = RecordingClient((model,))
                adapter = AuthenticatedOllamaAdapter(client, model_name=model)
                adapter.chat(
                    model='qwen3:8b', messages=[], format=schema,
                    options={'temperature': 0.7, 'num_predict': 220},
                )
                self.assertEqual(client.requests, [{
                    'model': model, 'messages': [], 'format': schema, 'think': False,
                    'options': {'num_ctx': 8192, 'temperature': 0.7, 'num_predict': 220},
                }])

    def test_think_defaults_off_but_a_call_can_ask_for_it(self):
        client = RecordingClient((GEMMA,))
        adapter = AuthenticatedOllamaAdapter(client, model_name=GEMMA)
        adapter.chat(model='qwen3:8b', messages=[])
        adapter.chat(model='qwen3:8b', messages=[], think=True)
        self.assertEqual([r['think'] for r in client.requests], [False, True])

    def test_a_refused_model_call_is_not_retried_on_another_model(self):
        class RefusingClient(RecordingClient):
            def chat(self, *args, **kwargs):
                super().chat(*args, **kwargs)
                raise ConnectionError('refused')

        client = RefusingClient((GEMMA,))
        adapter = AuthenticatedOllamaAdapter(client, model_name=GEMMA)
        with adapter.capture_model_failures() as failures:
            with self.assertRaisesRegex(RuntimeError, 'Ollama request failed'):
                adapter.chat(model='qwen3:8b', messages=[])
        self.assertEqual([r['model'] for r in client.requests], [GEMMA])
        self.assertEqual([str(f) for f in failures], ['ConnectionError'])

    def test_missing_selected_model_does_not_fall_back(self):
        client = RecordingClient()
        adapter = AuthenticatedOllamaAdapter(client, model_name=NINE)
        with self.assertRaises(RequiredModelUnavailableError):
            adapter.ensure_required_model()
        self.assertEqual(client.requests, [])
        qwen_only = AuthenticatedOllamaAdapter(RecordingClient((NINE, FOUR)), model_name=GEMMA)
        with self.assertRaises(RequiredModelUnavailableError):
            qwen_only.ensure_required_model()

    def test_similar_alternative_tag_is_not_selected_tag(self):
        adapter = AuthenticatedOllamaAdapter(RecordingClient((NINE+'-other',)), model_name=NINE)
        with self.assertRaises(RequiredModelUnavailableError):
            adapter.ensure_required_model()

    def test_default_similar_tag_is_not_the_requested_tag(self):
        adapter = AuthenticatedOllamaAdapter(RecordingClient(('qwen3:8b-other', NINE)))
        with self.assertRaises(RequiredModelUnavailableError):
            adapter.ensure_required_model()

    def test_two_generation_budget_is_preserved(self):
        self.assertEqual(MAX_MODEL_CALLS_PER_TURN, 2)
        for model in (NINE, GEMMA):
            with self.subTest(model=model):
                client = RecordingClient((model,))
                adapter = AuthenticatedOllamaAdapter(client, model_name=model)
                with adapter.capture_model_calls() as calls:
                    adapter.chat(model='qwen3:8b')
                    adapter.chat(model='qwen3:8b')
                    with self.assertRaisesRegex(RuntimeError, 'budget exhausted'):
                        adapter.chat(model='qwen3:8b')
                self.assertEqual(calls, [model, model])
                self.assertEqual(len(client.requests), 2)

    def test_unexpected_engine_model_still_rejected(self):
        client = RecordingClient((NINE,))
        adapter = AuthenticatedOllamaAdapter(client, model_name=NINE)
        with self.assertRaisesRegex(RuntimeError, 'Unexpected model'):
            adapter.chat(model='arbitrary-model')
        self.assertEqual(client.requests, [])

    def test_configuration_is_not_arbitrary_model_or_url(self):
        for model in ('', 'gpt-anything', 'https://example.com/model', NINE+'-other'):
            with self.subTest(model=model), self.assertRaises(ValueError):
                AuthenticatedOllamaAdapter(RecordingClient(), model_name=model)

    def test_environment_is_read_once_at_adapter_creation(self):
        with patch.dict(os.environ, {'OLLAMA_HOST': 'http://127.0.0.1:9', 'OLLAMA_PROXY_TOKEN': 'fixture-not-secret', 'AI_DND_OLLAMA_MODEL': NINE}):
            with patch('ollama.Client') as client:
                adapter = AuthenticatedOllamaAdapter.from_environment()
            os.environ['AI_DND_OLLAMA_MODEL'] = FOUR
            self.assertEqual(adapter.model_name, NINE)
            self.assertEqual(client.call_args.kwargs['timeout'], 90)

    def test_invalid_environment_fails_closed_without_client_creation(self):
        with patch.dict(os.environ, {'OLLAMA_HOST': 'http://127.0.0.1:9', 'OLLAMA_PROXY_TOKEN': 'fixture-not-secret', 'AI_DND_OLLAMA_MODEL': 'wrong-model'}):
            with patch('ollama.Client') as client, self.assertRaises(ValueError):
                AuthenticatedOllamaAdapter.from_environment()
            client.assert_not_called()

    def test_health_reports_selected_tag_without_calling_provider(self):
        client = RecordingClient((NINE,))
        adapter = AuthenticatedOllamaAdapter(client, model_name=NINE)
        with adapter.engine_binding():
            app = create_app(ollama_adapter=adapter, authenticator=None)
            with TestClient(app) as http:
                for path in ('/api/health', '/api/game/health'):
                    response = http.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()['model'], NINE)
        self.assertEqual(client.requests, [])

    def test_request_cannot_select_model(self):
        with self.assertRaises(ValidationError):
            TurnRequest(message='Merhaba', model=NINE)


class IdentitySuggestionModelTests(unittest.TestCase):
    """The one model call that goes around the adapter must not go around its choice."""

    def provider_request(self, environ):
        client = RecordingClient()
        with patch.dict(os.environ, environ, clear=True), patch('ollama.Client', return_value=client):
            self.assertEqual(identity_suggestion.local_ollama_provider('prompt'), 'ok')
        self.assertEqual(len(client.requests), 1)
        return client.requests[0]

    def test_suggestion_uses_the_game_model_not_the_engine_tag(self):
        self.assertEqual(self.provider_request({})['model'], PRODUCTION_LOCAL_MODEL)
        self.assertEqual(self.provider_request({'AI_DND_OLLAMA_MODEL': FOUR})['model'], FOUR)

    def test_suggestion_keeps_think_off_and_the_game_context_window(self):
        request = self.provider_request({})
        self.assertIs(request['think'], False)
        self.assertEqual(request['options']['num_ctx'], CONTEXT_WINDOW_TOKENS)

    def test_suggestion_refuses_an_unsupported_model(self):
        client = RecordingClient()
        with patch.dict(os.environ, {'AI_DND_OLLAMA_MODEL': 'wrong-model'}, clear=True):
            with patch('ollama.Client', return_value=client), self.assertRaises(ValueError):
                identity_suggestion.local_ollama_provider('prompt')
        self.assertEqual(client.requests, [])

    def test_selected_model_reads_the_environment_at_call_time(self):
        with patch.dict(os.environ, {'AI_DND_OLLAMA_MODEL': NINE}, clear=True):
            self.assertEqual(selected_local_model(), NINE)
            os.environ['AI_DND_OLLAMA_MODEL'] = FOUR
            self.assertEqual(selected_local_model(), FOUR)


@unittest.skipUnless(
    START_LOCAL.is_file(),
    'start_local.ps1 is not in this tree: the guarded runs stage ai-dnd, content, tools and lib only',
)
class StartLocalModelTests(unittest.TestCase):
    def test_launcher_default_and_allow_list_match_the_server(self):
        text = START_LOCAL.read_text(encoding='utf-8')
        default = re.search(r'\$requiredModel = if \(\$env:AI_DND_OLLAMA_MODEL\) \{ \$env:AI_DND_OLLAMA_MODEL \} else \{ "([^"]+)" \}', text)
        allowed = re.search(r'\$requiredModel -cnotin @\(([^)]*)\)', text)
        self.assertIsNotNone(default)
        self.assertIsNotNone(allowed)
        self.assertEqual(default.group(1), PRODUCTION_LOCAL_MODEL)
        self.assertEqual(tuple(re.findall(r'"([^"]+)"', allowed.group(1))), SUPPORTED_LOCAL_MODELS)

    def test_only_local_play_with_a_key_file_turns_the_model_chain_on(self):
        text = START_LOCAL.read_text(encoding='utf-8').replace('\r\n', '\n')
        local_play = re.search(r'^if \(\$LocalPlay\) \{\n(.*?)^\} else \{\n(.*?)^\}\n', text, re.M | re.S)
        self.assertIsNotNone(local_play)
        turned_on, otherwise = local_play.groups()
        self.assertIn('$env:AI_DND_MODEL_CHAIN = "gemini,haiku,gemma"', turned_on)
        self.assertIn('Test-Path', turned_on)
        self.assertIn('.aidnd-gemini-key', turned_on)
        self.assertIn('.aidnd-anthropic-key', turned_on)
        self.assertIn('Env:AI_DND_MODEL_CHAIN', otherwise)
        self.assertEqual(text.count('$env:AI_DND_MODEL_CHAIN ='), 1)
        for private in ('Get-Content', 'GEMINI_API_KEY', 'ANTHROPIC_API_KEY'):
            self.assertNotIn(private, text)


class LocalModelHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_selected_model_response_is_truthful_and_preserves_state(self):
        import tempfile
        from pathlib import Path
        import httpx
        from api.persistence.campaign_store import CampaignStore
        from api.session_manager import SessionManager
        from api.tests.auth_fixture import FixedAuthenticator, TEST_PLAYER
        with tempfile.TemporaryDirectory() as tmp:
            manager = SessionManager(campaign_store=CampaignStore(Path(tmp)/'campaigns.sqlite3', bound_principal=TEST_PLAYER))
            client = RecordingClient()
            adapter = AuthenticatedOllamaAdapter(client, model_name=NINE)
            with adapter.engine_binding():
                app = create_app(session_manager=manager, ollama_adapter=adapter, authenticator=FixedAuthenticator(TEST_PLAYER))
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as http:
                    created = await http.post('/api/game/sessions')
                    self.assertEqual(created.status_code, 200, created.text)
                    sid = created.json()['session_id']
                    before_response = await http.get(f'/api/game/sessions/{sid}/state')
                    self.assertEqual(before_response.status_code, 200, before_response.text)
                    before = before_response.json()
                    response = await http.post(f'/api/game/sessions/{sid}/turn', json={'message': 'Merhaba, nasılsın?'})
                    self.assertEqual(response.status_code, 503, response.text)
                    self.assertEqual(response.json()['detail']['code'], 'model_unavailable')
                    self.assertIn(NINE, response.json()['detail']['message'])
                    self.assertNotIn('qwen3:8b', response.json()['detail']['message'])
                    after_response = await http.get(f'/api/game/sessions/{sid}/state')
                    self.assertEqual(after_response.status_code, 200, after_response.text)
                    after = after_response.json()
                    self.assertEqual(before, after)
            self.assertEqual(client.requests, [])
