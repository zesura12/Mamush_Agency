"""Run the Telegram bot from the repository root (Render-compatible entrypoint)."""

from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).parent / "bot" / "main.py"), run_name="__main__")
