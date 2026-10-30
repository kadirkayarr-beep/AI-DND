"""Referent span classification (W05): a capitalised sentence-initial word is a person only on evidence.

"Bardak durur." (a cup stands) and "Elara durur." (a person stands) look identical to a capitalisation heuristic. The
classifier separates them with evidence instead of one more forbidden word: (1) a canonical registered name wins and carries
its entity id; (2) a word that the scene itself uses as a lowercase common noun, or that is an everyday scene object, is an
object; (3) everything else stays an UNKNOWN name candidate, which the caller keeps rejecting (fail closed).
"""
from __future__ import annotations

import re

# Everyday scene objects only; evidence that a capitalised word is a common noun, never an authority for people.
COMMON_SCENE_OBJECTS = frozenset({
    # words that are also given names (meşale, ocak, kupa, kâse...) are deliberately absent: only scene evidence may clear them
    "bardak", "kadeh", "tabak", "sürahi", "masa", "sandalye", "tezgah", "pencere", "fıçı", "sepet", "çuval", "sandık",
    "şömine", "çömlek", "cup", "mug", "plate", "table", "chair", "candle", "barrel", "bucket", "bench", "window",
    "lantern",
})


def fold(value: str) -> str:
    """Casefold with Turkish dotted/dotless i handled before lowercasing."""
    return str(value).replace("İ", "i").replace("I", "ı").casefold().replace("i̇", "i")


_SUFFIXES = frozenset({
    "", "lar", "ler", "ı", "i", "u", "ü", "ın", "in", "un", "ün", "da", "de", "ta", "te", "dan", "den", "tan", "ten",
    "a", "e", "ya", "ye", "s",
})


def _stem_in(word: str, vocabulary) -> bool:
    # stems shorter than 5 letters must match exactly: "mum"+"i", "masa"+"i" are name-shaped words, not objects
    return any(word == item or (len(item) >= 5 and word.startswith(item) and word[len(item):] in _SUFFIXES)
               for item in vocabulary)


def classify_referent_span(text: str, canonical_ids: dict, context: dict | None = None) -> dict:
    """`text`: the capitalised candidate; `canonical_ids`: {folded name -> entity id}; `context`: {"scene_texts": [str]}.

    Returns {"kind": "canonical_person" | "common_object" | "unknown_name", "entity_id": str | None}.
    """
    word = fold(str(text).strip())
    if word in canonical_ids:
        return {"kind": "canonical_person", "entity_id": canonical_ids[word]}
    scene_words = set()
    for scene_text in (context or {}).get("scene_texts", []):
        if isinstance(scene_text, str):
            # only lowercase uses count: a capitalised word in scene text may itself be a name
            scene_words.update(fold(match) for match in re.findall(r"\b[a-zçğıöşü]{3,}\b", scene_text))
    if _stem_in(word, COMMON_SCENE_OBJECTS) or word in scene_words:
        return {"kind": "common_object", "entity_id": None}
    return {"kind": "unknown_name", "entity_id": None}
