"""Replay-safe emergence randomness.

Seeded only from campaign_id and trigger_id. Not wall time, process id,
request id, or session.rng, so combat dice never shift an emergence draw.
"""

from __future__ import annotations

import hashlib
import random


def stream(campaign_id, trigger_id):
    if not isinstance(campaign_id, str) or not campaign_id or not isinstance(trigger_id, str) or not trigger_id:
        raise ValueError("Emergence seed needs a campaign and a trigger.")
    digest = hashlib.sha256(f"{campaign_id}:{trigger_id}".encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest, "big"))


def _weighted(rng, weights):
    labels = [label for label, _ in weights]
    values = [max(0, int(weight)) for _, weight in weights]
    if not labels or sum(values) <= 0:
        rng.random()
        return None
    return rng.choices(labels, weights=values, k=1)[0]


def decide(
    campaign_id,
    trigger_id,
    *,
    silence_rate,
    category_weights,
    reward_weights,
    significance_weights=(("minor", 4), ("notable", 1)),
    candidates=(),
    density_max=1,
):
    """Every draw happens in one fixed order, even when silence wins."""
    rng = stream(campaign_id, trigger_id)
    silent = rng.random() < float(silence_rate)
    significance = _weighted(rng, significance_weights) or "minor"
    category = _weighted(rng, category_weights)
    reward_class = _weighted(rng, reward_weights) or "none"
    rarity = rng.random()
    order = list(candidates)
    rng.shuffle(order)
    density = rng.randint(1, max(1, int(density_max)))
    return {
        "silent": silent or category is None,
        "significance": significance,
        "category": category,
        "reward_class": reward_class,
        "rarity_roll": round(rarity, 6),
        "candidate_order": order,
        "density": density,
    }
