import json
from pathlib import Path

HISTORY_DIR = Path("data/history")
LATEST_FILE = HISTORY_DIR / "latest_snapshot.json"


def ensure_history_dir():
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)



def load_previous_snapshot():
    ensure_history_dir()

    if not LATEST_FILE.exists():
        return []

    with open(LATEST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)



def save_current_snapshot(items):
    ensure_history_dir()

    with open(LATEST_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
