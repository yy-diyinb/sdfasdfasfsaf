"""themes.py — 主题加载器"""
import json
from pathlib import Path

COLOR_MAP = {
    "black": 0, "red": 1, "green": 2, "yellow": 3,
    "blue": 4, "magenta": 5, "cyan": 6, "white": 7,
}


class Theme:
    def __init__(self, data, path=None):
        self.name = data.get("name", path.stem if path else "?")
        self.description = data.get("description", "")
        self.symbols = data.get("symbols", {}) or {}
        self.colors = data.get("colors", {}) or {}

    def color(self, key, default="white"):
        return COLOR_MAP.get(self.colors.get(key, default), 7)


def load_theme(path):
    return Theme(json.loads(path.read_text(encoding="utf-8")), path)


def load_all_themes(folder):
    folder = Path(folder)
    out = []
    if folder.exists():
        for f in sorted(folder.glob("*.json")):
            try:
                out.append(load_theme(f))
            except Exception as e:
                print(f"[!] 主题 {f.name} 加载失败: {e}")
    return out
