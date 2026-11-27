"""One digest of the whole engine (game.py and game_parts/*.py): what a save records and what the live smokes print (D-346)."""
import hashlib
from pathlib import Path


def engine_files(game_file: Path) -> list[Path]:
    return [game_file] + sorted((game_file.parent / "game_parts").glob("*.py"))


def engine_digest(game_file: Path) -> str:
    digest = hashlib.sha256()
    for path in engine_files(game_file):
        digest.update(path.relative_to(game_file.parent).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()
