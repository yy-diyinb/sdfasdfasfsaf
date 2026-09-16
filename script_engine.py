"""玩家脚本的沙箱与 API"""
import ast
import random as _random
from collections import deque


class ScriptError(Exception):
    pass


class TurnEnd(Exception):
    """动作执行后由 API 内部抛出，结束本回合"""


# 允许脚本使用的内置函数
ALLOWED_BUILTINS = {
    "abs": abs, "min": min, "max": max, "sum": sum, "len": len,
    "range": range, "enumerate": enumerate, "zip": zip,
    "list": list, "dict": dict, "set": set, "tuple": tuple,
    "str": str, "int": int, "float": float, "bool": bool,
    "sorted": sorted, "reversed": reversed, "any": any, "all": all,
    "print": print, "round": round, "pow": pow, "divmod": divmod,
    "random": _random,  # 暴露 random 模块
}


def _validate_ast(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ScriptError("不允许 import")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise ScriptError("不允许 global / nonlocal")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ScriptError(f"不允许访问下划线属性: {node.attr}")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ScriptError(f"不允许使用下划线名: {node.id}")


class Script:
    """加载并编译一个玩家脚本"""

    def __init__(self, path):
        self.path = path
        self.source = path.read_text(encoding="utf-8")
        try:
            self.tree = ast.parse(self.source, filename=str(path))
        except SyntaxError as e:
            raise ScriptError(f"语法错误 line {e.lineno}: {e.msg}")
        _validate_ast(self.tree)
        self.code = compile(self.tree, str(path), "exec")

    def load(self):
        env = {"__builtins__": ALLOWED_BUILTINS}
        try:
            exec(self.code, env)
        except Exception as e:
            raise ScriptError(f"执行失败: {e}")
        fn = env.get("step")
        if not callable(fn):
            raise ScriptError("脚本必须定义 step(api) 函数")
        return fn


class API:
    """暴露给玩家脚本的接口"""

    def __init__(self, game):
        self._g = game
        self.turn = 0

    # ---------- 只读状态 ----------
    @property
    def hp(self):       return self._g.hp
    @property
    def max_hp(self):   return self._g.max_hp
    @property
    def px(self):       return self._g.px
    @property
    def py(self):       return self._g.py
    @property
    def kills(self):    return self._g.kills
    @property
    def score(self):    return self._g.score
    @property
    def dead(self):     return self._g.dead
    @property
    def map_size(self): return (self._g.W, self._g.H)

    # ---------- 查询 ----------
    def monsters(self):
        """[(name, x, y, hp, level), ...]"""
        return [(m["name"], m["x"], m["y"], m["hp"], m["level"])
                for m in self._g.monsters]

    def items(self):
        """[(name, x, y, class), ...]"""
        return [(it["name"], it["x"], it["y"], it["class"])
                for it in self._g.items]

    def nearest_monster(self):
        if not self._g.monsters:
            return None
        m = min(self._g.monsters,
                key=lambda m: abs(m["x"] - self.px) + abs(m["y"] - self.py))
        return (m["name"], m["x"], m["y"], m["hp"], m["level"])

    def nearest_item(self):
        if not self._g.items:
            return None
        it = min(self._g.items,
                 key=lambda i: abs(i["x"] - self.px) + abs(i["y"] - self.py))
        return (it["name"], it["x"], it["y"], it["class"])

    def distance_to(self, x, y):
        return abs(self.px - x) + abs(self.py - y)

    def is_walkable(self, x, y):
        g = self._g
        return (0 <= x < g.W and 0 <= y < g.H
                and g.map[y][x] in g.walkable)

    # ---------- 动作（调用后本回合结束） ----------
    def move(self, dx, dy):
        dx = (dx > 0) - (dx < 0)
        dy = (dy > 0) - (dy < 0)
        if (dx, dy) != (0, 0):
            self._g._move(dx, dy)
        raise TurnEnd()

    def move_to(self, tx, ty):
        nx, ny = self._bfs_next(tx, ty)
        if nx is not None:
            self._g._move(nx - self.px, ny - self.py)
        raise TurnEnd()

    def attack(self, x, y):
        for m in list(self._g.monsters):
            if m["x"] == x and m["y"] == y:
                if self.distance_to(x, y) <= 1:
                    self._g._attack(m)
                else:
                    nx, ny = self._bfs_next(x, y)
                    if nx is not None:
                        self._g._move(nx - self.px, ny - self.py)
                raise TurnEnd()
        raise TurnEnd()

    def pickup(self):
        self._g._auto_pickup()
        raise TurnEnd()

    def log(self, msg):
        self._g.msg = str(msg)[:60]

    # ---------- 内部：BFS 寻路下一步 ----------
    def _bfs_next(self, tx, ty):
        g = self._g
        start = (self.px, self.py)
        if start == (tx, ty):
            return None
        q = deque([start])
        parent = {start: None}
        while q:
            x, y = q.popleft()
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nx, ny = x + dx, y + dy
                if (nx, ny) in parent:
                    continue
                if not (0 <= nx < g.W and 0 <= ny < g.H):
                    continue
                if g.map[ny][nx] not in g.walkable and (nx, ny) != (tx, ty):
                    continue
                if (nx, ny) != (tx, ty) and any(
                        m["x"] == nx and m["y"] == ny for m in g.monsters):
                    continue
                parent[(nx, ny)] = (x, y)
                if (nx, ny) == (tx, ty):
                    cur = (nx, ny)
                    while parent[cur] and parent[cur] != start:
                        cur = parent[cur]
                    return cur
                q.append((nx, ny))
        return None
