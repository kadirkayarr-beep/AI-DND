---
name: D&D species source versions
description: Edition-labeling and save-compatibility rules for the AI-DND species catalog.
---

Keep Half-Elf and Half-Orc available as 2014 legacy species and identify their source/version separately from 2024 PHB species.

When adding character metadata to versioned save snapshots, make new fields optional when reading older records. Missing species-bonus metadata should default without changing the character's existing proficiencies.

**Why:** The user asked to retain the Half species and enrich the catalog with canonical D&D information while preserving existing-record compatibility.

**How to apply:** Preserve the edition labels and source citations when editing species data; treat new save metadata as optional so pre-existing campaign records continue to load.