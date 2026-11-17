"""The engine's source files: game.py plus game_parts/*.py. Tests that read engine text use this, not game.py alone."""
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[2]          # ai-dnd/


def engine_source_files(root: Path = ENGINE_ROOT) -> list[Path]:
    root = Path(root)
    return [root / "game.py"] + sorted((root / "game_parts").glob("*.py"))


def engine_source_text(root: Path = ENGINE_ROOT) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in engine_source_files(root))
