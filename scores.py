"""scores.py — 分数持久化与排行榜"""
import json
from pathlib import Path
from datetime import datetime

SCORE_FILE = Path(__file__).parent / "data" / "scores.json"
CONFIG_FILE = Path(__file__).parent / "data" / "config.json"
MAX_ENTRIES = 50


def load_scores():
    if not SCORE_FILE.exists():
        return []
    try:
        return json.loads(SCORE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_scores(scores):
    SCORE_FILE.parent.mkdir(exist_ok=True)
    SCORE_FILE.write_text(json.dumps(scores, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def add_score(name, score, depth, level, kills):
    """插入一条记录，返回 (新榜单, 该记录排名 1-based)"""
    entry = {
        "name": name, "score": int(score), "depth": int(depth),
        "level": int(level), "kills": int(kills),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    scores = load_scores()
    scores.append(entry)
    scores.sort(key=lambda s: (s.get("score", 0), s.get("depth", 0)), reverse=True)
    scores = scores[:MAX_ENTRIES]
    save_scores(scores)
    try:
        rank = scores.index(entry) + 1
    except ValueError:
        rank = None
    return scores, rank


def get_player_name():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text()).get("name", "adventurer")
        except Exception:
            pass
    try:
        name = input("冒险者名字 [adventurer]: ").strip() or "adventurer"
    except Exception:
        name = "adventurer"
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"name": name}), encoding="utf-8")
    return name
