"""Direct unit tests for api.routes_catalog: the read-only catalog routes keep their paths and payloads."""

import unittest

import game
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dnd_2024_rules import get_character_creation_catalog
from api.lore_authority import PRODUCTION_START_CATALOG
from api.routes_catalog import register_catalog_routes

PATHS = (
    "/api/game/character-options",
    "/api/character-options",
    "/api/game/character-creation-catalog",
    "/api/character-creation-catalog",
    "/api/game/campaign-start-options",
    "/api/campaign-start-options",
)


class CatalogRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        register_catalog_routes(app)
        cls.app = app
        cls.client = TestClient(app)

    def test_every_catalog_path_is_registered_once_and_read_only(self):
        registered = {}
        for route in self.app.routes:
            if route.path in PATHS:
                registered.setdefault(route.path, []).append(sorted(route.methods))
        self.assertEqual(sorted(registered), sorted(PATHS))
        for path, methods in registered.items():
            self.assertEqual(methods, [["GET"]], path)

    def test_character_options_list_the_game_races_and_classes(self):
        for path in PATHS[:2]:
            body = self.client.get(path).json()
            self.assertEqual(body, {"races": list(game.RACES), "classes": list(game.CLASSES)})

    def test_legacy_and_game_paths_answer_the_same(self):
        for legacy, current in zip(PATHS[1::2], PATHS[0::2]):
            self.assertEqual(self.client.get(legacy).json(), self.client.get(current).json())

    def test_character_creation_catalog_is_the_rules_catalog(self):
        response = self.client.get(PATHS[2])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), set(get_character_creation_catalog()))

    def test_start_options_come_from_the_production_catalog(self):
        response = self.client.get(PATHS[4])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), set(PRODUCTION_START_CATALOG.to_response()))

    def test_write_methods_are_refused(self):
        for path in PATHS:
            self.assertEqual(self.client.post(path).status_code, 405, path)


if __name__ == "__main__":
    unittest.main()
