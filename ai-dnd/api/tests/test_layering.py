"""G2.11 (D-590, D-583): the import-linter layer rules, read from source.

The contracts live in docs/agents/kalite-taramasi-20261125/importlinter.ini. The
test slots have no import-linter, so both rules are checked here from the import
statements, lazy imports included:
  1. no api.routes_* module reaches another api.routes_* module, by any chain;
  2. the engine does not import api; open edges are listed and may only shrink.
"""
import ast
import importlib
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2]
ROOT_PACKAGES = ("api", "game_parts", "adventure", "class_progression", "incidents")
ENGINE_PACKAGES = ROOT_PACKAGES[1:]

# Flat engine modules that still import api. Each needs a ports layer (model usage
# counters, character creation) or is a live script that drives the api on purpose.
# A removed edge must leave this list: the test fails on a stale entry.
FLAT_EDGES_LEFT = {
    "arrival_narration -> api.ollama_adapter",
    "character_progression -> api.character_creation",
    "front_proposal -> api.ollama_adapter",
    "live_integration_test -> api.ollama_adapter",
    "live_phase_c_narrative_smoke -> api.narrative_director",
    "live_phase_c_narrative_smoke -> api.narrative_memory",
}

# Direct engine-package -> api imports that still exist (lore authority, model
# adapter, narration helpers). Same list as ignore_imports in importlinter.ini.
PACKAGE_EDGES_LEFT = {
    "adventure.play -> api.lore_authority.campaign_state",
    "adventure.play -> api.lore_authority.models",
    "adventure.projection -> api.lore_authority.player_knowledge",
    "adventure.projection -> api.lore_authority.registry",
    "adventure.rewards -> api.lore_authority.campaign_state",
    "game_parts.dialogue -> api.ollama_adapter",
    "game_parts.narration -> api.ollama_adapter",
    "game_parts.narration -> api.opening_narrative",
    "game_parts.narration -> api.world_metadata",
    "game_parts.resolved_narration -> api.lore_authority.claim_authorization",
    "game_parts.text_rules_b -> api.lore_authority.claim_authorization",
    "game_parts.turn_front -> api.ollama_adapter",
    "incidents.arbiter -> api.ollama_adapter",
    "incidents.faction -> api.lore_authority.campaign_state",
    "incidents.faction -> api.lore_authority.models",
    "incidents.npcs -> api.lore_authority",
    "incidents.npcs -> api.lore_authority.models",
    "incidents.possibilities -> api.lore_authority.campaign_state",
    "incidents.possibilities -> api.lore_authority.models",
    "incidents.profiles -> api.lore_authority.models",
    "incidents.profiles -> api.lore_authority.pack_loader",
}


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ENGINE).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _root_modules() -> dict[str, Path]:
    found = {}
    for package in ROOT_PACKAGES:
        for path in sorted((ENGINE / package).rglob("*.py")):
            if "tests" not in path.relative_to(ENGINE).parts:
                found[_module_name(path)] = path
    return found


def _imported(path: Path) -> set[str]:
    """Return every module name this file imports, lazy imports included.

    `from api import m` names api.m.
    """
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == "api":
                names.update(f"api.{alias.name}" for alias in node.names)
            else:
                names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def _api_edges(sources: dict[str, Path]) -> set[str]:
    """Return `source -> api...` for every import of api in the given modules."""
    return {
        f"{module} -> {name}"
        for module, path in sources.items()
        for name in _imported(path)
        if name == "api" or name.startswith("api.")
    }


def _package_edges() -> set[str]:
    modules = _root_modules()
    engine = [m for m in modules if m.split(".")[0] in ENGINE_PACKAGES]
    return _api_edges({m: modules[m] for m in engine})


def _flat_edges() -> set[str]:
    """List flat edges by the rule of engine_api_edges.py (slots carry no docs/)."""
    flat = {
        path.stem: path
        for path in sorted(ENGINE.glob("*.py"))
        if not path.stem.startswith("test_")
        and path.stem not in {"acceptance_test", "conftest"}
    }
    return _api_edges(flat)


def _reachable(graph: dict[str, set[str]], source: str) -> set[str]:
    seen: set[str] = set()
    todo = [source]
    while todo:
        for target in graph[todo.pop()] - seen:
            seen.add(target)
            todo.append(target)
    return seen


def _routes_reaching_routes() -> list[str]:
    modules = _root_modules()
    graph = {
        name: {n for n in _imported(path) if n in modules}
        for name, path in modules.items()
    }
    routes = [name for name in modules if name.startswith("api.routes_")]
    return [
        f"{source} -> {other}"
        for source in routes
        for other in sorted(_reachable(graph, source))
        if other != source and other in routes
    ]


class TestRoutesDoNotReachEachOther(unittest.TestCase):
    """Contract api.routes_* modules do not import each other."""

    def test_no_routes_module_reaches_another_routes_module(self) -> None:
        """No chain of imports joins two routes modules."""
        if _routes_reaching_routes() != []:
            self.fail("_routes_reaching_routes() differs from []")


class TestEngineDoesNotImportApi(unittest.TestCase):
    """Contract engine packages do not import api, with the listed edges still open."""

    def test_flat_engine_edges_are_only_the_listed_ones(self) -> None:
        """A removed edge must leave the list; a new edge fails."""
        if _flat_edges() != FLAT_EDGES_LEFT:
            self.fail("_flat_edges() differs from FLAT_EDGES_LEFT")

    def test_engine_package_edges_are_only_the_listed_ones(self) -> None:
        """The list matches the ignore_imports list of importlinter.ini."""
        if _package_edges() != PACKAGE_EDGES_LEFT:
            self.fail("_package_edges() differs from PACKAGE_EDGES_LEFT")

    def test_rules_module_is_in_the_engine_and_the_old_path_is_the_same(self) -> None:
        """A patch on the old api path still reaches the engine."""
        engine_side = importlib.import_module("dnd_2024_rules")
        if importlib.import_module("api.dnd_2024_rules") is not engine_side:
            self.fail("old api path is not the engine module")
        if engine_side.__name__ != "dnd_2024_rules":
            self.fail("engine module has the wrong name")


if __name__ == "__main__":
    unittest.main()
