"""Trusted local model selection; no provider network or personal campaign data."""
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter, RequiredModelUnavailableError
from api.schemas import TurnRequest

NINE = 'qwen3.5:9b-q4_K_M'
FOUR = 'qwen3.5:4b-q4_K_M'


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

    def test_running_game_defaults_to_the_9b_model(self):
        env = {'OLLAMA_HOST': 'http://127.0.0.1:9', 'OLLAMA_PROXY_TOKEN': 'fixture-not-secret'}
        with patch.dict(os.environ, env):
            os.environ.pop('AI_DND_OLLAMA_MODEL', None)
            with patch('ollama.Client'):
                adapter = AuthenticatedOllamaAdapter.from_environment()
        self.assertEqual(adapter.model_name, NINE)
        # The engine keeps sending its fixed 'qwen3:8b' tag; the adapter maps it.
        client = RecordingClient((NINE,))
        mapped = AuthenticatedOllamaAdapter(client, model_name=adapter.model_name)
        mapped.chat(model='qwen3:8b', messages=[])
        self.assertEqual(client.requests[0]['model'], NINE)

    def test_explicit_local_selection_is_actual_requested_tag(self):
        for model in (FOUR, NINE):
            with self.subTest(model=model):
                client = RecordingClient((model,))
                adapter = AuthenticatedOllamaAdapter(client, model_name=model)
                adapter.ensure_required_model()
                with adapter.capture_model_calls() as calls:
                    result = adapter.chat(model='qwen3:8b', messages=[], think=False)
                self.assertEqual(result['message']['content'], 'ok')
                self.assertEqual(calls, [model])
                self.assertEqual(client.requests, [{'model': model, 'messages': [], 'think': False}])

    def test_missing_selected_model_does_not_fall_back(self):
        client = RecordingClient()
        adapter = AuthenticatedOllamaAdapter(client, model_name=NINE)
        with self.assertRaises(RequiredModelUnavailableError):
            adapter.ensure_required_model()
        self.assertEqual(client.requests, [])

    def test_similar_alternative_tag_is_not_selected_tag(self):
        adapter = AuthenticatedOllamaAdapter(RecordingClient((NINE+'-other',)), model_name=NINE)
        with self.assertRaises(RequiredModelUnavailableError):
            adapter.ensure_required_model()

    def test_default_similar_tag_is_not_the_requested_tag(self):
        adapter = AuthenticatedOllamaAdapter(RecordingClient(('qwen3:8b-other', NINE)))
        with self.assertRaises(RequiredModelUnavailableError):
            adapter.ensure_required_model()

    def test_two_generation_budget_is_preserved(self):
        client = RecordingClient((NINE,))
        adapter = AuthenticatedOllamaAdapter(client, model_name=NINE)
        with adapter.capture_model_calls() as calls:
            adapter.chat(model='qwen3:8b')
            adapter.chat(model='qwen3:8b')
            with self.assertRaisesRegex(RuntimeError, 'budget exhausted'):
                adapter.chat(model='qwen3:8b')
        self.assertEqual(calls, [NINE, NINE])
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
