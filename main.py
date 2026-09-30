from pathlib import Path
import runpy
import sys


def main():
    """Run the AI-DND terminal game from the workspace entry point."""
    ai_dnd_dir = Path(__file__).resolve().parent / "ai-dnd"
    game_file = ai_dnd_dir / "game.py"
    dir_str = str(ai_dnd_dir)
    added = False
    if dir_str not in sys.path:
        sys.path.insert(0, dir_str)
        added = True
    try:
        runpy.run_path(str(game_file), run_name="__main__")
    finally:
        if added and dir_str in sys.path:
            sys.path.remove(dir_str)


if __name__ == "__main__":
    main()
