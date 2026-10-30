"""W04 (D6): an indirect ruler question ("bu şehrin hükümdarı kim?") is answered only through a VERIFIED city link.

The historical ruler fixtures declared the query intent `rulership` and no `current_location_entity_id`, so the real resolver
(`game._supported_lore_question_response`) never saw a verified link between "bu şehir" and a city entity. The factory below
builds the context the resolver actually consumes: query intent `current_ruler`, `diagnostics.current_location_entity_id`,
a `current_lord_id` fact on that city, and verified entities carrying canonical names. Text similarity is never the identity
authority: a missing/wrong link must not invent a ruler, two cities with the same name must not merge, and a former ruler
is not the current one.
"""
from __future__ import annotations

import unittest

import game

QUESTION = "Bu şehrin hükümdarı kim?"


def make_verified_city_ruler_fixture(city_id: str, ruler_id: str, *, city_name: str = "Neverwinter",
                                     ruler_name: str = "Dagult Neverember", linked: bool = True,
                                     extra_cities=(), former_ruler=None) -> dict:
    """Lore-authority context for one city whose current ruler is `ruler_id`; `linked` controls the verified location link."""
    context = game._empty_lore_authority_context()
    facts = [{"fact_id": f"fact:{city_id}:current_lord", "subject_id": city_id, "predicate": "current_lord_id",
              "object_id_or_value": ruler_id, "notes": f"{ruler_name} is the current Lord of {city_name}."}]
    entities = [{"entity_id": city_id, "canonical_name": city_name, "aliases": []},
                {"entity_id": ruler_id, "canonical_name": ruler_name, "aliases": []}]
    for other_city, other_ruler, other_ruler_name in extra_cities:
        facts.append({"fact_id": f"fact:{other_city}:current_lord", "subject_id": other_city, "predicate": "current_lord_id",
                      "object_id_or_value": other_ruler, "notes": f"{other_ruler_name} rules {city_name}."})
        entities += [{"entity_id": other_city, "canonical_name": city_name, "aliases": []},
                     {"entity_id": other_ruler, "canonical_name": other_ruler_name, "aliases": []}]
    if former_ruler:
        former_id, former_name = former_ruler
        facts.append({"fact_id": f"fact:{city_id}:former_lord", "subject_id": city_id, "predicate": "former_lord_id",
                      "object_id_or_value": former_id, "notes": f"{former_name} once ruled {city_name}."})
        entities.append({"entity_id": former_id, "canonical_name": former_name, "aliases": []})
    context["sections"]["official_forgotten_realms_lore"] = facts
    context["sections"]["verified_entities"] = entities
    diagnostics = {"query_intents": ["current_ruler"]}
    if linked:
        diagnostics["current_location_entity_id"] = city_id
    context["diagnostics"] = diagnostics
    return context


def ask(context, question=QUESTION):
    reply = game._supported_lore_question_response(question, context, {"locations": {}, "npcs": [], "features": []})
    if reply is None:
        return ""
    return reply if isinstance(reply, str) else str(reply.get("narration") or reply.get("direct_response") or reply)


class IndirectRulerTests(unittest.TestCase):
    def test_indirect_ruler_requires_verified_city_link(self):
        linked = make_verified_city_ruler_fixture("fr:city:neverwinter", "fr:person:dagult")
        unlinked = make_verified_city_ruler_fixture("fr:city:neverwinter", "fr:person:dagult", linked=False)
        wrong = make_verified_city_ruler_fixture("fr:city:neverwinter", "fr:person:dagult")
        wrong["diagnostics"]["current_location_entity_id"] = "fr:city:elsewhere"
        twin = make_verified_city_ruler_fixture(
            "fr:city:neverwinter", "fr:person:dagult",
            extra_cities=[("campaign:city:neverwinter_twin", "campaign:person:other", "Baska Lord")])
        twin_other = make_verified_city_ruler_fixture(
            "fr:city:neverwinter", "fr:person:dagult",
            extra_cities=[("campaign:city:neverwinter_twin", "campaign:person:other", "Baska Lord")])
        twin_other["diagnostics"]["current_location_entity_id"] = "campaign:city:neverwinter_twin"
        past = make_verified_city_ruler_fixture(
            "fr:city:neverwinter", "fr:person:dagult", former_ruler=("fr:person:old", "Eski Lord"))
        obs = {
            "expected_ruler_id": "fr:person:dagult",
            "verified_city_ruler_id": "fr:person:dagult" if "Dagult Neverember" in ask(linked) else None,
            "missing_city_link_invented_ruler": "Dagult" in ask(unlinked) or "Dagult" in ask(wrong),
            "same_name_cities_merged": ("Baska Lord" in ask(twin)) or ("Dagult" in ask(twin_other))
                                        or ("Baska Lord" not in ask(twin_other)),
            "past_ruler_reported_as_current": "Eski Lord" in ask(past),
        }
        assert obs["verified_city_ruler_id"] == obs["expected_ruler_id"]
        assert obs["missing_city_link_invented_ruler"] is False
        assert obs["same_name_cities_merged"] is False
        self.assertIs(obs["past_ruler_reported_as_current"], False)
        self.assertIn("Dagult Neverember", ask(past), "the current ruler is still reported beside a former one")


if __name__ == "__main__":
    unittest.main()
