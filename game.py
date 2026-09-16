#!/usr/bin/env python3
"""Roguelike · NetHack 数据 + 多关卡 + RL 脚本 + 主题 + 文本"""
import curses, json, random
from pathlib import Path
from text_system import TextSystemMixin
from rl_lang import RLEngine, RLError, TurnEnd
from themes import load_all_themes, Theme
from scores import load_scores, add_score, get_player_name
from particles import Particles
from lang import tr, dwidth, pad, truncate
from races import RACES, load_player_race, save_player_race, get as get_race

DATA_FILE   = Path(__file__).parent / "data" / "nethack_data.json"
SAVE_FILE   = Path(__file__).parent / "save.json"

PRICE_BASE = {
    "WEAPON": 5, "ARMOR": 5, "POTION": 3, "SCROLL": 3,
    "WAND": 8, "RING": 8, "AMULET": 10, "GEM": 4,
    "FOOD": 2, "TOOL": 3, "SPBOOK": 10,
}

DUNGEON_THEMES = [
    {"name": "地牢", "floor": ".", "corr": "#",
     "mon_mul": 1.0, "item_mul": 1.0, "desc": "古老的地牢"},
    {"name": "矿洞", "floor": "·", "corr": "░",
     "mon_mul": 1.2, "item_mul": 1.3, "desc": "矿石与哥布林"},
    {"name": "精灵森林", "floor": "\"", "corr": ";",
     "mon_mul": 0.8, "item_mul": 1.5, "desc": "树木与精灵"},
    {"name": "深渊", "floor": ".", "corr": ":",
     "mon_mul": 1.5, "item_mul": 0.7, "desc": "恶魔的领域"},
    {"name": "亡灵领域", "floor": ",", "corr": ".",
     "mon_mul": 1.3, "item_mul": 1.0, "desc": "死者的地盘"},
]
SCRIPT_FILE = Path(__file__).parent / "scripts" / "explorer.rl"
THEMES_DIR  = Path(__file__).parent / "themes"

FALLBACK_SYM = {
    "S_stone":" ","S_vwall":"|","S_hwall":"-","S_crwall":"+",
    "S_floor":".","S_corr":"#","S_dnstair":">",
    "S_ant":"a","S_dog":"d","S_feline":"f","S_humanoid":"h","S_orc":"o",
    "S_rodent":"r","S_spider":"s","S_dragon":"D","S_demon":"&",
}
FALLBACK_MON = [
    {"name":"giant ant","symbol_key":"S_ant","level":2},
    {"name":"jackal","symbol_key":"S_dog","level":1},
    {"name":"kobold","symbol_key":"S_humanoid","level":1},
    {"name":"sewer rat","symbol_key":"S_rodent","level":1},
]
FALLBACK_ITEM = [
    {"name":"long sword","class":"WEAPON","char":")"},
    {"name":"potion of healing","class":"POTION","char":"!"},
    {"name":"food ration","class":"FOOD","char":"%"},
    {"name":"gold piece","class":"COIN","char":"$"},
]


def load_data():
    if not DATA_FILE.exists():
        return {"symbols":{"default":FALLBACK_SYM}, "monsters":FALLBACK_MON, "items":FALLBACK_ITEM}
    d = json.loads(DATA_FILE.read_text())
    if not d.get("symbols", {}).get("default"):
        d.setdefault("symbols", {})["default"] = FALLBACK_SYM
    if not d.get("monsters"): d["monsters"] = FALLBACK_MON
    if not d.get("items"):    d["items"]    = FALLBACK_ITEM
    if not isinstance(d.get("descriptions"), dict): d["descriptions"] = {}
    for key in ("oracles", "rumors_true", "rumors_false",
                "engravings", "epitaphs", "bogus_monsters"):
        if not isinstance(d.get(key), list): d[key] = []
    return d


C_WALL, C_MON, C_PLR, C_BAR, C_MSG = 1, 2, 3, 4, 5
C_ITEM, C_MAGIC, C_GOLD, C_FOOD = 6, 7, 8, 9


class Game(TextSystemMixin):
    W, H = 60, 22

    ITEM_COLOR = {
        "WEAPON": C_ITEM, "ARMOR": C_ITEM, "TOOL": C_ITEM,
        "RING": C_MAGIC, "AMULET": C_MAGIC, "POTION": C_MAGIC,
        "SCROLL": C_MAGIC, "SPBOOK": C_MAGIC, "WAND": C_MAGIC, "GEM": C_MAGIC,
        "COIN": C_GOLD, "FOOD": C_FOOD,
    }

    WEAPON_TIERS = [
        ("vorpal", 11), ("excalibur", 10),
        ("crystal", 8), ("runed", 7),
        ("two-handed", 7), ("katana", 6), ("tsurugi", 7),
        ("long sword", 5), ("battle-axe", 5), ("war hammer", 5),
        ("silver saber", 5), ("scimitar", 4), ("broadsword", 4),
        ("mace", 3), ("axe", 3), ("trident", 3), ("lance", 3),
        ("short sword", 2), ("spear", 2), ("quarterstaff", 2),
        ("dagger", 1), ("knife", 1), ("club", 1), ("whip", 1),
        ("dart", 0), ("arrow", 0), ("shuriken", 0), ("boomerang", 1),
    ]
    ARMOR_TIERS = [
        ("dragon scale mail", 9), ("crystal plate mail", 8),
        ("plate mail", 7), ("splint mail", 6), ("banded mail", 5),
        ("chain mail", 4), ("scale mail", 3), ("ring mail", 2),
        ("studded leather", 2), ("leather armor", 1),
        ("leather jacket", 1), ("robe", 1), ("cloak", 1),
        ("helmet", 1), ("shield", 2),
    ]
    RANGED_KEYS = {"S_DRAGON", "S_DEMON", "S_EYE", "S_VORTEX", "S_LIGHT",
                   "S_WAND", "S_COCKATRICE", "S_IMP"}
    SHIELD_KEYS = {"S_GIANT", "S_GOLEM", "S_TRAPPER", "S_JELLY", "S_MIMIC",
                   "S_ANT", "S_QUADRUPED"}

    def __init__(self, data, race_key=None):
        self.sym = data["symbols"].get("default", {})
        self.mon_pool = self._build_pool(data.get("monsters", []))
        self.item_pool = self._build_item_pool(data.get("items", []))

        self.base_sym = dict(self.sym)
        self.themes = load_all_themes(THEMES_DIR)
        if not self.themes:
            self.themes = [Theme({"name": "Default", "symbols": {}, "colors": {}})]
        self.theme_idx = 0
        self._apply_theme(self.themes[0])

        # 玩家状态（跨层保留）
        self.player_name = getattr(self, 'player_name', 'adventurer')
        self._death_recorded = False
        self.death_rank = None
        self.hp, self.max_hp = 20, 20
        self.kills, self.score = 0, 0
        self.level, self.exp = 1, 0
        self.exp_next = 5
        self.depth = 1
        self.dead = False

        # 物品栏
        self.inventory = []
        self.weapon = None
        self.armor = None
        self.atk_bonus = 0
        self.def_bonus = 0

        # 背包界面状态
        self.inv_open = False
        self.inv_cursor = 0

        # 粒子
        self.particles = Particles()

        # 种族
        self.race_key = race_key if race_key else load_player_race()
        self.race = get_race(self.race_key)
        self.max_hp += self.race["hp"]
        self.hp = self.max_hp
        self.race_atk = self.race["atk"]
        self.race_def = self.race["def"]
        self.atk_bonus += self.race_atk
        self.def_bonus += self.race_def
        self.race_skill_cd = 0


        # 显形
        self.reveal_turns = 0
        self.invuln_turns = 0

        # 护盾法印 / 祭坛临时加成（本层有效）
        self.temp_def_bonus = 0
        self.temp_atk_bonus = 0

        # 祭坛 / 陷阱
        self.altars = []
        self.traps  = {}
        self.poison_turns = 0

        # 地牢主题
        self.dungeon_theme_idx = 0
        self.dungeon_name = "地牢"

        # 金币 / 商店
        self.gold = 0
        self.shop_open = False
        self.shop_items = []
        self.shop_cursor = 0
        self.shop_mode = "buy"
        self.shop_pos = None

        # Boss 层
        self.boss = None
        self.boss_warned = False
        self.won = False

        # 文本系统
        self.msg = "hjkl/n 移 | i 包 | R 种族技 | l 查 | s 脚本 | T 主题 | H 榜 | q 退"
        self._init_text(data)

        # 关卡
        self.rooms = []
        self._new_level(first=True)

        # 脚本
        self.script = None
        self.auto_mode = False
        self.script_error = ""
        self._load_script()

    def _build_pool(self, mlist):
        pool = []
        for m in mlist:
            key = m.get("symbol_key", "")
            ch = self.sym.get(key)
            if not ch:
                continue
            if key in self.RANGED_KEYS:   role = "ranged"
            elif key in self.SHIELD_KEYS: role = "shield"
            else:                         role = "melee"
            pool.append({"name": m["name"], "char": ch, "level": m.get("level", 1),
                         "symbol_key": key, "role": role})
        if not pool:
            pool = [{"name": m["name"], "char": FALLBACK_SYM.get(m["symbol_key"], "?"),
                     "level": m["level"], "role": "melee"} for m in FALLBACK_MON]
        return pool

    def _build_item_pool(self, ilist):
        pool = [{"name": it["name"], "char": it["char"], "class": it.get("class", "TOOL")}
                for it in ilist if it.get("char")]
        return pool or FALLBACK_ITEM

    def _refresh_symbols(self):
        s = self.sym
        self.stone = s.get("S_stone", " ")
        self.floor = s.get("S_floor", ".")
        self.corr  = s.get("S_corr", "#")
        self.vwall = s.get("S_vwall", "|")
        self.hwall = s.get("S_hwall", "-")
        self.crwall= s.get("S_crwall", "+")
        self.walls = {self.vwall, self.hwall, self.crwall}
        self.dnstair_char = s.get("S_dnstair", ">")
        self.altar_char   = s.get("S_altar", "_")
        self.trap_char    = s.get("S_trap", "^")
        self.walkable = {self.floor, self.corr, "__STAIR__",
                         "__ALTAR__", "__TRAP__"}

    def _apply_theme(self, theme):
        self.theme = theme
        self.sym = dict(self.base_sym)
        self.sym.update(theme.symbols)
        self._refresh_symbols()

    def _cycle_theme(self):
        self.theme_idx = (self.theme_idx + 1) % len(self.themes)
        self._apply_theme(self.themes[self.theme_idx])
        self._init_colors()
        self.msg = f"主题: {self.theme.name}"

    def _carve_room(self, m, x, y, w, h):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                m[yy][xx] = self.floor
        for xx in range(x - 1, x + w + 1):
            if 0 <= xx < self.W:
                if y - 1 >= 0 and m[y - 1][xx] == self.stone: m[y - 1][xx] = self.hwall
                if y + h < self.H and m[y + h][xx] == self.stone: m[y + h][xx] = self.hwall
        for yy in range(y, y + h):
            if x - 1 >= 0 and m[yy][x - 1] == self.stone: m[yy][x - 1] = self.vwall
            if x + w < self.W and m[yy][x + w] == self.stone: m[yy][x + w] = self.vwall

    def _gen_map(self):
        m = [[self.stone] * self.W for _ in range(self.H)]
        rooms = []
        for _ in range(300):
            if len(rooms) >= 7: break
            w, h = random.randint(4, 10), random.randint(3, 5)
            x, y = random.randint(1, self.W - w - 2), random.randint(1, self.H - h - 2)
            if any(not (x + w + 1 < rx or rx + rw + 1 < x or
                        y + h + 1 < ry or ry + rh + 1 < y)
                   for rx, ry, rw, rh in rooms):
                continue
            rooms.append((x, y, w, h))
            self._carve_room(m, x, y, w, h)

        for i in range(len(rooms) - 1):
            x1, y1, w1, h1 = rooms[i]
            x2, y2, w2, h2 = rooms[i + 1]
            cx1, cy1 = x1 + w1 // 2, y1 + h1 // 2
            cx2, cy2 = x2 + w2 // 2, y2 + h2 // 2
            for x in range(min(cx1, cx2), max(cx1, cx2) + 1):
                if m[cy1][x] != self.floor: m[cy1][x] = self.corr
            for y in range(min(cy1, cy2), max(cy1, cy2) + 1):
                if m[y][cx2] != self.floor: m[y][cx2] = self.corr

        self.rooms = rooms
        if rooms:
            x, y, w, h = rooms[0]
            self.px, self.py = x + w // 2, y + h // 2
        return m

    def _free_floor(self, occ):
        for _ in range(300):
            x = random.randint(1, self.W - 2)
            y = random.randint(1, self.H - 2)
            if self.map[y][x] in self.walkable and (x, y) not in occ \
                    and self.map[y][x] not in ("__STAIR__", "__ALTAR__", "__TRAP__"):
                return x, y
        return None

    def _spawn_items(self, n):
        out, occ = [], {(self.px, self.py)}
        for _ in range(n):
            pos = self._free_floor(occ)
            if not pos: continue
            x, y = pos; occ.add((x, y))
            t = random.choice(self.item_pool)
            out.append({"name": t["name"], "char": t["char"],
                        "class": t["class"], "x": x, "y": y})
        return out

    def _spawn(self, n):
        out, occ = [], {(self.px, self.py)}
        hp_bonus = (self.depth - 1) * 2
        for _ in range(n):
            pos = self._free_floor(occ)
            if not pos: continue
            x, y = pos; occ.add((x, y))
            cand = [t for t in self.mon_pool if t["level"] <= max(1, self.depth + 2)]
            if not cand: cand = self.mon_pool
            t = random.choice(cand)
            mh = t["level"] + 4 + hp_bonus
            role = t.get("role", "melee")
            out.append({
                "name": t["name"], "char": t["char"], "level": t["level"],
                "hp": mh, "max_hp": mh, "x": x, "y": y,
                "role": role,
                "shield": 50 if role == "shield" else 0,
                "range": 5 if role == "ranged" else 0,
            })
        return out

    def _apply_dungeon_theme(self):
        idx = ((self.depth - 1) // 10) % len(DUNGEON_THEMES)
        self.dungeon_theme_idx = idx
        t = DUNGEON_THEMES[idx]
        self.dungeon_name = t["name"]
        s = self.sym
        self.floor = t.get("floor") or s.get("S_floor", ".")
        self.corr  = t.get("corr")  or s.get("S_corr", "#")
        self.walkable = {self.floor, self.corr, "__STAIR__",
                         "__ALTAR__", "__TRAP__", "__SHOP__"}

    def _new_level(self, first=False):
        self._apply_dungeon_theme()
        self.rooms = []
        self.map = self._gen_map()
        if self.rooms:
            x, y, w, h = self.rooms[-1]
            sx, sy = x + w // 2, y + h // 2
            self.map[sy][sx] = "__STAIR__"
            self.dnstair_x, self.dnstair_y = sx, sy
        # 祭坛 & 陷阱
        self.altars = []
        self.traps  = {}
        occ = {(self.px, self.py), (self.dnstair_x, self.dnstair_y)}
        if random.random() < 0.20:
            pos = self._free_floor(occ)
            if pos:
                x, y = pos
                self.map[y][x] = "__ALTAR__"
                self.altars.append(pos)
                occ.add(pos)
        for _ in range(random.randint(2, 4)):
            pos = self._free_floor(occ)
            if not pos: break
            x, y = pos
            self.map[y][x] = "__TRAP__"
            self.traps[pos] = random.choice(["spike", "teleport", "poison"])
            occ.add(pos)

        # 商店（每 10 层）
        self.shop_pos = None
        self.shop_items = []
        if self.depth % 10 == 0:
            pos = self._free_floor(occ)
            if pos:
                x, y = pos
                self.map[y][x] = "__SHOP__"
                self.shop_pos = pos
                self.shop_items = self._gen_shop_items()
                occ.add(pos)

        is_boss = (self.depth % 5 == 0)
        if is_boss:
            self._spawn_boss_level()
        else:
            self.boss = None
            t = DUNGEON_THEMES[self.dungeon_theme_idx]
            n_mon  = int(min(6 + self.depth * 2, 25) * t["mon_mul"])
            n_item = int(min(10 + self.depth, 20) * t["item_mul"])
            self.items    = self._spawn_items(n_item)
            self.monsters = self._spawn(n_mon)
        if not first:
            if is_boss:
                self.msg = f"⚠ 第 {self.depth} 层 · {self.dungeon_name} · BOSS 巢穴 ⚠"
            else:
                self.msg = f"第 {self.depth} 层 · {self.dungeon_name}"

    def _spawn_boss_level(self):
        """Boss 层：一个小怪潮 + 一只 boss"""
        n_min = 4 + self.depth // 3
        n_item = 8 + self.depth // 2
        self.items = self._spawn_items(min(n_item, 15))
        small = self._spawn(min(n_min, 12))

        # 选一个怪物作为 boss 模板
        if not self.mon_pool:
            return
        tpl = max(self.mon_pool, key=lambda t: t["level"])
        bx, by = self.dnstair_x, self.dnstair_y - 3
        for _ in range(50):
            bx = random.randint(2, self.W - 3)
            by = random.randint(2, self.H - 3)
            if self.map[by][bx] == self.floor:
                break
        lvl = tpl["level"] + self.depth
        hp  = 30 + self.depth * 6
        self.boss = {
            "name": f"{tpl['name']} 之王", "char": tpl["char"], "level": lvl,
            "hp": hp, "max_hp": hp, "x": bx, "y": by,
            "role": "melee", "shield": 0, "range": 0,
            "is_boss": True,
        }
        self.monsters = small + [self.boss]
        self.boss_warned = False

    # ---------- 商店 ----------
    def _gen_shop_items(self):
        out = []
        for _ in range(random.randint(5, 8)):
            t = random.choice(self.item_pool)
            out.append({
                "name": t["name"], "char": t["char"],
                "class": t["class"],
                "price": self._buy_price(t["class"], t["name"]),
            })
        return out

    def _buy_price(self, cls, name):
        base = PRICE_BASE.get(cls, 3)
        if cls == "WEAPON":
            return base + self._weapon_bonus(name) * 3 + random.randint(0, 3)
        if cls == "ARMOR":
            return base + self._armor_bonus(name) * 3 + random.randint(0, 3)
        return base + random.randint(0, 2)

    def _sell_price(self, it):
        return max(1, self._inv_item_value(it) * 2)

    def _open_shop(self):
        self.shop_open = True
        self.shop_cursor = 0
        self.shop_mode = "buy"
        self.msg = f"商店 · 金币 {self.gold} · Tab 切换买/卖 · Esc 离开"

    def _shop_move(self, d):
        n = len(self.shop_items) if self.shop_mode == "buy" else len(self.inventory)
        if n == 0: return
        self.shop_cursor = (self.shop_cursor + d) % n

    def _shop_buy(self):
        if not self.shop_items: return
        idx = min(self.shop_cursor, len(self.shop_items) - 1)
        it = self.shop_items[idx]
        if self.gold < it["price"]:
            self.msg = f"金币不足 (需要 {it['price']})"
            return
        if len(self.inventory) >= 12:
            self.msg = "背包已满"
            return
        self.gold -= it["price"]
        self.inventory.append({
            "name": it["name"], "char": it["char"],
            "class": it["class"],
        })
        self.shop_items.pop(idx)
        self.msg = f"买入 {tr(it['name'])} -{it['price']}金"
        if self.shop_cursor >= len(self.shop_items):
            self.shop_cursor = max(0, len(self.shop_items) - 1)

    def _shop_sell(self):
        if not self.inventory: return
        idx = min(self.shop_cursor, len(self.inventory) - 1)
        it = self.inventory[idx]
        price = self._sell_price(it)
        self.gold += price
        self.score += price // 2
        self.inventory.pop(idx)
        self.msg = f"卖出 {tr(it['name'])} +{price}金"
        if self.shop_cursor >= len(self.inventory):
            self.shop_cursor = max(0, len(self.inventory) - 1)

    def _draw_shop(self, s, W, H):
        box_w = min(W - 2, 64)
        box_h = min(self.H, 20)
        x0 = max(0, (W - box_w) // 2)
        y0 = max(0, (self.H - box_h) // 2)
        frame = curses.color_pair(C_BAR) | curses.A_BOLD
        head  = curses.color_pair(C_PLR) | curses.A_BOLD
        item  = curses.color_pair(C_MSG)
        sel   = curses.color_pair(C_PLR) | curses.A_BOLD | curses.A_REVERSE

        for i in range(box_h):
            try: s.addstr(y0+i, x0, " " * box_w, frame)
            except curses.error: pass
        try:
            s.addstr(y0, x0, "┌" + "─"*(box_w-2) + "┐", frame)
            for i in range(1, box_h-1):
                s.addstr(y0+i, x0, "│", frame)
                s.addstr(y0+i, x0+box_w-1, "│", frame)
            s.addstr(y0+box_h-1, x0, "└" + "─"*(box_w-2) + "┘", frame)
        except curses.error: pass

        try:
            s.addstr(y0, x0+2, f" 商店 · 金币 {self.gold} ", head)
        except curses.error: pass

        mid = box_w // 2
        try:
            s.addstr(y0+1, x0+1, " 商品", head)
            s.addstr(y0+1, x0+mid, " 背包（卖出）", head)
            s.addstr(y0+2, x0+1, "─"*(mid-2), frame)
            s.addstr(y0+2, x0+mid, "─"*(box_w-mid-2), frame)
        except curses.error: pass

        max_l = box_h - 5
        mode = self.shop_mode
        # 左：商品
        if not self.shop_items:
            try: s.addstr(y0+3, x0+2, "(无)", item)
            except curses.error: pass
        else:
            for i, it in enumerate(self.shop_items[:max_l]):
                is_sel = (mode == "buy" and i == self.shop_cursor)
                m = ">" if is_sel else " "
                line = f" {m} {i+1}. {truncate(tr(it['name']), 18)}  {it['price']}金"
                try:
                    s.addstr(y0+3+i, x0+1, truncate(line, mid-2),
                             sel if is_sel else item)
                except curses.error: pass
        # 右：背包
        if not self.inventory:
            try: s.addstr(y0+3, x0+mid+1, "(空)", item)
            except curses.error: pass
        else:
            for i, it in enumerate(self.inventory[:max_l]):
                is_sel = (mode == "sell" and i == self.shop_cursor)
                m = ">" if is_sel else " "
                price = self._sell_price(it)
                line = f" {m} {i+1}. {truncate(tr(it['name']), 14)}  {price}金"
                try:
                    s.addstr(y0+3+i, x0+mid+1, truncate(line, box_w-mid-2),
                             sel if is_sel else item)
                except curses.error: pass

        hint = " ↑/↓ 选择  Enter 买/卖  Tab 切换  Esc 离开 "
        try:
            s.addstr(y0+box_h-2, x0+1, truncate(hint, box_w-2), head)
        except curses.error: pass

    def _altar_sacrifice(self, x, y):
        cands = [(self._inv_item_value(it), i, it)
                 for i, it in enumerate(self.inventory)
                 if it["class"] in ("WEAPON", "ARMOR")]
        if not cands:
            self.msg = "祭坛拒绝了你——背包里没有可献祭的装备"
            return
        _, i, it = min(cands, key=lambda t: t[0])
        self.inventory.pop(i)
        if it["class"] == "WEAPON":
            self.temp_atk_bonus += 2
            self.msg = f"你在祭坛前献祭了 {tr(it['name'])}，力量涌现 (+2攻)"
        else:
            self.temp_def_bonus += 2
            self.msg = f"你在祭坛前献祭了 {tr(it['name'])}，护佑降临 (+2防)"
        self.particles.burst(x, y, ch="*", n=12, color=3, radius=3)
        self.map[y][x] = self.floor
        if (x, y) in self.altars:
            self.altars.remove((x, y))

    def _trigger_trap(self, x, y):
        ttype = self.traps.pop((x, y), None)
        if ttype is None:
            return
        self.map[y][x] = self.floor
        if ttype == "spike":
            dmg = random.randint(5, 15)
            self.hp -= dmg
            self.particles.hit(x, y, color=2)
            self.msg = f"踩到尖刺陷阱 -{dmg}HP"
            if self.hp <= 0:
                self._handle_death("尖刺陷阱")
        elif ttype == "teleport":
            for _ in range(200):
                nx = random.randint(1, self.W - 2)
                ny = random.randint(1, self.H - 2)
                if self.map[ny][nx] in self.walkable:
                    self.px, self.py = nx, ny
                    self.particles.magic(nx, ny, color=5)
                    self.msg = f"踩到传送陷阱 → ({nx},{ny})"
                    break
        elif ttype == "poison":
            self.hp -= 3
            self.poison_turns = 5
            self.particles.burst(x, y, ch="~", n=6, color=2, radius=1)
            self.msg = "踩到毒陷阱 -3HP · 中毒 5 回合"
            if self.hp <= 0:
                self._handle_death("毒陷阱")

    def _tick_poison(self):
        if self.poison_turns > 0:
            self.poison_turns -= 1
            self.hp -= 1
            self.particles.add(self.px, self.py, "~", ttl=2, color=2)
            if self.hp <= 0:
                self._handle_death("毒")

    def _descend(self):
        self.depth += 1
        self.score += 50
        if self.depth >= 100:
            self._victory()
            return
        heal = self.max_hp - self.hp
        if heal > 0: self.hp += heal
        self.temp_atk_bonus = 0
        self.temp_def_bonus = 0
        self.poison_turns = 0
        self._new_level(first=False)
        self.msg = f"下到第 {self.depth} 层 (HP 回满 +{heal}, +50分)"
        self._save()

    # ---------- 存档 ----------
    def _save(self):
        state = {
            "version": 1,
            "race_key": getattr(self, "race_key", None),
            "player_name": self.player_name,
            "depth": self.depth, "score": self.score, "kills": self.kills,
            "turn": self.turn, "level": self.level,
            "exp": self.exp, "exp_next": self.exp_next,
            "max_hp": self.max_hp, "hp": self.hp,
            "atk_bonus": self.atk_bonus, "def_bonus": self.def_bonus,
            "weapon": self.weapon, "armor": self.armor,
            "inventory": self.inventory,
            "gold": getattr(self, "gold", 0),
        }
        try:
            SAVE_FILE.write_text(json.dumps(state, ensure_ascii=False))
        except Exception as e:
            self.msg = f"[save err] {e}"

    @staticmethod
    def load_state():
        if not SAVE_FILE.exists():
            return None
        try:
            return json.loads(SAVE_FILE.read_text())
        except Exception:
            return None

    def restore(self, state):
        self.player_name = state.get("player_name", self.player_name)
        self.depth     = state.get("depth", 1)
        self.score     = state.get("score", 0)
        self.kills     = state.get("kills", 0)
        self.turn      = state.get("turn", 0)
        self.level     = state.get("level", 1)
        self.exp       = state.get("exp", 0)
        self.exp_next  = state.get("exp_next", 8)
        self.max_hp    = state.get("max_hp", self.max_hp)
        self.hp        = state.get("hp", self.max_hp)
        self.atk_bonus = state.get("atk_bonus", 0)
        self.def_bonus = state.get("def_bonus", 0)
        self.weapon    = state.get("weapon")
        self.armor     = state.get("armor")
        self.inventory = state.get("inventory", [])
        self.gold      = state.get("gold", 0)
        self._new_level(first=(self.depth == 1))

    def _victory(self):
        self.won = True
        self.dead = True          # 阻止继续移动
        self.auto_mode = False
        self._record_death()      # 同样记录成绩
        rank = self.death_rank if self.death_rank is not None else "?"
        self.popup = ("🏆 通关！到达第 100 层", [
            "你带着 NetHack 的护身符返回地面！",
            "",
            f"最终分数 {self.score}   等级 Lv{self.level}   击杀 {self.kills}",
            f"冒险者: {self.player_name}",
            "",
            f"排行榜排名 #{rank}",
            "",
            "任意键继续 · H 看排行榜 · q 退出",
        ])
        self.msg = "🏆 通关！"

    def _move(self, dx, dy):
        if self.dead: return
        nx, ny = self.px + dx, self.py + dy
        if not (0 <= nx < self.W and 0 <= ny < self.H): return
        if self.map[ny][nx] not in self.walkable: return
        for m in list(self.monsters):
            if m["x"] == nx and m["y"] == ny:
                self._attack(m)
                self._monster_turns()
                return
        self.px, self.py = nx, ny
        self.particles.tick()
        if self.reveal_turns > 0:
            self.reveal_turns -= 1
        if self.race_skill_cd > 0:
            self.race_skill_cd -= 1
        if getattr(self, "invuln_turns", 0) > 0:
            self.invuln_turns -= 1
        if self.map[ny][nx] == "__STAIR__":
            self._auto_pickup()
            self._descend()
            return

        if self.map[ny][nx] == "__ALTAR__":
            self._altar_sacrifice(nx, ny)
        elif self.map[ny][nx] == "__TRAP__":
            self._trigger_trap(nx, ny)
        elif self.map[ny][nx] == "__SHOP__":
            self._open_shop()

        self._auto_pickup()
        self._tick_poison()
        if self.dead:
            return
        self.turn += 1
        if random.random() < 0.008:
            self._flavor()
        self._monster_turns()

    def _attack(self, m):
        dmg = (random.randint(1, 6) + self.level - 1 + self.atk_bonus
               + getattr(self, 'temp_atk_bonus', 0))
        sh = m.get("shield", 0)
        if sh > 0:
            dmg = max(1, dmg - dmg * sh // 100)
        m["hp"] -= dmg
        if m["hp"] <= 0:
            self.monsters.remove(m)
            self.kills += 1
            is_boss = m.get("is_boss", False)
            bonus = 300 if is_boss else 0
            self.score += m["level"] * 5 + bonus
            gain = m["level"] * (3 if is_boss else 1)
            gain = int(gain * self.race.get("exp_mul", 1.0))
            self.exp += gain
            if is_boss:
                self.particles.burst(m["x"], m["y"], "★", n=20, color=3, radius=4)
                self.msg = f"★ 击杀 BOSS {tr(m['name'])} +{gain}exp +{bonus}分"
                self.boss = None
            else:
                self.particles.die(m["x"], m["y"])
                self.msg = f"击杀 {tr(m['name'])} +{gain}exp (+{m['level']*5}分)"
            self._check_levelup()
            self._auto_pickup(); return
        else:
            self.particles.hit(m["x"], m["y"], color=2)
        self.msg = f"打 {tr(m['name'])} -{dmg}hp  (HP {m['hp']}/{m['max_hp']})"

    def _check_levelup(self):
        while self.exp >= self.exp_next:
            self.exp -= self.exp_next
            self.level += 1
            self.exp_next = 5 + self.level * 3
            self.max_hp += 4
            self.hp = self.max_hp
            self.msg = f"升级! Lv{self.level}  HP {self.max_hp}"

    def _auto_pickup(self):
        for it in list(self.items):
            if it["x"] == self.px and it["y"] == self.py:
                self.items.remove(it)
                self._apply_item(it)

    def _apply_item(self, it):
        cls = it["class"]; name = it["name"].lower()

        if cls == "COIN" or "gold" in name:
            v = random.randint(5, 30)
            self.gold += v
            self.score += v
            self.msg = f"拾取 {tr(it['name'])} +{v}金"
            return

        if cls == "WEAPON":
            bonus = self._weapon_bonus(it["name"])
            if self.weapon is None or bonus > self.weapon.get("bonus", 0):
                if self.weapon:
                    if len(self.inventory) < 12:
                        self.inventory.append(self.weapon)
                    else:
                        self.score += 2
                it["bonus"] = bonus
                self.weapon = it
                self.atk_bonus = bonus
                self.msg = f"装备 {tr(it['name'])}  +{bonus}攻"
            elif len(self.inventory) < 12:
                self.inventory.append(it)
                self.msg = f"拾取 {tr(it['name'])} (入包)"
            else:
                self.score += 2; self.msg = "背包满"
            return

        if cls == "ARMOR":
            bonus = self._armor_bonus(it["name"])
            if self.armor is None or bonus > self.armor.get("bonus", 0):
                if self.armor:
                    if len(self.inventory) < 12:
                        self.inventory.append(self.armor)
                    else:
                        self.score += 2
                it["bonus"] = bonus
                self.armor = it
                self.def_bonus = bonus
                self.msg = f"穿上 {tr(it['name'])}  +{bonus}防"
            elif len(self.inventory) < 12:
                self.inventory.append(it)
                self.msg = f"拾取 {tr(it['name'])} (入包)"
            else:
                self.score += 2; self.msg = "背包满"
            return

        # 药水 / 食物 / 卷轴 / 魔杖 / 戒指 / 护符 / 宝石 / 工具
        if cls in ("POTION", "FOOD", "SCROLL", "WAND", "RING",
                   "AMULET", "GEM", "TOOL", "SPBOOK"):
            if len(self.inventory) < 12:
                self.inventory.append(it)
                self.msg = f"拾取 {tr(it['name'])} (背包 {len(self.inventory)}/12)"
            else:
                self.score += 2; self.msg = "背包满"
            return

        self.score += 3
        self.msg = f"拾取 {tr(it['name'])} (+3 未知类型)"

    # ---------- 怪物 AI ----------
    def _compute_dist_field(self):
        from collections import deque
        dist = [[-1] * self.W for _ in range(self.H)]
        dist[self.py][self.px] = 0
        q = deque([(self.px, self.py)])
        while q:
            x, y = q.popleft()
            nd = dist[y][x] + 1
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.W and 0 <= ny < self.H and dist[ny][nx] == -1:
                    if self.map[ny][nx] in self.walkable:
                        dist[ny][nx] = nd
                        q.append((nx, ny))
        return dist

    def _has_los(self, x0, y0, x1, y1):
        dx = abs(x1 - x0); dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while (x0, y0) != (x1, y1):
            e2 = 2 * err
            if e2 > -dy: err -= dy; x0 += sx
            if e2 <  dx: err += dx; y0 += sy
            if (x0, y0) == (x1, y1): break
            if self.map[y0][x0] in self.walls:
                return False
        return True

    def _monster_turns(self):
        if self.dead or not self.monsters:
            return
        dist = self._compute_dist_field()
        avg_lvl = sum(m["level"] for m in self.monsters) / len(self.monsters)
        player_power = self.level + self.depth // 3
        alerted = player_power > avg_lvl + 2
        chase_range = 25 if alerted else 12

        for m in list(self.monsters):
            if self.dead or m not in self.monsters:
                continue
            d = dist[m["y"]][m["x"]]
            role = m.get("role", "melee")

            if role == "ranged" and 2 <= d <= m.get("range", 5):
                if self._has_los(m["x"], m["y"], self.px, self.py):
                    self._monster_ranged_attack(m)
                    continue

            if d == 1:
                self._monster_attack(m)
                continue

            if d == -1 or d > chase_range:
                if random.random() < 0.15:
                    self._monster_wander(m)
                continue

            if role == "ranged" and 2 <= d <= m.get("range", 5):
                if self._has_los(m["x"], m["y"], self.px, self.py):
                    continue

            best, best_d = None, d
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nx, ny = m["x"] + dx, m["y"] + dy
                if not (0 <= nx < self.W and 0 <= ny < self.H):
                    continue
                if dist[ny][nx] == -1 or dist[ny][nx] >= best_d:
                    continue
                if nx == self.px and ny == self.py:
                    continue
                if any(o["x"] == nx and o["y"] == ny
                       for o in self.monsters if o is not m):
                    continue
                best, best_d = (nx, ny), dist[ny][nx]
            if best:
                m["x"], m["y"] = best

    def _monster_attack(self, m):
        if getattr(self, "invuln_turns", 0) > 0:
            self.msg = f"无敌状态 · {tr(m['name'])} 攻击无效"
            return
        raw = max(1, m["level"] // 2 + (self.depth - 1) // 3)
        dmg = max(1, raw - (self.def_bonus + self.temp_def_bonus) // 2)
        self.hp -= dmg
        self.msg = f"{tr(m['name'])} 攻击你 -{dmg}hp"
        if self.hp <= 0:
            self._handle_death(tr(m["name"]))

    def _monster_ranged_attack(self, m):
        if getattr(self, "invuln_turns", 0) > 0:
            self.msg = f"无敌状态 · {tr(m['name'])} 远程无效"
            return
        raw = max(1, m["level"] // 3 + (self.depth - 1) // 4)
        dmg = max(1, raw - (self.def_bonus + self.temp_def_bonus) // 2)
        self.hp -= dmg
        self.msg = f"{tr(m['name'])} 远程攻击 -{dmg}hp"
        if self.hp <= 0:
            self._handle_death(tr(m["name"]) + " (远程)")

    def _monster_wander(self, m):
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = m["x"] + dx, m["y"] + dy
            if not (0 <= nx < self.W and 0 <= ny < self.H):
                continue
            if self.map[ny][nx] not in self.walkable:
                continue
            if nx == self.px and ny == self.py:
                continue
            if any(o["x"] == nx and o["y"] == ny
                   for o in self.monsters if o is not m):
                continue
            m["x"], m["y"] = nx, ny
            return

    # ---------- 分数 ----------
    def _record_death(self):
        if self._death_recorded:
            return
        self._death_recorded = True
        # 死亡/通关后清存档
        try:
            SAVE_FILE.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass
        try:
            _, rank = add_score(self.player_name, self.score,
                                self.depth, self.level, self.kills)
            self.death_rank = rank
        except Exception as e:
            self.death_rank = None
            self.msg = f"保存分数失败: {e}"

    def _handle_death(self, killer):
        self.hp = 0
        self.dead = True
        self.auto_mode = False
        self._record_death()
        rank = self.death_rank if self.death_rank is not None else "?"
        self.popup = ("你死了", [
            f"在第 {self.depth} 层被 {killer} 杀死",
            "",
            f"最终分数 {self.score}   等级 Lv{self.level}   击杀 {self.kills}",
            f"冒险者: {self.player_name}",
            "",
            f"排行榜排名  #{rank}",
            "",
            "任意键继续 · H 看排行榜 · q 退出",
        ])
        self.msg = f"R.I.P. 排名 #{rank}"

    def _show_leaderboard(self):
        scores = load_scores()
        if not scores:
            self.popup = ("排行榜", ["暂无记录。开始你的冒险吧！"])
            return
        lines = []
        lines.append(f"{'#':>2}  {pad('名字', 10)} {'分数':>6} {'深':>3} {'Lv':>3} {'杀':>3}  日期")
        lines.append("─" * 50)
        for i, s_ in enumerate(scores[:20]):
            name = s_.get("name", "?")
            date = s_.get("date", "")[:10]
            lines.append(
                f"{i+1:>2}  {pad(truncate(name, 10), 10)} {s_.get('score',0):>6} "
                f"{s_.get('depth',0):>3} {s_.get('level',0):>3} "
                f"{s_.get('kills',0):>3}  {date}"
            )
        self.popup = ("排行榜 · Top 20", lines)


    # ---------- 物品栏 ----------
    def _weapon_bonus(self, name):
        n = name.lower()
        for kw, b in self.WEAPON_TIERS:
            if kw in n: return b
        return 1

    def _armor_bonus(self, name):
        n = name.lower()
        for kw, b in self.ARMOR_TIERS:
            if kw in n: return b
        return 1

    def _use_healing(self):
        if self.hp >= self.max_hp:
            return False
        for it in self.inventory:
            if it["class"] == "POTION" and "heal" in it["name"].lower():
                self.inventory.remove(it)
                heal = random.randint(5, 12) + self.level
                self.hp = min(self.max_hp, self.hp + heal)
                self.msg = f"喝 {tr(it['name'])} +{heal}HP"
                return True
        for it in self.inventory:
            if it["class"] == "FOOD":
                self.inventory.remove(it)
                heal = random.randint(2, 5)
                self.hp = min(self.max_hp, self.hp + heal)
                self.msg = f"吃 {tr(it['name'])} +{heal}HP"
                return True
        return False

    def _open_inventory(self):
        self.inv_open = True
        self.msg = f"[背包] cursor={self.inv_cursor} items={len(self.inventory)}"
        if self.inv_cursor >= len(self.inventory):
            self.inv_cursor = max(0, len(self.inventory) - 1)

    def _close_inventory(self):
        self.inv_open = False

    def _inv_move(self, d):
        if not self.inventory:
            return
        self.inv_cursor = (self.inv_cursor + d) % len(self.inventory)

    def _inv_use(self):
        if not self.inventory:
            self.msg = "背包是空的"
            return
        idx = min(self.inv_cursor, len(self.inventory) - 1)
        it = self.inventory[idx]
        cls = it["class"]
        name = it["name"].lower()

        if cls == "POTION":
            self.inventory.pop(idx)
            if "heal" in name or "extra" in name:
                heal = random.randint(5, 12) + self.level
                self.hp = min(self.max_hp, self.hp + heal)
                self.msg = f"喝 {tr(it['name'])}  +{heal}HP"
            else:
                self.score += 5
                self.msg = f"喝下 {tr(it['name'])}  (+5分)"

        elif cls == "FOOD":
            self.inventory.pop(idx)
            heal = random.randint(2, 5)
            self.hp = min(self.max_hp, self.hp + heal)
            self.msg = f"吃 {tr(it['name'])}  +{heal}HP"

        elif cls == "WEAPON":
            old = self.weapon
            self.inventory.pop(idx)
            it["bonus"] = self._weapon_bonus(it["name"])
            self.weapon = it
            self.atk_bonus = it["bonus"]
            if old:
                self.inventory.append(old)
            self.msg = f"装备 {tr(it['name'])}  +{it['bonus']}攻"

        elif cls == "ARMOR":
            old = self.armor
            self.inventory.pop(idx)
            it["bonus"] = self._armor_bonus(it["name"])
            self.armor = it
            self.def_bonus = it["bonus"]
            if old:
                self.inventory.append(old)
            self.msg = f"穿上 {tr(it['name'])}  +{it['bonus']}防"

        else:
            self.inventory.pop(idx)
            self.score += 3
            self.msg = f"用掉 {tr(it['name'])}  (+3分)"

        if self.inv_cursor >= len(self.inventory):
            self.inv_cursor = max(0, len(self.inventory) - 1)

    # ---------- 背包自动管理（供脚本调用） ----------
    def _inv_item_value(self, it):
        """物品在当前强度下的“价值”评分，用于选优/选汰"""
        cls = it["class"]; name = it["name"].lower()
        if cls == "WEAPON":   return 2 + self._weapon_bonus(it["name"])
        if cls == "ARMOR":    return 2 + self._armor_bonus(it["name"])
        if cls in ("RING", "AMULET", "WAND", "SPBOOK"): return 6
        if cls == "GEM":      return 5
        if cls == "POTION":   return 4
        if cls == "SCROLL":   return 3
        if cls == "FOOD":     return 2
        return 1

    def _inv_equip_best(self):
        """把背包里比当前更强的武器/护甲穿上。返回 True 表示有变化"""
        did = False

        # 武器
        cur = self.atk_bonus if self.weapon else -1
        best_i, best_b = -1, cur
        for i, it in enumerate(self.inventory):
            if it["class"] != "WEAPON": continue
            b = self._weapon_bonus(it["name"])
            if b > best_b:
                best_i, best_b = i, b
        if best_i != -1:
            it = self.inventory.pop(best_i)
            it["bonus"] = best_b
            if self.weapon:
                self.inventory.append(self.weapon)
            self.weapon = it
            self.atk_bonus = best_b
            self.msg = f"自动装备 {tr(it['name'])} +{best_b}攻"
            did = True

        # 护甲
        cur = self.def_bonus if self.armor else -1
        best_i, best_b = -1, cur
        for i, it in enumerate(self.inventory):
            if it["class"] != "ARMOR": continue
            b = self._armor_bonus(it["name"])
            if b > best_b:
                best_i, best_b = i, b
        if best_i != -1:
            it = self.inventory.pop(best_i)
            it["bonus"] = best_b
            if self.armor:
                self.inventory.append(self.armor)
            self.armor = it
            self.def_bonus = best_b
            self.msg = f"自动穿上 {tr(it['name'])} +{best_b}防"
            did = True

        return did

    def _inv_discard_worst(self):
        """销毁背包里价值最低的物品（治疗药水/食物永不丢）。返回 (name, gain) 或 None"""
        if not self.inventory: return None
        candidates = []
        for i, it in enumerate(self.inventory):
            cls = it["class"]; name = it["name"].lower()
            if cls == "POTION" and "heal" in name: continue
            if cls == "FOOD": continue
            candidates.append((i, self._inv_item_value(it), it))
        if not candidates:
            return None
        i, v, it = min(candidates, key=lambda x: x[1])
        self.inventory.pop(i)
        gain = max(1, v)
        self.score += gain
        self.msg = f"自动销毁 {tr(it['name'])} +{gain}分"
        if self.inv_cursor >= len(self.inventory):
            self.inv_cursor = max(0, len(self.inventory) - 1)
        return it["name"], gain

    def _auto_manage_inventory(self, threshold=8):
        """脚本调用：装备最优 + 超量时清理垃圾。返回 True 表示有变化"""
        did = self._inv_equip_best()
        while len(self.inventory) > threshold:
            if self._inv_discard_worst() is None:
                break
            did = True
        return did

    def _inv_destroy(self):
        if not self.inventory:
            self.msg = "背包是空的"
            return
        idx = min(self.inv_cursor, len(self.inventory) - 1)
        it = self.inventory.pop(idx)
        cls = it["class"]
        name = it["name"].lower()

        # 销毁得分：武器/护甲按品质，其他按类别
        if cls == "WEAPON":
            gain = 4 + self._weapon_bonus(it["name"]) * 3
        elif cls == "ARMOR":
            gain = 4 + self._armor_bonus(it["name"]) * 3
        elif cls in ("RING", "AMULET", "WAND", "SPBOOK"):
            gain = 8
        elif cls == "POTION":
            gain = 5
        elif cls == "SCROLL":
            gain = 4
        elif cls == "GEM":
            gain = 6
        else:
            gain = 2

        self.score += gain
        self.msg = f"销毁 {tr(it['name'])}  +{gain}分"

        if self.inv_cursor >= len(self.inventory):
            self.inv_cursor = max(0, len(self.inventory) - 1)

    def _draw_inventory(self, s, W, H):
        box_w = min(W - 2, 58)
        box_h = min(self.H, 18)
        x0 = max(0, (W - box_w) // 2)
        y0 = max(0, (self.H - box_h) // 2)

        attr_frame = curses.color_pair(C_BAR) | curses.A_BOLD
        attr_head  = curses.color_pair(C_PLR) | curses.A_BOLD
        attr_item  = curses.color_pair(C_MSG)
        attr_sel   = curses.color_pair(C_PLR) | curses.A_BOLD | curses.A_REVERSE

        # 清底
        for i in range(box_h):
            try:
                s.addstr(y0+i, x0, " " * box_w, attr_frame)
            except curses.error:
                pass

        try:
            s.addstr(y0, x0, "┌" + "─"*(box_w-2) + "┐", attr_frame)
            for i in range(1, box_h-1):
                s.addstr(y0+i, x0, "│", attr_frame)
                s.addstr(y0+i, x0+box_w-1, "│", attr_frame)
            s.addstr(y0+box_h-1, x0, "└" + "─"*(box_w-2) + "┘", attr_frame)
        except curses.error:
            pass

        try:
            s.addstr(y0, x0+2, " 背包 ", attr_head)
        except curses.error:
            pass

        w = tr(self.weapon["name"]) if self.weapon else "(空)"
        a = tr(self.armor["name"]) if self.armor else "(空)"
        line1 = f" 武器 {pad(truncate(w, 20), 20)} +{self.atk_bonus}攻"
        line2 = f" 护甲 {pad(truncate(a, 20), 20)} +{self.def_bonus}防"
        line3 = f" HP {self.hp}/{self.max_hp}   背包 {len(self.inventory)}/12"
        for i, line in enumerate((line1, line2, line3)):
            try:
                s.addstr(y0+1+i, x0+1, truncate(line, box_w-2), attr_item)
            except curses.error:
                pass

        try:
            s.addstr(y0+4, x0+1, "─"*(box_w-2), attr_frame)
        except curses.error:
            pass

        max_items = box_h - 7
        if not self.inventory:
            try:
                s.addstr(y0+5, x0+2, " (空)", attr_item)
            except curses.error:
                pass
        else:
            for i, it in enumerate(self.inventory[:max_items]):
                sel = (i == self.inv_cursor)
                marker = ">" if sel else " "
                name = pad(truncate(tr(it["name"]), 26), 26)
                line = f" {marker} {i+1:>2}. {name} [{it['class']}]"
                try:
                    s.addstr(y0+5+i, x0+1, truncate(line, box_w-2),
                              attr_sel if sel else attr_item)
                except curses.error:
                    pass

        hint = " ↑/↓ 移动   ← 使用/装备   → 销毁得分数   i/Esc 关闭 "
        try:
            s.addstr(y0+box_h-2, x0+1, truncate(hint, box_w-2), attr_head)
        except curses.error:
            pass


    # ---------- 种族技能 ----------
    def _use_race_skill(self):
        if self.race_skill_cd > 0:
            self.msg = f"{self.race['skill']['name']} 冷却中（{self.race_skill_cd} 回合）"
            return
        sk = self.race["skill"]
        name = sk["name"]
        amount = sk.get("amount", 0)

        if self.race_key == "human":
            self.exp += amount
            self._check_levelup()
            self.msg = f"{name} +{amount}exp"
            self.particles.magic(self.px, self.py, color=7)

        elif self.race_key == "elf":
            rng = amount
            for _ in range(80):
                nx = random.randint(max(1, self.px - rng), min(self.W - 2, self.px + rng))
                ny = random.randint(max(1, self.py - rng), min(self.H - 2, self.py + rng))
                if self.map[ny][nx] not in self.walkable: continue
                if any(o["x"] == nx and o["y"] == ny for o in self.monsters): continue
                self.particles.magic(self.px, self.py, color=5)
                self.px, self.py = nx, ny
                self.particles.magic(nx, ny, color=5)
                self.msg = f"{name} →({nx},{ny})"
                break
            else:
                self.msg = "无落点"
                return

        elif self.race_key == "dwarf":
            self.temp_def_bonus += amount
            self.particles.magic(self.px, self.py, color=6)
            self.msg = f"{name} 减伤 +{amount}（本层）"

        elif self.race_key == "orc":
            self.temp_atk_bonus = getattr(self, "temp_atk_bonus", 0) + amount
            self.temp_def_bonus -= 3
            self.particles.burst(self.px, self.py, "!", n=8, color=2, radius=2)
            self.msg = f"{name} 攻击 +{amount} 防御 -3（本层）"

        elif self.race_key == "goblin":
            if not self.monsters:
                self.msg = "没有目标"
                return
            m = min(self.monsters,
                    key=lambda x: abs(x["x"]-self.px) + abs(x["y"]-self.py))
            d = abs(m["x"]-self.px) + abs(m["y"]-self.py)
            if d > 5:
                self.msg = "目标太远（需 5 格内）"
                return
            self.score += amount
            self.particles.burst(m["x"], m["y"], "$", n=5, color=8, radius=1)
            self.msg = f"{name} 从 {tr(m['name'])} 偷到 {amount} 分"

        elif self.race_key == "dragonborn":
            hits = 0
            for m in list(self.monsters):
                if abs(m["x"]-self.px) + abs(m["y"]-self.py) <= 4:
                    m["hp"] -= amount
                    self.particles.hit(m["x"], m["y"], color=2)
                    hits += 1
                    if m["hp"] <= 0 and m in self.monsters:
                        self.monsters.remove(m)
                        self.kills += 1
                        is_boss = m.get("is_boss", False)
                        self.score += m["level"] * 5 + (300 if is_boss else 0)
                        self.exp += m["level"] * (3 if is_boss else 1)
                        self.particles.die(m["x"], m["y"], color=2)
                        if is_boss: self.boss = None
            self.particles.burst(self.px, self.py, "*", n=12, color=2, radius=4)
            if hits:
                self.msg = f"{name} 灼烧 {hits} 敌 -{amount}"
            else:
                self.msg = f"{name}（无目标）"

        else:
            self.msg = "无技能"
            return

        self.race_skill_cd = sk.get("cooldown", 10)

    def _load_script(self):
        try:
            if not SCRIPT_FILE.exists():
                self.script = None
                self.script_error = f"脚本不存在: {SCRIPT_FILE}"
                self.msg = "无脚本"
                return
            source = SCRIPT_FILE.read_text(encoding="utf-8")
            self.script = RLEngine(source, self, name=SCRIPT_FILE.name)
            self.script_error = ""
            self.msg = f"已加载 {SCRIPT_FILE.name}，按 s 启动"
        except RLError as e:
            self.script = None; self.script_error = str(e)
            self.msg = f"脚本错误: {e}"
        except Exception as e:
            self.script = None; self.script_error = str(e)
            self.msg = f"脚本异常: {e}"

    def _script_step(self):
        if self.dead or self.script is None:
            self.auto_mode = False; return
        # 卡住检测：连续 20 回合无进展 → 强制随机移动
        state = (self.px, self.py, self.kills, len(self.items),
                 len(self.monsters), self.depth, self.hp)
        if getattr(self, "_last_state", None) == state:
            self._stuck_turns = getattr(self, "_stuck_turns", 0) + 1
        else:
            self._stuck_turns = 0
            self._last_state = state
        if self._stuck_turns > 20:
            self._stuck_turns = 0
            dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
            random.shuffle(dirs)
            for dx, dy in dirs:
                nx, ny = self.px + dx, self.py + dy
                if 0 <= nx < self.W and 0 <= ny < self.H \
                        and self.map[ny][nx] in self.walkable:
                    self._move(dx, dy)
                    self.msg = "脚本卡住 → 强制移动"
                    return
        try:
            self.script.step()
        except TurnEnd:
            pass
        except RLError as e:
            self.script_error = str(e); self.auto_mode = False
            self.msg = f"脚本崩溃: {e}"
        except Exception as e:
            self.script_error = str(e); self.auto_mode = False
            self.msg = f"脚本异常: {e}"

    def _init_colors(self):
        if not curses.has_colors(): return
        curses.start_color()
        try:
            curses.use_default_colors(); bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        c = self.theme.color
        curses.init_pair(C_WALL,  c("wall", "white"), bg)
        curses.init_pair(C_MON,   c("monster", "red"), bg)
        curses.init_pair(C_PLR,   c("player", "yellow"), bg)
        curses.init_pair(C_BAR,   c("bar", "cyan"), bg)
        curses.init_pair(C_MSG,   c("msg", "green"), bg)
        curses.init_pair(C_ITEM,  c("item", "white"), bg)
        curses.init_pair(C_MAGIC, c("magic", "magenta"), bg)
        curses.init_pair(C_GOLD,  c("gold", "yellow"), bg)
        curses.init_pair(C_FOOD,  c("food", "green"), bg)

    def _draw(self, s):
        s.clear()
        H, W = s.getmaxyx()
        if H < self.H + 2 or W < self.W:
            s.addstr(0, 0, f"终端太小，需要 {self.W}x{self.H+2}")
            s.refresh(); return
        wall_attr  = curses.color_pair(C_WALL)
        stair_attr = curses.color_pair(C_BAR) | curses.A_BOLD
        for y in range(self.H):
            for x in range(self.W):
                ch = self.map[y][x]
                if ch == "__STAIR__":
                    s.addch(y, x, self.dnstair_char, stair_attr)
                elif ch == "__ALTAR__":
                    s.addch(y, x, self.altar_char, stair_attr)
                elif ch == "__TRAP__":
                    s.addch(y, x, self.trap_char,
                            curses.color_pair(C_MON) | curses.A_BOLD)
                elif ch == "__SHOP__":
                    s.addch(y, x, "$",
                            curses.color_pair(C_GOLD) | curses.A_BOLD)
                elif ch in self.walls:
                    s.addch(y, x, ch, wall_attr)
                else:
                    s.addch(y, x, ch, 0)
        for it in self.items:
            s.addch(it["y"], it["x"], it["char"],
                    curses.color_pair(self.ITEM_COLOR.get(it["class"], C_ITEM)))
        for m in self.monsters:
            role = m.get("role", "melee")
            is_boss = m.get("is_boss", False)
            if is_boss:            col = C_GOLD
            elif role == "ranged": col = C_MAGIC
            elif role == "shield": col = C_BAR
            else:                  col = C_MON
            attr = curses.color_pair(col)
            if is_boss: attr |= curses.A_BOLD
            if self.reveal_turns > 0:
                attr |= curses.A_REVERSE
            s.addch(m["y"], m["x"], m["char"], attr)

        # 粒子
        for p in self.particles.list:
            if 0 <= p.x < self.W and 0 <= p.y < self.H:
                attr = curses.color_pair(p.color) if p.color else 0
                if p.bold: attr |= curses.A_BOLD
                try:
                    s.addch(p.y, p.x, p.ch, attr)
                except curses.error:
                    pass
        s.addch(self.py, self.px, "@", curses.color_pair(C_PLR) | curses.A_BOLD)
        mode = "自动" if self.auto_mode else ("手动" if self.script else "无脚本")
        cd = self.race_skill_cd
        cd_str = "就绪" if cd == 0 else f"CD{cd:>2}"
        eq = f"{self.race['sym']} {self.race['name'][:2]} ⚔{self.atk_bonus} 🛡{self.def_bonus + self.temp_def_bonus} [{cd_str}]"
        if self.boss:
            eq += " ☠BOSS"
        bar = (f" {eq} Lv{self.level} HP{self.hp:>2}/{self.max_hp} E{self.exp:>2}/{self.exp_next} "
               f"深{self.depth:>2} 金{self.gold:>4} 分{self.score:>4} 杀{self.kills:>2} "
               f"物{len(self.items):>2} 怪{len(self.monsters):>2} "
               f"| {self.dungeon_name} | {mode}")
        s.addstr(self.H, 0, truncate(bar, W - 1), curses.color_pair(C_BAR) | curses.A_BOLD)
        s.addstr(self.H + 1, 0, truncate(self.msg, W - 1), curses.color_pair(C_MSG))
        if self.popup:
            self._draw_popup(s, W, H)
        if self.inv_open:
            try:
                self._draw_inventory(s, W, H)
            except Exception as e:
                self.msg = f"[draw err] {e}"
        if self.shop_open:
            try:
                self._draw_shop(s, W, H)
            except Exception as e:
                self.msg = f"[shop err] {e}"
        s.refresh()

    def run(self, s):
        curses.curs_set(0); s.keypad(True)
        self._init_colors(); self._draw(s)
        while True:
            if self.auto_mode and not self.dead:
                s.nodelay(True)
                k = s.getch()
                s.nodelay(False)
                if k != -1:
                    self.auto_mode = False
                    if k in (ord("q"), ord("Q")): break
                    self._draw(s); continue
                self._script_step(); self._draw(s)
                curses.napms(50); continue
            k = s.getch()
            if self.popup:
                was_final = self.dead or getattr(self, "won", False)
                if k == ord("H"):
                    self.popup = None
                    self._show_leaderboard()
                elif k in (ord("q"), ord("Q")):
                    if was_final:
                        break
                    self.popup = None
                elif was_final:
                    pass  # 死亡/胜利弹窗不响应其他键
                else:
                    self.popup = None
                self._draw(s)
                continue

            if self.shop_open:
                if k in (27, ord("q"), ord("Q")):
                    self.shop_open = False
                elif k == 9:
                    self.shop_mode = "sell" if self.shop_mode == "buy" else "buy"
                    self.shop_cursor = 0
                elif k in (curses.KEY_DOWN, ord("j")):
                    self._shop_move(+1)
                elif k in (curses.KEY_UP, ord("k")):
                    self._shop_move(-1)
                elif k in (10, 13, curses.KEY_ENTER, ord(" ")):
                    if self.shop_mode == "buy":
                        self._shop_buy()
                    else:
                        self._shop_sell()
                self._draw(s)
                continue

            if self.inv_open:
                if k in (ord("i"), 27, ord("q"), ord("Q")):
                    self._close_inventory()
                elif k in (curses.KEY_DOWN, ord("j")):
                    self._inv_move(+1)
                elif k in (curses.KEY_UP, ord("k")):
                    self._inv_move(-1)
                elif k in (curses.KEY_LEFT, ord("u"), 10, 13):
                    self._inv_use()
                elif k in (curses.KEY_RIGHT, ord("d")):
                    self._inv_destroy()
                self._draw(s)
                continue

            if k in (ord("q"), ord("Q")): break
            elif k == ord("H"):   self._show_leaderboard()
            elif k == ord("i"):   self._open_inventory()
            elif k == ord("R"):   self._use_race_skill()
            elif k == ord("u"):
                if not self._use_healing():
                    self.msg = "没有可用的治疗药水/食物"
            elif k == ord("l"):   self._look()
            elif k == ord("s"):
                if self.script and not self.dead:
                    self.auto_mode = True; self.msg = "脚本启动……"
                else:
                    self.msg = self.script_error or "无脚本"
            elif k == ord("r"):   self._load_script()
            elif k == ord("T"):   self._cycle_theme()
            elif k == curses.KEY_UP:    self._move(0, -1)
            elif k == curses.KEY_DOWN:  self._move(0, 1)
            elif k == curses.KEY_LEFT:  self._move(-1, 0)
            elif k == curses.KEY_RIGHT: self._move(1, 0)
            elif k == ord("k"):    self._move(0, -1)
            elif k == ord("j"):    self._move(0, 1)
            elif k == ord("h"):    self._move(-1, 0)
            elif k == ord("n"):    self._move(1, 0)   # n = 右移（替代 l）
            self._draw(s)


def select_race(stdscr):
    """游戏内种族选择前端，返回选中的 race key"""
    if curses.has_colors():
        curses.start_color()
        try:
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        curses.init_pair(1, curses.COLOR_CYAN, bg)
        curses.init_pair(2, curses.COLOR_YELLOW, bg)
        curses.init_pair(3, curses.COLOR_GREEN, bg)
        curses.init_pair(4, curses.COLOR_WHITE, bg)
        curses.init_pair(5, curses.COLOR_MAGENTA, bg)
    else:
        bg = 0

    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.nodelay(False)

    keys = list(RACES.keys())
    saved = load_player_race()
    cur = keys.index(saved) if saved in keys else 0

    while True:
        stdscr.clear()
        H, W = stdscr.getmaxyx()

        banner = "════════════════════════════════════"
        title  = "         选 择 你 的 种 族         "
        top = max(0, (W - len(banner)) // 2)
        try:
            stdscr.addstr(1, top, banner, curses.color_pair(5) | curses.A_BOLD)
            stdscr.addstr(2, top, title,  curses.color_pair(2) | curses.A_BOLD)
            stdscr.addstr(3, top, banner, curses.color_pair(5) | curses.A_BOLD)
        except curses.error:
            pass

        list_x = 3
        list_y = 6
        for i, k in enumerate(keys):
            r = RACES[k]
            sel = (i == cur)
            mark = "▶" if sel else " "
            line = f" {mark} {r['sym']}  {pad(truncate(r['name'], 8), 8)}"
            attr = (curses.color_pair(2) | curses.A_BOLD | curses.A_REVERSE
                    if sel else curses.color_pair(4))
            try:
                stdscr.addstr(list_y + i * 2, list_x, line, attr)
                stdscr.addstr(list_y + i * 2 + 1, list_x + 4, r['desc'],
                              curses.color_pair(4) | curses.A_DIM)
            except curses.error:
                pass

        r = RACES[keys[cur]]
        det_x = list_x + 26
        det_y = list_y
        lines = [
            (f"{r['sym']}  {r['name']}",  curses.color_pair(2) | curses.A_BOLD),
            ("", 0),
            (r['desc'],                    curses.color_pair(4)),
            ("", 0),
            (f"生命   {r['hp']:+d}",       curses.color_pair(4)),
            (f"攻击   {r['atk']:+d}",      curses.color_pair(4)),
            (f"防御   {r['def']:+d}",      curses.color_pair(4)),
            (f"经验   ×{r['exp_mul']:.2f}", curses.color_pair(4)),
            ("", 0),
            (f"技能 · {r['skill']['name']}", curses.color_pair(3) | curses.A_BOLD),
            (f"冷却 {r['skill']['cooldown']} 回合", curses.color_pair(3)),
            (r['skill']['desc'].format(amount=r['skill'].get('amount', 0)),
             curses.color_pair(3)),
        ]
        for i, (line, attr) in enumerate(lines):
            if not line:
                continue
            try:
                stdscr.addstr(det_y + i, det_x, line, attr)
            except curses.error:
                pass

        hint = " ↑/↓ 切换     Enter / Space 确认 "
        hy = H - 2
        hx = max(0, (W - len(hint)) // 2)
        try:
            stdscr.addstr(hy, hx, hint, curses.color_pair(1) | curses.A_BOLD)
        except curses.error:
            pass

        stdscr.refresh()
        k = stdscr.getch()

        if k in (curses.KEY_UP, ord('k')):
            cur = (cur - 1) % len(keys)
        elif k in (curses.KEY_DOWN, ord('j')):
            cur = (cur + 1) % len(keys)
        elif k in (10, 13, curses.KEY_ENTER, ord(' ')):
            save_player_race(keys[cur])
            return keys[cur]
        elif k in (ord('q'), ord('Q')):
            save_player_race(keys[cur])
            return keys[cur]


def title_screen(stdscr, state):
    """主菜单。返回 'new' / 'continue' / 'quit'。state 为存档 dict 或 None"""
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.nodelay(False)
    if curses.has_colors():
        try:
            curses.start_color()
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        try:
            curses.init_pair(1, curses.COLOR_CYAN, bg)
            curses.init_pair(2, curses.COLOR_YELLOW, bg)
            curses.init_pair(3, curses.COLOR_GREEN, bg)
        except curses.error:
            pass

    items = [("New Game", "new")]
    if state is not None:
        items.append((
            f"Continue  ·  第{state.get('depth',1)}层 "
            f"·  {state.get('score',0)}分  "
            f"Lv{state.get('level',1)}",
            "continue",
        ))
    items.append(("Quit", "quit"))
    cur = 0

    while True:
        stdscr.clear()
        H, W = stdscr.getmaxyx()

        title = "N E T H A C K   ·   R E M A K E"
        sub   = "将 军 的 命 令"
        try:
            stdscr.addstr(3, max(0, (W - len(title)) // 2), title,
                          curses.color_pair(1) | curses.A_BOLD)
            stdscr.addstr(5, max(0, (W - len(sub)) // 2), sub,
                          curses.color_pair(2))
        except curses.error:
            pass

        list_y = max(8, H // 2 - 2)
        for i, (label, _) in enumerate(items):
            sel = (i == cur)
            mark = "▶ " if sel else "  "
            line = f"{mark}{label}"
            x = max(2, (W - len(line)) // 2)
            attr = (curses.color_pair(2) | curses.A_BOLD | curses.A_REVERSE
                    if sel else curses.color_pair(3))
            try:
                stdscr.addstr(list_y + i * 2, x, line, attr)
            except curses.error:
                pass

        hint = " ↑/↓ 选择    Enter 确认    Q 退出 "
        try:
            stdscr.addstr(H - 2, max(0, (W - len(hint)) // 2), hint,
                          curses.color_pair(3) | curses.A_DIM)
        except curses.error:
            pass

        stdscr.refresh()
        k = stdscr.getch()
        if k in (curses.KEY_UP, ord('k')):
            cur = (cur - 1) % len(items)
        elif k in (curses.KEY_DOWN, ord('j')):
            cur = (cur + 1) % len(items)
        elif k in (10, 13, curses.KEY_ENTER, ord(' ')):
            return items[cur][1]
        elif k in (ord('q'), ord('Q')):
            return "quit"


if __name__ == "__main__":
    data = load_data()
    name = get_player_name()

    def _run(stdscr):
        while True:
            state = Game.load_state()
            choice = title_screen(stdscr, state)
            if choice == "quit":
                return
            if choice == "new":
                try:
                    SAVE_FILE.unlink()
                except FileNotFoundError:
                    pass
                state = None
                break
            if choice == "continue" and state is not None:
                break
        if state is not None:
            g = Game(data, race_key=state.get("race_key"))
            g.player_name = state.get("player_name", name)
            g.restore(state)
        else:
            race_key = select_race(stdscr)
            g = Game(data, race_key=race_key)
            g.player_name = name
        g.run(stdscr)

    curses.wrapper(_run)
