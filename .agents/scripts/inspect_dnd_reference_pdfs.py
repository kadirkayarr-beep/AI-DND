from __future__ import annotations

import re
from pathlib import Path

import fitz


OUTPUT = Path(".agents/outputs/dnd-reference-review")
OUTPUT.mkdir(parents=True, exist_ok=True)

SOURCES = [
    (
        "Dungeon Master's Guide 2024",
        Path("attached_assets/D&D_5e_-_Dungeon_Master_Guide_2024_1790967864536.pdf"),
        ["Netheril", "Forgotten Realms", "campaign", "adventure", "magic item"],
    ),
    (
        "Monster Manual 2024",
        Path("attached_assets/D&D_5e_-_Monster_Manual_2024_1790967864536.pdf"),
        ["Netheril", "lich", "phaerimm", "dragon", "beholder"],
    ),
    (
        "Player's Handbook 2024",
        Path("attached_assets/D&D_5e_-_Players_Handbook_2024_1790967864536.pdf"),
        [
            "Fighting Style",
            "Protection",
            "Defense",
            "Dwarf",
            "Tough",
            "Chain Mail",
            "Scale Mail",
            "Leather Armor",
            "Hit Points",
            "Starting Equipment",
        ],
    ),
    (
        "Forgotten Realms: Netheril's Fall",
        Path("attached_assets/Forgotten_Realms_Netheril_s_Fall_(mostly_here)_1790968211203.pdf"),
        [
            "Netheril",
            "Karsus",
            "Mystryl",
            "Ioulaum",
            "Phaerimm",
            "Anauroch",
            "Thultanthar",
            "Shade",
        ],
    ),
]


def excerpt(text: str, term: str, radius: int = 200) -> str:
    match = re.search(re.escape(term), text, re.IGNORECASE)
    if not match:
        return ""
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def render_page(page: fitz.Page, path: Path) -> None:
    page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False).save(path)


for title, pdf_path, terms in SOURCES:
    document = fitz.open(pdf_path)
    page_texts: list[str] = []
    print(f"\n## {title}")
    print(f"Pages: {document.page_count}; metadata title: {document.metadata.get('title')!r}")
    print(f"First-page text length: {len(document[0].get_text('text'))}")

    for page_number in range(document.page_count):
        page_texts.append(document[page_number].get_text("text"))

    stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    render_page(document[0], OUTPUT / f"{stem}-page-1.png")

    if "Netheril" in title:
        combined = "\n\n".join(
            f"--- PDF page {page_number + 1} ---\n{text}"
            for page_number, text in enumerate(page_texts)
        )
        (OUTPUT / "netheril-full-text.txt").write_text(combined, encoding="utf-8")
        informative_pages = [
            (sum(term.lower() in text.lower() for term in terms), page_number)
            for page_number, text in enumerate(page_texts)
            if len(text.strip()) > 300
        ]
        if informative_pages:
            _, page_number = max(informative_pages)
            render_page(document[page_number], OUTPUT / f"{stem}-content-page-{page_number + 1}.png")

    for term in terms:
        hits = [
            (page_number + 1, text)
            for page_number, text in enumerate(page_texts)
            if re.search(re.escape(term), text, re.IGNORECASE)
        ]
        pages = [page_number for page_number, _ in hits]
        print(f"\n{term}: PDF page(s) {pages[:12]}{' …' if len(pages) > 12 else ''}")
        if hits:
            print(f"  {excerpt(hits[0][1], term)}")

    if "Player's Handbook" in title:
        candidates = [
            (page_number, text)
            for page_number, text in enumerate(page_texts)
            if "protection" in text.lower()
            and "fighting style" in text.lower()
            and len(text) > 500
        ]
        if candidates:
            page_number, _ = candidates[0]
            render_page(document[page_number], OUTPUT / f"{stem}-fighting-styles-page-{page_number + 1}.png")

    print(
        "Non-empty text pages:",
        sum(bool(text.strip()) for text in page_texts),
        "/",
        document.page_count,
    )
    document.close()

print(f"\nRendered samples and targeted text: {OUTPUT}")