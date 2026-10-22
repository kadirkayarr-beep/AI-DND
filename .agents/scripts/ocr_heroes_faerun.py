from __future__ import annotations

import json
import subprocess
import unicodedata
from pathlib import Path
from external_sources import source_path

import pymupdf


SOURCE = source_path('Forgotten_Realms_-_Heroes_of_Faerun_1790680112925.pdf')
OUTPUT = Path(".agents/outputs/dnd-reference-review")
OUTPUT.mkdir(parents=True, exist_ok=True)
TEXT_OUTPUT = OUTPUT / "heroes-of-faerun-ocr.txt"
INDEX_OUTPUT = OUTPUT / "heroes-of-faerun-ocr-index.json"
KEYWORDS = [
    "Faerûn", "1501 DR", "Year of the Shining Mythal", "Netheril",
    "Mystryl", "Mystra", "Karsus", "Neverwinter", "Waterdeep",
    "Baldur's Gate", "Harpers", "Zhentarim", "Emerald Enclave",
    "Lords' Alliance", "Red Wizards", "background", "subclass", "feat",
    "spell", "species", "hit points", "healing", "death saving throw",
]


def normalized(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


keyword_pages: dict[str, list[int]] = {term: [] for term in KEYWORDS}
doc = pymupdf.open(SOURCE)
page_count = doc.page_count
with TEXT_OUTPUT.open("w", encoding="utf-8") as output:
    for page_index in range(page_count):
        page = doc[page_index]
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(1.5, 1.5),
            colorspace=pymupdf.csGRAY,
            alpha=False,
        )
        if page_index < 12:
            pixmap.save(OUTPUT / f"heroes-faerun-pdf-page-{page_index + 1}.png")

        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "3"],
            input=pixmap.tobytes("png"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=45,
        )
        if result.returncode:
            raise RuntimeError(
                f"Tesseract failed on PDF p.{page_index + 1}: "
                f"{result.stderr.decode(errors='replace')}"
            )
        text = result.stdout.decode("utf-8", errors="replace")
        output.write(f"\n--- PDF page {page_index + 1} ---\n{text}\n")
        normalized_text = normalized(text)
        for term in KEYWORDS:
            if normalized(term) in normalized_text:
                keyword_pages[term].append(page_index + 1)

        if (page_index + 1) % 20 == 0:
            print(f"OCR processed {page_index + 1}/{page_count} pages")
doc.close()

INDEX_OUTPUT.write_text(
    json.dumps(
        {
            "source": str(SOURCE),
            "page_count": page_count,
            "ocr_language": "eng",
            "keyword_pdf_pages": keyword_pages,
            "text_file": str(TEXT_OUTPUT),
            "rendered_sample_pages": list(range(1, 13)),
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print(f"OCR text: {TEXT_OUTPUT}")
print(f"Topic index: {INDEX_OUTPUT}")
for term, pages in keyword_pages.items():
    print(f"{term}: {pages[:45]}{' …' if len(pages) > 45 else ''}")