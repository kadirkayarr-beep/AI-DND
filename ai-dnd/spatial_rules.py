"""Spatial rules owner (K06): the one place for movement cost and cover values.

Sources (D&D 5e - Players Handbook 2024.pdf): p.24 Difficult Terrain costs 1 extra foot per foot (never stacked); p.363
crawling and p.362 climbing cost 1 extra foot per foot, 2 extra feet in Difficult Terrain (that figure already includes the
terrain's own foot), and a Climb Speed ignores the climbing surcharge; p.25 cover: Half +2, Three-Quarters +5 to AC (and Dex
saves; ONLY the AC part is implemented here, the Dexterity-save bonus is not wired yet), Total Cover cannot be targeted
directly, only the most protective degree applies.

This module owns numbers only. Canonical positions and distances stay engine facts (weapon_attack.pair); the map, when it
exists, is a projection of those facts and must call these functions, never carry a second geometry.
"""
from __future__ import annotations

COVER_AC = {"none": 0, "half": 2, "three_quarters": 5}
COVER_RANK = {"none": 0, "half": 2, "three_quarters": 5, "total": 99}


def movement_cost(distance_ft, *, crawling=False, climbing=False, has_climb_speed=False, difficult_terrain=False):
    """Feet of Speed spent to cover `distance_ft` of ground."""
    if type(distance_ft) is not int or distance_ft < 0:
        raise ValueError("Movement distance must be a non-negative integer.")
    extra = int(bool(difficult_terrain)) + int(bool(crawling)) + int(bool(climbing) and not has_climb_speed)
    return distance_ft * (1 + extra)
