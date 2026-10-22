# Optional external reference books

The game uses the reviewed lore packs committed under `ai-dnd/api/lore_authority/packs`; it does not load the owner-provided PDF books during gameplay. UI portrait assets remain in `attached_assets/generated_images`.

Keep legally obtained reference books outside this checkout. Set `AI_DND_REFERENCE_DIR` to a directory containing the original PDF filenames listed in `.agents/scripts/external-books.json`. This optional setting is for research tools only and is not an authentication or runtime provider setting. No personal path is committed.

Explicit full-material check from the repository root:

```powershell
python .agents/scripts/external_sources.py --source-dir <external-book-directory>
```

All seven expected PDF identities must match size and SHA256. Missing files, wrong headers and mismatched hashes fail; absent configuration is an error, never a silent skip. Research scripts `inspect_dnd_reference_pdfs.py`, `review_reference_corpus.py` and `ocr_heroes_faerun.py` use the same environment setting. Their existing optional PDF/OCR dependencies are unchanged.

Default campaign-start tests still enforce the exact two reviewed source IDs, filenames/hash metadata, page citation shape, gated publication, allowed start catalog and API/persistence behavior. Reading full proprietary book bytes is now the separate explicit command above, not a prerequisite of default CI. Run the verifier's synthetic corruption/missing-file/path-boundary checks with:

```powershell
python -m unittest discover -s .agents/scripts -p test_external_sources.py
```

The owner has local hash-verified source-to-destination manifests outside Git. Historical reports and corpus indexes retain original filenames/paths as provenance; resolve books through the external directory now. Legacy RAR deliveries and temporary PDF fragments are archival material, not game dependencies. No Git history or historical LFS objects were rewritten/pruned. Removing these files from the current tree does not automatically reclaim `.git/lfs` storage.
