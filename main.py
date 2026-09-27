from pathlib import Path
import runpy

 
def main():
    """Run the AI-DND terminal game from the workspace entry point."""
    game_file = Path(__file__).resolve().parent / "ai-dnd" / "game.py"
    runpy.run_path(str(game_file), run_name="__main__")

if __name__ == "__main__":
    main()
