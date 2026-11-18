"""The engine's source files: game.py plus game_parts/*.py. Tests that read engine text use this, not game.py alone."""
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[2]          # ai-dnd/
BATCH_DIR = ENGINE_ROOT / "scripts" / "engine_split" / "batches"


def engine_source_files(root: Path = ENGINE_ROOT) -> list[Path]:
    root = Path(root)
    return [root / "game.py"] + sorted((root / "game_parts").glob("*.py"))


def engine_source_text(root: Path = ENGINE_ROOT) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in engine_source_files(root))


def batch_names(batch: str) -> list[str]:
    """The names of one Plan 2 move batch (scripts/engine_split/batches/<batch>.txt, one per line), in file order."""
    text = (BATCH_DIR / f"{batch}.txt").read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]
