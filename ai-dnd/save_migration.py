"""Explicit engine-save migration.

Ordinary load and save never call this module. A failed migration does not
modify the source file.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import game
import spells


_MIGRATIONS = {(3, 4), (3, 5), (4, 5)}
_SPELL_FIELDS = ("cantrips", "spells", "spell_slots_remaining")


def migrate_save_payload(payload: dict[str, Any], target_version: int) -> dict[str, Any]:
    """Return a validated payload at target_version. The input is not mutated."""
    if not isinstance(payload, dict):
        raise ValueError("Kayıt dosyası bir JSON nesnesi olmalı.")
    source = copy.deepcopy(payload)
    game._validate_save_payload(source)
    current = source.get("version")
    if (current, target_version) not in _MIGRATIONS:
        raise ValueError("Bu kayıt göçü desteklenmiyor.")

    migrated = copy.deepcopy(source)
    player = migrated["player"]
    if "xp" not in player:
        player["xp"] = 0
    if current < 4:
        _fill_absent_spell_fields(player)
    migrated["version"] = target_version
    game._validate_save_payload(migrated)
    return migrated


def migrate_save_file(source: Path | str, destination: Path | str, target_version: int) -> Path:
    """Write a migrated copy. The source bytes stay unchanged."""
    source_path = Path(source).expanduser()
    destination_path = Path(destination).expanduser()
    if source_path.resolve() == destination_path.resolve():
        raise ValueError("Göç hedefi kaynak dosyanın üzerine yazılamaz.")
    original = source_path.read_bytes()
    try:
        payload = json.loads(original.decode("utf-8"))
        migrated = migrate_save_payload(payload, target_version)
        _write_payload(destination_path, migrated)
        return destination_path
    finally:
        if source_path.read_bytes() != original:
            raise RuntimeError("Göç kaynak dosyayı değiştirdi.")


def _fill_absent_spell_fields(player: dict[str, Any]) -> None:
    """Encode a v3 file's absent spell block as the canonical empty v4 state.

    A feat that was not stored is left absent. A partial spell block is rejected
    instead of being completed from guesswork.
    """
    present = [field for field in _SPELL_FIELDS if field in player]
    if not present:
        player.update(copy.deepcopy(spells.empty_spell_state()))
        return
    if len(present) != len(_SPELL_FIELDS):
        raise ValueError("Kayıt büyü alanları eksik; göç eksik alanı uyduramaz.")


def _write_payload(destination: Path, payload: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
