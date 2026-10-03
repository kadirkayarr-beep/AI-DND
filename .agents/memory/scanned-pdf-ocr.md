---
name: Scanned PDF OCR
description: Reliable OCR settings for image-only tabletop reference PDFs in this workspace.
---

For scanned reference books, render grayscale pages at about 2.5× and run Tesseract with `--psm 6 --dpi 300`, setting `OMP_THREAD_LIMIT=1` and `OMP_NUM_THREADS=1`. Process pages sequentially; use alternate page-segmentation modes only as fallbacks. Verify important names, dates, and rules against rendered pages because OCR can distort proper nouns.

**Why:** Parallel high-resolution Tesseract jobs saturated CPU and repeatedly timed out, while sequential page processing with one OpenMP thread completed the scanned pages.

**How to apply:** Use this for image-only tabletop PDFs, track every PDF page through completion, and visually verify any extracted fact that will enter the rules or lore catalog.