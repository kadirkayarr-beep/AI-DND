"""G2.10: character creation split (D-540), creation input limits (D-319, D-313), one blank check (D-539),
hosted docs and health (D-314), campaign id conflict (D-385), per-owner identity rejections (D-316)."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from pydantic import ValidationError

from api import character_creation
from api.auth import FailClosedAuthenticator, FixedAuthenticator, OidcAuthenticator, OidcSettings
from api.dnd_2024_rules import (
    ABILITY_KEYS,
    BACKGROUND_DEFINITIONS,
    CharacterCreationError,
    get_character_creation_catalog,
    validate_background_bonuses,
)
from api.identity_suggestion import IdentitySuggestionRequest, IdentitySuggestionService
from api.main import create_app
from api import schemas
from api.schemas import CampaignCreateRequest, CharacterCreateInput, TurnRequest
from api.session_manager import SessionManager
from api.tests import test_campaign_api as campaigns
from api.tests.auth_fixture import PLAYER_A, PLAYER_B, TEST_PLAYER
from api.tests.journeys.runner import _campaign_seeded
from api.tests.test_dilim0_start_purse import SPECS, create, random_created
from api.tests.test_roadmap_c18_rogue import spec as rogue_spec
from api.tests.town_seed import fixed_town

GOLDEN = json.loads(Path(__file__).with_name("g210_creation_golden.json").read_text(encoding="utf-8"))
TOWN_SEED = 8420
BASE_CHARACTER = {"mode": "custom", "name": "Ada", "species": "Human", "class": "Rogue"}
BACKGROUND = "Soldier"
PERMITTED = list(BACKGROUND_DEFINITIONS[BACKGROUND]["abilities"])
OUTSIDE = next(key for key in ABILITY_KEYS if key not in PERMITTED)


def snap(session):
    character = json.dumps(session.character, sort_keys=True, default=str)
    return [session.world_state.get("currency", {}).get("player"), list(session.world_state["inventory"]),
            hashlib.sha256(character.encode()).hexdigest()[:16]]


class TestCreationSplitKeepsTheCharacter(unittest.TestCase):
    """D-540: every class, package and background option, and random seeds, still produce the same purse, items and record."""

    def test_custom_classes_packages_and_options_match_the_recorded_result(self):
        catalog = get_character_creation_catalog()
        seen = 0
        for character_class in SPECS:
            for package in catalog["classes"][character_class]["equipment_packages"]:
                for option in ("A", "B"):
                    key = f"{character_class}|{package['id']}|{option}"
                    with self.subTest(key):
                        session, _ = create(character_class, package["id"], option)
                        self.assertEqual(snap(session), GOLDEN[key])
                        seen += 1
        self.assertEqual(seen, len([key for key in GOLDEN if not key.startswith("random|")]))

    def test_random_seeds_match_the_recorded_result(self):
        for seed in range(1, 25):
            with self.subTest(seed=seed):
                self.assertEqual(snap(random_created(seed)), GOLDEN[f"random|{seed}"])


class TestBackgroundBonusLimits(unittest.TestCase):
    """D-319: only +1/+2 on permitted abilities, and only the six abilities."""

    def bonuses(self, **extra):
        value = {PERMITTED[0]: 2, PERMITTED[1]: 1}
        value.update(extra)
        return value

    def test_the_plain_two_one_split_is_accepted(self):
        validate_background_bonuses(BACKGROUND, self.bonuses())

    def test_a_negative_bonus_is_refused(self):
        for target in (PERMITTED[2], OUTSIDE):
            with self.subTest(target=target), self.assertRaises(CharacterCreationError):
                validate_background_bonuses(BACKGROUND, self.bonuses(**{target: -1}))

    def test_a_zero_bonus_on_a_listed_key_is_still_fine_but_an_unknown_key_is_not(self):
        validate_background_bonuses(BACKGROUND, self.bonuses(**{OUTSIDE: 0}))
        with self.assertRaises(CharacterCreationError):
            validate_background_bonuses(BACKGROUND, self.bonuses(luck=0))

    def test_a_bonus_that_is_not_a_whole_number_is_refused(self):
        for bad in (1.5, "2", True, None):
            with self.subTest(bad=bad), self.assertRaises(CharacterCreationError):
                validate_background_bonuses(BACKGROUND, {PERMITTED[0]: bad, PERMITTED[1]: 1})

    def test_a_final_score_below_three_is_refused_even_if_the_bonus_check_let_it_through(self):
        request = rogue_spec()
        request.update(background=BACKGROUND, ability_score_method="manual",
                       ability_scores=dict.fromkeys(ABILITY_KEYS, 3),
                       background_ability_bonuses={PERMITTED[0]: -2, PERMITTED[1]: 1})
        session = SimpleNamespace()
        with patch.object(character_creation, "validate_background_bonuses"), self.assertRaises(CharacterCreationError) as caught:
            character_creation.configure_character(session, mode="custom", **request)
        self.assertIn("at least 3", str(caught.exception))


class TestCreateInputShape(unittest.TestCase):
    """D-313: list sizes and the dictionary keys are bounded in the model, with no change to the published schema."""

    def body(self, **fields):
        return {**BASE_CHARACTER, **fields}

    def test_a_five_thousand_item_list_is_refused_in_every_list_field(self):
        for field in ("proficient_skills", "expertise_skills", "proficient_tools", "species_bonus_skills",
                      "equipment_choices", "cantrips", "spells", "languages"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                CharacterCreateInput.model_validate(self.body(**{field: ["x"] * 5000}))

    def test_a_long_list_entry_is_refused(self):
        with self.assertRaises(ValidationError):
            CharacterCreateInput.model_validate(self.body(languages=["x" * 500]))

    def test_extra_dictionary_keys_are_refused(self):
        scores = dict.fromkeys(ABILITY_KEYS, 10)
        for field in ("ability_scores", "background_ability_bonuses"):
            with self.subTest(field=field):
                CharacterCreateInput.model_validate(self.body(**{field: dict(scores)}))
                with self.assertRaises(ValidationError):
                    CharacterCreateInput.model_validate(self.body(**{field: {**scores, "luck": 1}}))
                with self.assertRaises(ValidationError):
                    CharacterCreateInput.model_validate(self.body(**{field: {f"k{i}": 1 for i in range(5000)}}))

    def test_a_normal_request_still_validates(self):
        CharacterCreateInput.model_validate(self.body(languages=["Elvish", "Dwarvish"], equipment_choices=["Dagger"],
                                                      proficient_skills=["Stealth"]))


class TestOneBlankCheck(unittest.TestCase):
    """D-539: one shared check, same refusal for empty, blank and missing."""

    def test_empty_blank_and_missing_are_refused_with_the_same_text(self):
        for bad in ("", "   ", "\t\n", None):
            with self.subTest(bad=bad), self.assertRaises(ValueError) as caught:
                schemas.require_non_blank(bad, "Thing must not be blank.")
            self.assertEqual(str(caught.exception), "Thing must not be blank.")

    def test_text_comes_back_stripped(self):
        self.assertEqual(schemas.require_non_blank("  ada ", "x"), "ada")

    def test_each_model_keeps_its_own_message(self):
        cases = (
            (lambda: TurnRequest.model_validate({"message": "   ", "action_id": "5b0f6c52-8d0c-4f6e-9d3a-0a1b2c3d4e5f"}), "Message must not be empty."),
            (lambda: TurnRequest.model_validate({"message": "hi", "target_id": "   ", "action_id": "5b0f6c52-8d0c-4f6e-9d3a-0a1b2c3d4e5f"}), "Target ID must not be blank."),
            (lambda: CharacterCreateInput.model_validate({"mode": "custom", "name": "   "}), "Character name must not be blank."),
            (lambda: CampaignCreateRequest.model_validate({"name": "   "}), "Campaign name must not be blank."),
        )
        for build, text in cases:
            with self.subTest(text=text), self.assertRaises(ValidationError) as caught:
                build()
            self.assertIn(text, str(caught.exception))


class TestCampaignHttp(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaigns.CampaignApiTests.asyncSetUp
    asyncTearDown = campaigns.CampaignApiTests.asyncTearDown

    async def test_a_body_over_the_limit_is_413_and_a_normal_one_is_not(self):
        big = b'{"name": "' + b"a" * 300_000 + b'"}'
        with fixed_town(self, TOWN_SEED):
            response = await self.http.post("/api/campaigns", content=big, headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(response.json()["detail"]["code"], "request_too_large")
        with fixed_town(self, TOWN_SEED):
            ok = await self.http.post("/api/campaigns", json={"name": "Small"})
        self.assertEqual(ok.status_code, 200, ok.text)

    async def test_a_five_thousand_item_list_and_extra_keys_are_422(self):
        bad_scores = {**dict.fromkeys(ABILITY_KEYS, 10), "luck": 3}
        for character in ({**BASE_CHARACTER, "languages": ["x"] * 5000},
                          {**BASE_CHARACTER, "ability_scores": bad_scores}):
            with fixed_town(self, TOWN_SEED):
                response = await self.http.post("/api/campaigns", json={"character": character})
            self.assertEqual(response.status_code, 422, response.text)
            # Refused by the request model (a list of field errors), not later by character creation.
            self.assertIsInstance(response.json()["detail"], list)

    async def test_an_existing_campaign_id_is_409_with_its_own_code(self):
        with _campaign_seeded({"campaign_seed": 8421}):
            first = await self.http.post("/api/campaigns", json={"name": "One"})
        self.assertEqual(first.status_code, 200, first.text)
        with _campaign_seeded({"campaign_seed": 8421}):
            second = await self.http.post("/api/campaigns", json={"name": "Two"})
        self.assertEqual(second.status_code, 409, second.text)
        self.assertEqual(second.json()["detail"]["code"], "campaign_id_conflict")


class TestHostedSurface(unittest.IsolatedAsyncioTestCase):
    """D-314: outside local play there are no docs routes and the health body is status only."""

    def adapter(self):
        return SimpleNamespace(model_name="gemma4-fast", model_chain=["cloud-a", "gemma4-fast"],
                               spend_warning=lambda: "3.10 USD today", install_for_engine=lambda: None, cloud_chain=None)

    async def get(self, authenticator, path):
        app = create_app(session_manager=SessionManager(campaign_store=None), ollama_adapter=self.adapter(),
                         authenticator=authenticator)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            return await client.get(path)

    def hosted(self):
        return OidcAuthenticator(OidcSettings("https://issuer.example", "aud", "client", "secret", {"keys": [{}]}))

    async def test_hosted_has_no_docs_routes(self):
        for path in ("/docs", "/redoc", "/openapi.json"):
            with self.subTest(path=path):
                self.assertEqual((await self.get(self.hosted(), path)).status_code, 404)

    async def test_fail_closed_is_hosted_too(self):
        for path in ("/docs", "/redoc", "/openapi.json"):
            with self.subTest(path=path):
                self.assertEqual((await self.get(FailClosedAuthenticator(), path)).status_code, 404)
        response = await self.get(FailClosedAuthenticator(), "/api/health")
        self.assertEqual(set(response.json()), {"status", "engine", "model"})
        self.assertNotIn("x-ai-dnd-instance", response.headers)

    def test_start_local_treats_a_hidden_chain_as_on(self):
        text = (Path(__file__).resolve().parents[3] / "start_local.ps1").read_text(encoding="utf-8")
        helper = text.split("function Test-ChainOn", 1)[1].split("function ", 1)[0]
        self.assertIn("X-AI-DND-Instance", helper)
        self.assertIn("return $true", helper)

    async def test_local_keeps_the_docs_routes(self):
        for path in ("/docs", "/redoc", "/openapi.json"):
            with self.subTest(path=path):
                self.assertEqual((await self.get(FixedAuthenticator(TEST_PLAYER), path)).status_code, 200)

    async def test_hosted_health_has_no_chain_spend_or_process_id(self):
        response = await self.get(self.hosted(), "/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"status", "engine", "model"})
        self.assertNotIn("x-ai-dnd-instance", response.headers)

    async def test_local_health_still_shows_the_chain_and_the_spend_warning(self):
        response = await self.get(FixedAuthenticator(TEST_PLAYER), "/api/health")
        self.assertEqual(response.json()["model_chain"], ["cloud-a", "gemma4-fast"])
        self.assertEqual(response.json()["spend_warning"], "3.10 USD today")
        self.assertIn("x-ai-dnd-instance", response.headers)


def refusal(index, **overrides):
    body = {"draft_id": f"draft-{index}", "field": "nonsense", "request_id": f"bad-{index}", "input_revision": 1}
    body.update(overrides)
    return IdentitySuggestionRequest.model_validate(body)


class TestIdentityRejectionsPerOwner(unittest.TestCase):
    """D-316: one owner's refused requests cannot fill the shared store for the others."""

    def test_forty_refusals_do_not_make_another_owner_storage_full(self):
        service = IdentitySuggestionService(provider=lambda _prompt: "kisa", timeout_seconds=2)
        for index in range(40):
            self.assertEqual(service.submit(refusal(index), PLAYER_A).code, "invalid_field")
        other = service.submit(IdentitySuggestionRequest.model_validate(
            {"draft_id": "d", "field": "personality", "request_id": "ok-1", "input_revision": 1, "current_text": "Sakin."}), PLAYER_B)
        self.assertNotEqual(other.code, "storage_full")
        self.assertEqual(other.status in {"queued", "running", "ready"}, True)

    def test_the_flooding_owner_keeps_a_bounded_number_of_stored_refusals(self):
        service = IdentitySuggestionService(provider=lambda _prompt: "kisa", timeout_seconds=2)
        for index in range(40):
            service.submit(refusal(index), PLAYER_A)
        self.assertLess(len(service._jobs), 32)
