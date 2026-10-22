from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from external_sources import source_path

import fitz


OUTPUT = Path(".agents/outputs/dnd-reference-review")
OUTPUT.mkdir(parents=True, exist_ok=True)

SOURCES = [
    {
        "key": "dmg_2024",
        "title": "D&D 5e Dungeon Master's Guide 2024",
        "path": source_path('D&D_5e_-_Dungeon_Master_Guide_2024_1790967864536.pdf'),
        "terms": [
            "campaign", "adventure", "encounter", "magic item", "attunement",
            "treasure", "downtime", "travel", "faction", "fear", "chase",
        ],
    },
    {
        "key": "mm_2024",
        "title": "D&D 5e Monster Manual 2024",
        "path": source_path('D&D_5e_-_Monster_Manual_2024_1790967864536.pdf'),
        "terms": [
            "challenge rating", "legendary action", "lair action", "goblin",
            "wolf", "skeleton", "zombie", "bandit", "owlbear", "dragon",
            "beholder", "lich", "phaerimm",
        ],
    },
    {
        "key": "phb_2024",
        "title": "D&D 5e Player's Handbook 2024",
        "path": source_path('D&D_5e_-_Players_Handbook_2024_1790967864536.pdf'),
        "terms": [
            "d20 test", "attack roll", "saving throw", "death saving throw",
            "exhaustion", "weapon mastery", "weapon properties", "concentration",
            "short rest", "long rest", "fighting style", "protection",
            "origin feat", "background", "species", "fighter",
        ],
    },
    {
        "key": "adventures_faerun",
        "title": "Forgotten Realms: Adventures in Faerûn",
        "path": source_path('Forgotten_Realms_-_Adventures_in_Faerûn_1790680112924.pdf'),
        "terms": [
            "Faerûn", "Sword Coast", "Neverwinter", "Waterdeep", "Baldur's Gate",
            "Icewind Dale", "Anauroch", "Netheril", "Harpers", "Zhentarim",
            "Lords' Alliance", "Emerald Enclave", "Red Wizards", "faction",
            "adventure", "region", "travel",
        ],
    },
    {
        "key": "heroes_faerun",
        "title": "Forgotten Realms: Heroes of Faerûn",
        "path": source_path('Forgotten_Realms_-_Heroes_of_Faerun_1790680112925.pdf'),
        "terms": [
            "Faerûn", "background", "species", "subclass", "feat", "spell",
            "Harpers", "Zhentarim", "Lords' Alliance", "Emerald Enclave",
            "Red Wizards", "Neverwinter", "Waterdeep", "Baldur's Gate",
        ],
    },
    {
        "key": "netherils_fall",
        "title": "Forgotten Realms: Netheril's Fall",
        "path": source_path('Forgotten_Realms_Netheril_s_Fall_(mostly_here)_1790968211203.pdf'),
        "terms": [
            "Netheril", "Karsus", "Mystryl", "Mystra", "Ioulaum", "phaerimm",
            "Anauroch", "Thultanthar", "City of Shade", "mythallar",
            "Shadowfell", "flying city",
        ],
    },
]


def normalized(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def excerpt(text: str, term: str, radius: int = 230) -> str:
    source = normalized(text)
    needle = normalized(term)
    match = re.search(re.escape(needle), source)
    if not match:
        return ""
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


results: list[dict[str, object]] = []
for source in SOURCES:
    path = source["path"]
    document = fitz.open(path)
    page_count = document.page_count
    terms: dict[str, dict[str, object]] = {
        term: {"count": 0, "pdf_pages": [], "examples": []}
        for term in source["terms"]
    }
    nonempty_pages = 0
    empty_pages: list[int] = []
    text_chars = 0
    toc = document.get_toc()

    cover_path = OUTPUT / f"{source['key']}-pdf-page-1.png"
    document[0].get_pixmap(matrix=fitz.Matrix(0.8, 0.8), alpha=False).save(cover_path)

    for page_index in range(page_count):
        text = document[page_index].get_text("text", sort=True)
        if text.strip():
            nonempty_pages += 1
            text_chars += len(text)
        else:
            empty_pages.append(page_index + 1)

        normalized_page = normalized(text)
        for term, hit_info in terms.items():
            needle = normalized(term)
            matches = list(re.finditer(re.escape(needle), normalized_page))
            if not matches:
                continue
            hit_info["count"] = int(hit_info["count"]) + len(matches)
            pages = hit_info["pdf_pages"]
            if len(pages) < 40:
                pages.append(page_index + 1)
            examples = hit_info["examples"]
            if len(examples) < 4:
                examples.append(
                    {"pdf_page": page_index + 1, "text": excerpt(text, term)}
                )

    result = {
        "key": source["key"],
        "title": source["title"],
        "path": str(path),
        "pdf_metadata": document.metadata,
        "page_count": page_count,
        "text_pages_nonempty": nonempty_pages,
        "text_pages_empty": empty_pages,
        "text_character_count": text_chars,
        "pdf_toc": toc,
        "term_index": terms,
        "cover_image": str(cover_path),
    }
    results.append(result)
    document.close()

    print(
        f"\n## {source['title']}\n"
        f"pages={page_count}; text_pages={nonempty_pages}; "
        f"empty_text_pages={len(empty_pages)}; chars={text_chars}; "
        f"metadata_title={result['pdf_metadata'].get('title')!r}"
    )
    if toc:
        print("PDF outline:")
        for level, title, page in toc[:100]:
            print(f"  {'  ' * (level - 1)}{title} [PDF p. {page}]")
        if len(toc) > 100:
            print(f"  ... {len(toc) - 100} additional outline entries")
    else:
        print("PDF outline: none")
    print("Selected topic index:")
    for term, info in terms.items():
        pages = info["pdf_pages"]
        print(
            f"  {term}: {info['count']} hits; PDF pages "
            f"{pages[:24]}{' …' if len(pages) > 24 else ''}"
        )
        for example in info["examples"][:1]:
            print(f"    p.{example['pdf_page']}: {example['text']}")

(OUTPUT / "corpus-index.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"\nSaved page-level index and cover renders under {OUTPUT}")