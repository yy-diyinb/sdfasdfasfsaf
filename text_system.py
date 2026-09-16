"""text_system.py — 游戏文本系统 mixin"""
import random, curses


class TextSystemMixin:
    def _init_text(self, data):
        self.descriptions = data.get("descriptions", {}) or {}
        self.oracles = data.get("oracles", []) or []
        self.rumors = list(data.get("rumors_true", []) or []) + \
                      list(data.get("rumors_false", []) or [])
        self.engravings = data.get("engravings", []) or []
        self.epitaphs = data.get("epitaphs", []) or []
        self.bogus = data.get("bogus_monsters", []) or []
        self.popup = None
        self.turn = 0

    def _lookup_desc(self, name):
        name = name.lower().strip()
        d = self.descriptions
        if not d: return None
        if name in d: return d[name]
        if name.endswith("s") and name[:-1] in d: return d[name[:-1]]
        for k, v in d.items():
            if k.endswith("*") and name.startswith(k[:-1]): return v
        first = name.split()[0] if name else ""
        for k, v in d.items():
            if k.rstrip("*") == first: return v
        return None

    def _wrap(self, text, width):
        words = text.split()
        lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) + 1 <= width:
                cur = (cur + " " + w).strip()
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
        return lines

    def _show_popup(self, title, body):
        lines = self._wrap(body, self.W - 6) if body else ["(暂无描述)"]
        lines = lines[: self.H - 4]
        self.popup = (title, lines)

    def _look_monster(self, m):
        title = f"{m['name']}  Lv{m['level']}  HP {m['hp']}/{m.get('max_hp', m['hp'])}"
        self._show_popup(title, self._lookup_desc(m["name"]))

    def _look_item(self, it):
        title = f"{it['name']}  [{it['class']}]"
        self._show_popup(title, self._lookup_desc(it["name"]))

    def _look(self):
        for m in self.monsters:
            if m["x"] == self.px and m["y"] == self.py:
                self._look_monster(m); return
        for m in self.monsters:
            if abs(m["x"] - self.px) + abs(m["y"] - self.py) == 1:
                self._look_monster(m); return
        for it in self.items:
            if it["x"] == self.px and it["y"] == self.py:
                self._look_item(it); return
        if self.monsters:
            m = min(self.monsters, key=lambda x: abs(x["x"]-self.px)+abs(x["y"]-self.py))
            self._look_monster(m); return
        if self.items:
            it = min(self.items, key=lambda x: abs(x["x"]-self.px)+abs(x["y"]-self.py))
            self._look_item(it); return
        self._show_popup("你", f"HP {self.hp}/{self.max_hp}  击杀 {self.kills}  得分 {self.score}")

    def _flavor(self):
        pool = []
        if self.rumors:     pool += [("传闻", r) for r in self.rumors]
        if self.engravings: pool += [("刻着", e) for e in self.engravings]
        if self.epitaphs:   pool += [("墓碑", e) for e in self.epitaphs]
        if self.oracles:    pool += [("神谕", o) for o in self.oracles]
        if not pool: return
        kind, txt = pool[random.randrange(len(pool))]
        self.msg = f"{kind}: {txt[:70]}"

    def _draw_popup(self, s, W, H):
        title, lines = self.popup
        widths = [len(title)] + [len(l) for l in lines]
        content_w = max(widths) if widths else 0
        box_w = min(W - 2, max(content_w + 4, 30))
        box_h = len(lines) + 2
        x0 = max(0, (W - box_w) // 2)
        y0 = max(0, (self.H - box_h) // 2)
        try:
            s.addstr(y0, x0, "┌" + "─" * (box_w - 2) + "┐", curses.color_pair(4) | curses.A_BOLD)
            t = " " + title[: box_w - 4] + " "
            s.addstr(y0, x0 + 1, t, curses.color_pair(3) | curses.A_BOLD)
            for i, line in enumerate(lines):
                s.addstr(y0 + 1 + i, x0, "│", curses.color_pair(4) | curses.A_BOLD)
                s.addstr(y0 + 1 + i, x0 + 2,
                         line[: box_w - 4].ljust(box_w - 4), curses.color_pair(5))
                s.addstr(y0 + 1 + i, x0 + box_w - 1, "│", curses.color_pair(4) | curses.A_BOLD)
            s.addstr(y0 + box_h - 1, x0, "└" + "─" * (box_w - 2) + "┘", curses.color_pair(4) | curses.A_BOLD)
        except curses.error:
            pass
