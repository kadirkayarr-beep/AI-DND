"""Fixed English portrait prompt (portrait P1, Task 1). Pure: no I/O, no network, no engine state.

Only the text built here ever leaves the machine. The character name is never sent, and a refused text is never echoed.
HTTP texts for the codes live in refusals.REFUSAL_TEXT and are looked up in api/main.py (not here)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import game

TEMPLATE_HEAD = "Head-and-shoulders portrait of an adult (18+) {who}, fantasy character. Appearance: {appearance}"
STYLE_SUFFIX = ("hand-inked portrait on aged parchment, book-page illustration, muted warm palette, "
                "head and shoulders, no text, no signature, no border, no watermark, fully clothed, "
                "Forgotten Realms fantasy")
APPEARANCE_CAP = 600
PROMPT_CAP = 1200
EMPTY_APPEARANCE = "as described by species and class"

PORTRAIT_ERROR_CODES = (
    "portrait_disabled", "portrait_text_refused", "portrait_limit_reached", "portrait_daily_cap",
    "portrait_budget_unavailable", "portrait_service_refused", "portrait_service_failed",
    "portrait_busy", "portrait_not_found", "portrait_storage_failed",
)

PREFIX_STEMS = (  # a word starting with one of these refuses
    "cocu", "bebe", "ergen", "loli", "shota", "teen", "underage", "infant", "toddler", "schoolgirl", "schoolboy",
    "ciplak", "cinsel", "seks", "sex", "erotik", "erotic", "mustehcen", "porn", "nud", "naked", "nsfw",
    "topless", "lingerie", "fetis", "fetish", "sehvet", "orgy",
    "disney", "marvel", "pixar", "pokemon", "nike", "adidas", "mcdonald", "celebrit", "unlu",
)
EXACT_WORDS = ("kid", "kids", "child", "children", "minor", "minors", "baby", "meme", "memeler", "memeleri")
PHRASES = ("resit olmayan", "kucuk kiz", "kucuk oglan", "kucuk cocuk", "yasi kucuk", "ic camasir",
           "star wars", "harry potter", "dc comics", "coca cola")
UNDER_AGE = r"\b([0-9]|1[0-7])\s*(yas|yasinda|yasindaki|year|years|yo)\b|\b(yas|age)\s*:?\s*([0-9]|1[0-7])\b"
PRIVATE = r"https?://|www\.|\S+@\S+\.\S+|\d{6,}"   # matched on the cleaned (not folded) text

_UNDER_AGE_RE = re.compile(UNDER_AGE)
_PRIVATE_RE = re.compile(PRIVATE, re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9]+")
_TR_ASCII = str.maketrans("çğıöşü", "cgiosu")


@dataclass(frozen=True)
class PortraitPrompt:
    text: str


@dataclass(frozen=True)
class PromptRefusal:
    code: str = "portrait_text_refused"


def clean_text(text: str) -> str:
    """NFKC, control/format characters dropped (newline and tab become a space), whitespace collapsed."""
    out = []
    for ch in unicodedata.normalize("NFKC", text or ""):
        if ch in "\n\t":
            out.append(" ")
        elif not unicodedata.category(ch).startswith("C"):
            out.append(ch)
    return " ".join("".join(out).split())


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("İ", "i").replace("I", "ı").lower()
    return text.translate(_TR_ASCII)


def is_forbidden(text: str) -> bool:
    folded = _fold(clean_text(text))
    words = _WORD_RE.findall(folded)
    if any(w.startswith(PREFIX_STEMS) or w in EXACT_WORDS for w in words):
        return True
    joined = " ".join(words)
    if any(p in joined for p in PHRASES):
        return True
    return bool(_UNDER_AGE_RE.search(folded))


def _cap_on_word(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    cut = text[:cap + 1].rfind(" ")
    return (text[:cut] if cut > 0 else text[:cap]).rstrip()


def _who(species: str | None, character_class: str | None) -> str:
    race = next((r for r in game.RACES if r.lower() == clean_text(species or "").lower()), None)
    klass = next((c for c in game.CLASSES if c.lower() == clean_text(character_class or "").lower()), None)
    return f"{race.lower()} {klass.lower()}" if race and klass else "adventurer"


def build_portrait_prompt(*, species: str | None, character_class: str | None, appearance: str | None,
                          character_name: str | None) -> PortraitPrompt | PromptRefusal:
    text = clean_text(appearance or "")
    name = clean_text(character_name or "")
    if len(name) >= 3:
        text = re.sub(re.escape(name), "the character", text, flags=re.IGNORECASE)
    if _PRIVATE_RE.search(text) or is_forbidden(text):
        return PromptRefusal("portrait_text_refused")
    text = _cap_on_word(text, APPEARANCE_CAP).rstrip(" .,;:") or EMPTY_APPEARANCE
    head = TEMPLATE_HEAD.format(who=_who(species, character_class), appearance=text)
    prompt = head + ". " + STYLE_SUFFIX
    return PortraitPrompt(prompt) if len(prompt) <= PROMPT_CAP else PromptRefusal("portrait_text_refused")
