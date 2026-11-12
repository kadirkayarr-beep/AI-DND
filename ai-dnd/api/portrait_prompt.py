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

# Matched on folded text (NFKC, Turkish case, combining marks dropped, Turkish letters to ascii), word by word.
# Beyond this it is a keyword list: the fixed "adult (18+)" line and the provider's own filter are the backstop.
PREFIX_STEMS = (  # a word starting with one of these refuses
    "cocu", "bebe", "ergen", "loli", "shota", "teen", "underage", "infant", "toddler", "schoolgirl", "schoolboy",
    "child", "pubescent", "oglan", "adolescent", "juvenile", "preteen", "prepubescent", "kiddo",
    "ciplak", "cinsel", "erotik", "erotic", "mustehcen", "porn", "naked", "nsfw",
    "topless", "lingerie", "fetis", "fetish", "sehvet", "orgy",
    "disney", "pixar", "pokemon", "adidas", "mcdonald", "celebrit",
)
EXACT_WORDS = (
    "kid", "kids", "minor", "minors", "baby", "meme", "memeler", "memeleri",
    "sex", "sexy", "sexual", "seks", "seksi", "seksuel", "seksual", "nude", "nudes", "nudity", "nudist",
    "breast", "breasts", "boobs", "tits", "underwear", "bikini", "striptiz", "penis", "hentai", "bdsm",
    "marvel", "nike",
)
ALLOWED_WORDS = ("ergenekon",)   # starts with a stem but is a place name
PHRASES = ("resit olmayan", "kucuk kiz", "kucuk oglan", "kucuk cocuk", "yasi kucuk", "ic camasir",
           "little girl", "young girl", "genc kiz", "not an adult", "not adult",
           "unlu bir akt", "unlu akt", "unlu oyuncu", "unlu bir oyuncu", "unlu sarkici", "unlu bir sarkici",
           "star wars", "harry potter", "dc comics", "coca cola")
_EN_NUMBERS = ("one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
               "seventeen")
_NUM = (r"(?:(?<![0-9])(?:1[0-7]|[0-9])(?![0-9])|(?<![a-z0-9])(?:" + _EN_NUMBERS +
        r"|bir|iki|uc|dort|bes|alti|yedi|sekiz|dokuz|on\s+(?:bir|iki|uc|dort|bes|alti|yedi)|on)(?![a-z0-9]))")
# A tens/hundred word before the unit digit word ("otuz bes", "twenty five", "yuz on iki") and "on sekiz"/"on dokuz" are adult ages.
_ADULT_COMPOUND_RE = re.compile(
    r"(?<![a-z])(?:(?:yirmi|otuz|kirk|elli|altmis|yetmis|seksen|doksan|yuz|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
    r"ninety|hundred)[\s\-]+(?:on[\s\-]+)?(?:" + _EN_NUMBERS + r"|bir|iki|uc|dort|bes|alti|yedi|sekiz|dokuz)"
    r"|on\s+(?:sekiz|dokuz))(?![a-z])")
_UNIT = r"(?:y\s*/\s*o|yo|yrs?|years?|yil\w*|yas\w*)(?![a-z])"
UNDER_AGE = (_NUM + r"[\s\-./]*" + _UNIT                                  # 12 years old, on iki yasinda, 12-year-old, 12 y/o
             + r"|(?<![a-z])(?:yasi|yas|aged?)\s*[:=]?\s*" + _NUM                 # yas: 12, age twelve
             + r"|(?<![a-z])(?:under|below)\s+(?:the\s+age\s+of\s+)?(?:18|eighteen)(?![a-z0-9])"
             + r"|(?<![a-z])not\s+(?:an?\s+)?adult|yasindan\s+kucuk"
             + r"|(?<![a-z])looks?\s+(?:like\s+)?(?:an?\s+|about\s+)?(?:" + _EN_NUMBERS + r")(?![a-z])")
PRIVATE = r"https?://|www\.|\S+@\S+\.\S+|\d{6,}"   # matched on the cleaned (not folded) text

_UNDER_AGE_RE = re.compile(UNDER_AGE)
_PRIVATE_RE = re.compile(PRIVATE, re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9]+")
_TR_ASCII = str.maketrans("çğıöşü", "cgiosu")
_LEET = str.maketrans("01345", "oieas")
_LEET_L = str.maketrans("01345", "oleas")   # 1 can stand for i or l
_LOOKALIKE = str.maketrans("асеорхуіјкмтѕοα", "aceopxyijkmtsoa")   # Cyrillic/Greek lookalikes, for the check only
_JOIN_RE = re.compile(r"(?<![a-z0-9])[a-z0-9](?:[\s.\-_*]+[a-z0-9])+(?![a-z0-9])")


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


def _fold_char(ch: str) -> str:
    ch = ch.replace("İ", "i").replace("I", "ı").lower()
    ch = "".join(c for c in unicodedata.normalize("NFD", ch) if unicodedata.category(c) != "Mn")
    return ch.translate(_TR_ASCII)


def _fold(text: str) -> str:
    return "".join(_fold_char(ch) for ch in text)


def _word_hit(folded: str) -> bool:
    words = [w for w in _WORD_RE.findall(folded) if w not in ALLOWED_WORDS]
    if any(w.startswith(PREFIX_STEMS) or w in EXACT_WORDS for w in words):
        return True
    padded = " " + " ".join(words)
    return any(" " + p in padded for p in PHRASES)


def is_forbidden(text: str) -> bool:
    folded = _fold(clean_text(text))
    joined = _JOIN_RE.sub(lambda m: re.sub(r"[\s.\-_*]+", "", m.group()), folded)
    for variant in (folded, joined):
        if _UNDER_AGE_RE.search(_ADULT_COMPOUND_RE.sub("xx", variant)):
            return True
    for variant in (folded, joined):
        looked = variant.translate(_LOOKALIKE)
        if _word_hit(looked) or _word_hit(looked.translate(_LEET)) or _word_hit(looked.translate(_LEET_L)):
            return True
    return False


def _replace_name(text: str, name: str) -> str:
    """Replace the character name, also when it was typed without diacritics or in another case (checked on folded text)."""
    fname = _fold(name)
    if len(fname) < 3:   # Ruling: 1-2 letter names are not replaced; they would mangle ordinary words
        return text
    pieces = [_fold_char(ch) for ch in text]
    starts, folded = [], ""
    for i, piece in enumerate(pieces):
        starts.extend([i] * len(piece))
        folded += piece
    out, last = [], 0
    for m in re.finditer(re.escape(fname), folded):
        first, end = starts[m.start()], starts[m.end() - 1] + 1
        if first >= last:
            out.append(text[last:first] + "the character")
            last = end
    return "".join(out) + text[last:]


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
    text = _replace_name(text, name)
    if _PRIVATE_RE.search(text) or is_forbidden(text):
        return PromptRefusal("portrait_text_refused")
    text = _cap_on_word(text, APPEARANCE_CAP).rstrip(" .,;:") or EMPTY_APPEARANCE
    head = TEMPLATE_HEAD.format(who=_who(species, character_class), appearance=text)
    prompt = head + ". " + STYLE_SUFFIX
    return PortraitPrompt(prompt) if len(prompt) <= PROMPT_CAP else PromptRefusal("portrait_text_refused")
