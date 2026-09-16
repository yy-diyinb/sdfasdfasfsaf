"""rl_lang.py — Roguelike Script (RL) 语言的词法、语法与解释器"""

import re
from collections import ChainMap


class RLError(Exception): pass
class TurnEnd(Exception): pass
class _ReturnSignal(Exception):
    def __init__(self, value): self.value = value
class _BreakSignal(Exception): pass
class _ContinueSignal(Exception): pass


# ============ 词法分析 ============
KEYWORDS = {"if", "else", "while", "for", "in", "var", "func",
            "return", "true", "false", "null", "and", "or", "not",
            "break", "continue"}

TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>\#[^\n]*)
  | (?P<num>\d+\.\d+|\d+)
  | (?P<str>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>==|!=|<=|>=|\+=|-=|\*=|/=|%=|&&|\|\||[+\-*/%<>=(){}\[\],.!;:])
""", re.VERBOSE)


class Token:
    __slots__ = ("kind", "value", "line", "col")
    def __init__(self, kind, value, line, col):
        self.kind = kind; self.value = value; self.line = line; self.col = col
    def __repr__(self):
        return f"Token({self.kind},{self.value!r},L{self.line})"


def _unescape(s):
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            nxt = s[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r",
                        "\\": "\\", '"': '"', "'": "'"}.get(nxt, nxt))
            i += 2
        else:
            out.append(c); i += 1
    return "".join(out)


def tokenize(src):
    tokens, pos, line, col = [], 0, 1, 1
    while pos < len(src):
        m = TOKEN_RE.match(src, pos)
        if not m:
            raise RLError(f"line {line}: 无法识别的字符 {src[pos]!r}")
        text = m.group()
        kind = m.lastgroup
        if kind == "ws":
            nl = text.count("\n")
            if nl: line += nl; col = 1
            else:  col += len(text)
        elif kind == "comment":
            pass
        elif kind == "num":
            v = float(text) if "." in text else int(text)
            tokens.append(Token("NUM", v, line, col))
        elif kind == "str":
            tokens.append(Token("STR", _unescape(text[1:-1]), line, col))
        elif kind == "ident":
            if text in KEYWORDS: tokens.append(Token("KW", text, line, col))
            else:                tokens.append(Token("IDENT", text, line, col))
        elif kind == "op":
            tokens.append(Token("OP", text, line, col))
        pos = m.end(); col += len(text)
    tokens.append(Token("EOF", None, line, col))
    return tokens


# ============ 语法分析 ============
class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self, off=0): return self.tokens[self.pos + off]
    def advance(self):
        t = self.tokens[self.pos]; self.pos += 1; return t
    def at(self, kind, value=None):
        t = self.peek()
        return t.kind == kind and (value is None or t.value == value)
    def eat(self, kind, value=None):
        if self.at(kind, value): return self.advance()
        return None
    def expect(self, kind, value=None):
        t = self.advance()
        if t.kind != kind or (value is not None and t.value != value):
            raise RLError(f"line {t.line}: 期望 {value or kind}，得到 {t.value!r}")
        return t

    def parse(self):
        out = []
        while not self.at("EOF"):
            out.append(self.stmt())
        return out

    # ---- 语句 ----
    def stmt(self):
        t = self.peek()
        if t.kind == "KW":
            if t.value == "var":     return self.var_decl()
            if t.value == "if":      return self.if_stmt()
            if t.value == "while":   return self.while_stmt()
            if t.value == "for":     return self.for_stmt()
            if t.value == "func":    return self.func_decl()
            if t.value == "return":  return self.return_stmt()
            if t.value == "break":   self.advance(); self.eat("OP",";"); return ("break",)
            if t.value == "continue":self.advance(); self.eat("OP",";"); return ("continue",)
        if t.kind == "OP" and t.value == "{":
            return ("block", self.block())
        # 表达式 / 赋值
        expr = self.expr()
        t2 = self.peek()
        if t2.kind == "OP" and t2.value == "=":
            self.advance()
            rhs = self.expr()
            self.eat("OP", ";")
            if expr[0] != "var":
                raise RLError(f"line {t.line}: 赋值左侧必须是变量")
            return ("assign", expr[1], rhs)
        if t2.kind == "OP" and t2.value in ("+=", "-=", "*=", "/=", "%="):
            op = t2.value[0]
            self.advance()
            rhs = self.expr()
            self.eat("OP", ";")
            if expr[0] != "var":
                raise RLError(f"line {t.line}: 复合赋值左侧必须是变量")
            return ("assign", expr[1], ("bin", op, expr, rhs))
        self.eat("OP", ";")
        return ("expr_stmt", expr)

    def block(self):
        self.expect("OP", "{")
        out = []
        while not self.at("OP", "}"):
            out.append(self.stmt())
        self.expect("OP", "}")
        return out

    def var_decl(self):
        self.expect("KW", "var")
        name = self.expect("IDENT").value
        self.expect("OP", "=")
        expr = self.expr()
        self.eat("OP", ";")
        return ("var_decl", name, expr)

    def if_stmt(self):
        self.expect("KW", "if")
        self.expect("OP", "(")
        cond = self.expr()
        self.expect("OP", ")")
        then = self.block()
        else_ = None
        if self.eat("KW", "else"):
            if self.at("KW", "if"):
                else_ = [self.if_stmt()]
            else:
                else_ = self.block()
        return ("if", cond, then, else_)

    def while_stmt(self):
        self.expect("KW", "while")
        self.expect("OP", "(")
        cond = self.expr()
        self.expect("OP", ")")
        body = self.block()
        return ("while", cond, body)

    def for_stmt(self):
        self.expect("KW", "for")
        self.expect("OP", "(")
        var = self.expect("IDENT").value
        self.expect("KW", "in")
        seq = self.expr()
        self.expect("OP", ")")
        body = self.block()
        return ("for", var, seq, body)

    def func_decl(self):
        self.expect("KW", "func")
        name = self.expect("IDENT").value
        self.expect("OP", "(")
        params = []
        if not self.at("OP", ")"):
            while True:
                params.append(self.expect("IDENT").value)
                if not self.eat("OP", ","): break
        self.expect("OP", ")")
        body = self.block()
        return ("func_decl", name, params, body)

    def return_stmt(self):
        self.expect("KW", "return")
        if self.at("OP", ";"):
            self.advance()
            return ("return", None)
        e = self.expr()
        self.eat("OP", ";")
        return ("return", e)

    # ---- 表达式（优先级从低到高） ----
    def expr(self):       return self.or_expr()
    def or_expr(self):
        left = self.and_expr()
        while self.at("KW","or") or self.at("OP","||"):
            self.advance()
            right = self.and_expr()
            left = ("bin","or",left,right)
        return left
    def and_expr(self):
        left = self.eq_expr()
        while self.at("KW","and") or self.at("OP","&&"):
            self.advance()
            right = self.eq_expr()
            left = ("bin","and",left,right)
        return left
    def eq_expr(self):
        left = self.cmp_expr()
        while self.at("OP","==") or self.at("OP","!="):
            op = self.advance().value
            right = self.cmp_expr()
            left = ("bin",op,left,right)
        return left
    def cmp_expr(self):
        left = self.add_expr()
        while self.at("OP","<") or self.at("OP","<=") or \
              self.at("OP",">") or self.at("OP",">="):
            op = self.advance().value
            right = self.add_expr()
            left = ("bin",op,left,right)
        return left
    def add_expr(self):
        left = self.mul_expr()
        while self.at("OP","+") or self.at("OP","-"):
            op = self.advance().value
            right = self.mul_expr()
            left = ("bin",op,left,right)
        return left
    def mul_expr(self):
        left = self.unary_expr()
        while self.at("OP","*") or self.at("OP","/") or self.at("OP","%"):
            op = self.advance().value
            right = self.unary_expr()
            left = ("bin",op,left,right)
        return left
    def unary_expr(self):
        if self.at("KW","not") or self.at("OP","!"):
            self.advance()
            return ("un","not",self.unary_expr())
        if self.at("OP","-"):
            self.advance()
            return ("un","-",self.unary_expr())
        return self.postfix_expr()
    def postfix_expr(self):
        e = self.primary()
        while True:
            if self.at("OP","("):
                self.advance()
                args = []
                if not self.at("OP",")"):
                    while True:
                        args.append(self.expr())
                        if not self.eat("OP",","): break
                self.expect("OP",")")
                e = ("call", e, args)
            elif self.at("OP","."):
                self.advance()
                name = self.expect("IDENT").value
                e = ("attr", e, name)
            elif self.at("OP","["):
                self.advance()
                idx = self.expr()
                self.expect("OP","]")
                e = ("index", e, idx)
            else:
                break
        return e
    def _parse_interp(self, s):
        """把 "a${x}b${y}c" 拆成 [("str","a"),("expr",ast),...]"""
        parts = []
        i = 0
        while i < len(s):
            j = s.find("${", i)
            if j == -1:
                parts.append(("str", s[i:])); break
            if j > i:
                parts.append(("str", s[i:j]))
            depth, k = 1, j + 2
            while k < len(s) and depth > 0:
                if s[k] == "{": depth += 1
                elif s[k] == "}": depth -= 1
                k += 1
            if depth != 0:
                raise RLError("字符串插值 ${ 未闭合")
            inner = s[j+2:k-1]
            sub = Parser(tokenize(inner))
            parts.append(("expr", sub.expr()))
            i = k
        return parts

    def primary(self):
        t = self.peek()
        if t.kind == "NUM":   self.advance(); return ("num", t.value)
        if t.kind == "STR":
            self.advance()
            raw = t.value
            if "${" in raw:
                return ("interp", self._parse_interp(raw))
            return ("str", raw)
        if t.kind == "KW":
            if t.value == "true":  self.advance(); return ("bool", True)
            if t.value == "false": self.advance(); return ("bool", False)
            if t.value == "null":  self.advance(); return ("null",)
        if t.kind == "IDENT":
            self.advance(); return ("var", t.value)
        if t.kind == "OP" and t.value == "(":
            self.advance()
            e = self.expr()
            self.expect("OP", ")")
            return e
        if t.kind == "OP" and t.value == "[":
            self.advance()
            elems = []
            if not self.at("OP", "]"):
                while True:
                    elems.append(self.expr())
                    if not self.eat("OP", ","): break
            self.expect("OP", "]")
            return ("list", elems)
        if t.kind == "OP" and t.value == "{":
            self.advance()
            pairs = []
            if not self.at("OP", "}"):
                while True:
                    kt = self.peek()
                    if kt.kind == "STR":
                        self.advance(); key = ("str", kt.value)
                    elif kt.kind == "IDENT":
                        self.advance(); key = ("str", kt.value)
                    else:
                        raise RLError(f"line {kt.line}: 字典键必须是字符串或标识符")
                    self.expect("OP", ":")
                    v = self.expr()
                    pairs.append((key, v))
                    if not self.eat("OP", ","): break
            self.expect("OP", "}")
            return ("dict", pairs)
        raise RLError(f"line {t.line}: 无法解析 {t.value!r}")


# ============ 解释器 ============
class Obj:
    """轻量对象容器"""
    __slots__ = ("_d",)
    def __init__(self, **kw): self._d = kw
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._d.get(name)
    def __repr__(self):
        return f"Obj({self._d})"


def _truthy(v):
    return bool(v) and v is not None


class Interp:
    def __init__(self, engine):
        self.engine = engine

    # ---------- 表达式 ----------
    def eval(self, node, env):
        tag = node[0]
        if tag == "num":  return node[1]
        if tag == "str":  return node[1]
        if tag == "bool": return node[1]
        if tag == "null": return None
        if tag == "list":
            return [self.eval(x, env) for x in node[1]]
        if tag == "dict":
            out = {}
            for k_node, v_node in node[1]:
                out[self.eval(k_node, env)] = self.eval(v_node, env)
            return out
        if tag == "interp":
            parts = []
            for kind, val in node[1]:
                if kind == "str":
                    parts.append(val)
                else:
                    v = self.eval(val, env)
                    if isinstance(v, bool): v = "true" if v else "false"
                    parts.append(str(v))
            return "".join(parts)
        if tag == "var":
            name = node[1]
            if name in env: return env[name]
            raise RLError(f"未定义变量: {name}")
        if tag == "bin":
            op, a, b = node[1], node[2], node[3]
            if op in ("and", "&&"):
                L = self.eval(a, env)
                if not _truthy(L): return L
                return self.eval(b, env)
            if op in ("or", "||"):
                L = self.eval(a, env)
                if _truthy(L): return L
                return self.eval(b, env)
            L = self.eval(a, env); R = self.eval(b, env)
            return self.binop(op, L, R)
        if tag == "un":
            op, x = node[1], node[2]
            v = self.eval(x, env)
            if op == "not": return not _truthy(v)
            if op == "-":   return -v
            raise RLError(f"未知一元运算符: {op}")
        if tag == "call":
            args = [self.eval(a, env) for a in node[2]]
            fn = self.eval(node[1], env)
            if not callable(fn):
                raise RLError(f"不是函数: {node[1]}")
            return fn(*args)
        if tag == "attr":
            obj = self.eval(node[1], env)
            name = node[2]
            if name.startswith("_"):
                raise RLError(f"不允许访问 {name}")
            if obj is None: return None
            if isinstance(obj, dict): return obj.get(name)
            return getattr(obj, name, None)
        if tag == "index":
            obj = self.eval(node[1], env)
            idx = self.eval(node[2], env)
            try:
                return obj[idx]
            except Exception as e:
                raise RLError(f"索引失败: {e}")
        raise RLError(f"未知表达式: {tag}")

    def binop(self, op, a, b):
        try:
            if op == "+":
                # 字符串拼接：任一边是 str 就都转成 str
                if isinstance(a, str) or isinstance(b, str):
                    if isinstance(a, bool): a = "true" if a else "false"
                    if isinstance(b, bool): b = "true" if b else "false"
                    return str(a) + str(b)
                return a + b
            if op == "-": return a - b
            if op == "*": return a * b
            if op == "/":
                if b == 0: raise RLError("除以零")
                return a / b
            if op == "%":
                if b == 0: raise RLError("对零取模")
                return a % b
            if op == "==": return a == b
            if op == "!=": return a != b
            if op == "<":  return a < b
            if op == ">":  return a > b
            if op == "<=": return a <= b
            if op == ">=": return a >= b
        except TypeError as e:
            raise RLError(f"类型不匹配: {e}")
        raise RLError(f"未知运算符: {op}")

    # ---------- 语句 ----------
    def exec(self, node, env):
        tag = node[0]
        if tag == "var_decl":
            env[node[1]] = self.eval(node[2], env); return
        if tag == "assign":
            env[node[1]] = self.eval(node[2], env); return
        if tag == "expr_stmt":
            self.eval(node[1], env); return
        if tag == "block":
            for s in node[1]: self.exec(s, env)
            return
        if tag == "if":
            _, cond, then, else_ = node
            if _truthy(self.eval(cond, env)):
                for s in then: self.exec(s, env)
            elif else_:
                for s in else_: self.exec(s, env)
            return
        if tag == "while":
            _, cond, body = node
            guard = 0
            while _truthy(self.eval(cond, env)):
                guard += 1
                if guard > 10000:
                    raise RLError("while 循环次数超限（防止死循环）")
                try:
                    for s in body: self.exec(s, env)
                except _BreakSignal: break
                except _ContinueSignal: continue
            return
        if tag == "for":
            _, var, seq, body = node
            items = self.eval(seq, env) or []
            for item in items:
                env[var] = item
                try:
                    for s in body: self.exec(s, env)
                except _BreakSignal: break
                except _ContinueSignal: continue
            return
        if tag == "func_decl":
            _, name, params, body = node
            env[name] = self.make_func(params, body, env)
            return
        if tag == "return":
            val = None if node[1] is None else self.eval(node[1], env)
            raise _ReturnSignal(val)
        if tag == "break":    raise _BreakSignal()
        if tag == "continue": raise _ContinueSignal()
        raise RLError(f"未知语句: {tag}")

    def make_func(self, params, body, closure):
        interp = self
        def fn(*args):
            if len(args) != len(params):
                raise RLError(f"函数需要 {len(params)} 个参数，给了 {len(args)} 个")
            local = ChainMap({}, closure)
            for p, a in zip(params, args): local[p] = a
            try:
                for s in body: interp.exec(s, local)
            except _ReturnSignal as r:
                return r.value
            return None
        return fn


# ============ 引擎：把游戏接口注入脚本 ============
class RLEngine:
    def __init__(self, source, game, name="<script>"):
        self.game = game
        self.name = name
        self.globals = {}
        self._install_builtins()

        tokens = tokenize(source)
        stmts = Parser(tokens).parse()
        self.interp = Interp(self)
        try:
            for s in stmts:
                self.interp.exec(s, self.globals)
        except TurnEnd:
            raise RLError("顶层不能执行动作")

    # ---------- 内置函数 ----------
    def _install_builtins(self):
        g = self.globals
        g["move"]            = self._bi_move
        g["move_to"]         = self._bi_move_to
        g["attack"]          = self._bi_attack
        g["pickup"]          = self._bi_pickup
        g["log"]             = self._bi_log
        g["distance_to"]     = self._bi_distance
        g["is_walkable"]     = self._bi_walkable
        g["monsters"]        = self._bi_monsters
        g["items"]           = self._bi_items
        g["nearest_monster"] = self._bi_nearest_monster
        g["nearest_item"]    = self._bi_nearest_item
        g["stairs"]          = self._bi_stairs
        g["use_healing"]     = self._bi_use_healing
        g["auto_manage"]     = self._bi_auto_manage
        g["race_skill"]      = self._bi_race_skill
        g["race_skill_ready"] = self._bi_race_ready
        g["equip_best"]      = self._bi_equip_best
        g["discard_worst"]   = self._bi_discard_worst
        g["inv"]             = self._bi_inv
        g["equipped"]        = self._bi_equipped
        g["reachable"]       = self._bi_reachable
        g["altars"]          = self._bi_altars
        g["nearest_altar"]   = self._bi_nearest_altar
        g["at_altar"]        = self._bi_at_altar
        g["altar_sacrifice"] = self._bi_altar_sacrifice
        g["altar_value"]     = self._bi_altar_value
        g["poisoned"]        = self._bi_poisoned
        g["gold"]            = self._bi_gold
        g["near_shop"]       = self._bi_near_shop
        g["shop_items"]      = self._bi_shop_items
        g["buy"]             = self._bi_buy
        g["sell"]            = self._bi_sell
        # 纯函数
        g["abs"]  = abs
        g["min"]  = min
        g["max"]  = max
        g["len"]  = len
        g["rand"] = self._bi_rand
        g["print"] = self._bi_print
        g["range"] = lambda *a: list(range(*[int(x) for x in a]))
        g["abs"] = abs
        g["min"] = min
        g["max"] = max
        g["len"] = len
        g["contains"] = lambda h, n: str(n) in str(h)
        g["str"]  = str
        g["lower"] = lambda x: str(x).lower()

    def _bi_print(self, *args):
        text = " ".join(str(a) for a in args)
        self.game.msg = f"[print] {text}"[:78]

    def _bi_rand(self, n):
        import random
        return random.randint(0, int(n) - 1) if n > 0 else 0

    # ---------- 玩家状态 ----------
    def _make_me(self):
        g = self.game
        return Obj(hp=g.hp, max_hp=g.max_hp, x=g.px, y=g.py,
                   kills=g.kills, score=g.score, dead=g.dead,
                   level=getattr(g, "level", 1), exp=getattr(g, "exp", 0),
                   depth=getattr(g, "depth", 1),
                   atk_bonus=getattr(g, "atk_bonus", 0),
                   def_bonus=getattr(g, "def_bonus", 0),
                   temp_atk_bonus=getattr(g, "temp_atk_bonus", 0),
                   temp_def_bonus=getattr(g, "temp_def_bonus", 0),
                   poison_turns=getattr(g, "poison_turns", 0),
                   gold=getattr(g, "gold", 0))

    def _make_monster(self, m):
        return Obj(name=m["name"], x=m["x"], y=m["y"],
                   hp=m["hp"], max_hp=m.get("max_hp", m["hp"]),
                   level=m["level"])

    def _make_item(self, it):
        return Obj(name=it["name"], x=it["x"], y=it["y"], cls=it["class"])

    def _bi_monsters(self):
        return [self._make_monster(m) for m in self.game.monsters]

    def _bi_items(self):
        return [self._make_item(it) for it in self.game.items]

    def _bi_nearest_monster(self):
        g = self.game
        if not g.monsters: return None
        df = self._dist_field()
        best, best_d = None, 10**9
        for m in g.monsters:
            d = df[m["y"]][m["x"]]
            if d == -1: continue
            if d < best_d:
                best_d = d; best = m
        return self._make_monster(best) if best else None

    def _bi_nearest_item(self):
        g = self.game
        if not g.items: return None
        df = self._dist_field()
        best, best_d = None, 10**9
        for it in g.items:
            d = df[it["y"]][it["x"]]
            if d == -1: continue
            if d < best_d:
                best_d = d; best = it
        return self._make_item(best) if best else None

    def _bi_race_skill(self):
        g = self.game
        fn = getattr(g, "_use_race_skill", None)
        if fn and getattr(g, "race_skill_cd", 0) == 0:
            fn()
            raise TurnEnd()
        return False

    def _bi_race_ready(self):
        return getattr(self.game, "race_skill_cd", 0) == 0

    def _bi_auto_manage(self):
        """装备最优 + 清理垃圾。不消耗回合，返回是否有变化"""
        g = self.game
        fn = getattr(g, "_auto_manage_inventory", None)
        return bool(fn()) if fn else False

    def _bi_equip_best(self):
        g = self.game
        fn = getattr(g, "_inv_equip_best", None)
        return bool(fn()) if fn else False

    def _bi_discard_worst(self):
        g = self.game
        fn = getattr(g, "_inv_discard_worst", None)
        return (fn() is not None) if fn else False

    def _bi_use_healing(self):
        ok = getattr(self.game, "_use_healing", lambda: False)()
        if ok:
            raise TurnEnd()
        return False

    def _bi_altars(self):
        return [Obj(x=x, y=y) for (x, y) in getattr(self.game, "altars", [])]

    def _bi_nearest_altar(self):
        g = self.game
        if not getattr(g, "altars", None):
            return None
        df = self._dist_field()
        best, best_d = None, 10**9
        for (x, y) in g.altars:
            d = df[y][x]
            if d != -1 and d < best_d:
                best_d, best = d, (x, y)
        if best is None:
            return None
        return Obj(x=best[0], y=best[1], dist=best_d)

    def _bi_at_altar(self):
        g = self.game
        return (g.px, g.py) in getattr(g, "altars", [])

    def _bi_altar_value(self):
        g = self.game
        vals = []
        for it in getattr(g, "inventory", []):
            if it["class"] in ("WEAPON", "ARMOR"):
                try: vals.append(g._inv_item_value(it))
                except Exception: vals.append(1)
        return min(vals) if vals else -1

    def _bi_altar_sacrifice(self):
        g = self.game
        if not self._bi_at_altar(): return False
        fn = getattr(g, "_altar_sacrifice", None)
        if not fn: return False
        before = len(g.inventory)
        fn(g.px, g.py)
        if len(g.inventory) < before:
            raise TurnEnd()
        return False

    def _bi_poisoned(self):
        return getattr(self.game, "poison_turns", 0) > 0

    # ---------- 商店 ----------
    def _bi_gold(self):
        return getattr(self.game, "gold", 0)

    def _bi_near_shop(self):
        g = self.game
        if getattr(g, "shop_pos", None) is None:
            return None
        df = self._dist_field()
        x, y = g.shop_pos
        d = df[y][x]
        if d == -1: return None
        return Obj(x=x, y=y, dist=d)

    def _bi_shop_items(self):
        return [Obj(name=it["name"], cls=it["class"], price=it["price"])
                for it in getattr(self.game, "shop_items", [])]

    def _bi_buy(self, idx):
        g = self.game
        if not getattr(g, "shop_open", False):
            return False
        g.shop_cursor = int(idx)
        g.shop_mode = "buy"
        before = len(g.inventory)
        g._shop_buy()
        return len(g.inventory) > before

    def _bi_sell(self, idx):
        g = self.game
        if not getattr(g, "shop_open", False):
            return False
        g.shop_cursor = int(idx)
        g.shop_mode = "sell"
        before = len(g.inventory)
        g._shop_sell()
        return len(g.inventory) < before

    def _bi_inv(self):
        return [Obj(name=it["name"], cls=it["class"])
                for it in getattr(self.game, "inventory", [])]

    def _bi_equipped(self):
        g = self.game
        w = getattr(g, "weapon", None)
        a = getattr(g, "armor", None)
        return Obj(weapon=w["name"] if w else None,
                   armor=a["name"] if a else None,
                   atk=getattr(g, "atk_bonus", 0),
                   defense=getattr(g, "def_bonus", 0))

    def _bi_stairs(self):
        g = self.game
        x = getattr(g, "dnstair_x", None)
        y = getattr(g, "dnstair_y", None)
        if x is None or y is None:
            return None
        return Obj(x=x, y=y)

    def _dist_field(self):
        """从玩家位置 BFS 的距离场，缓存到 (px,py,turn)"""
        g = self.game
        key = (g.px, g.py, getattr(g, "turn", 0))
        if getattr(self, "_df_key", None) == key and getattr(self, "_df", None):
            return self._df
        from collections import deque
        df = [[-1] * g.W for _ in range(g.H)]
        df[g.py][g.px] = 0
        q = deque([(g.px, g.py)])
        while q:
            x, y = q.popleft()
            nd = df[y][x] + 1
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < g.W and 0 <= ny < g.H and df[ny][nx] == -1:
                    if g.map[ny][nx] in g.walkable:
                        df[ny][nx] = nd
                        q.append((nx, ny))
        self._df = df
        self._df_key = key
        return df

    def _bi_reachable(self, x, y):
        g = self.game
        x, y = int(x), int(y)
        if not (0 <= x < g.W and 0 <= y < g.H): return False
        return self._dist_field()[y][x] != -1

    def _bi_distance(self, x, y):
        return abs(self.game.px - int(x)) + abs(self.game.py - int(y))

    def _bi_walkable(self, x, y):
        g = self.game
        x, y = int(x), int(y)
        return 0 <= x < g.W and 0 <= y < g.H and g.map[y][x] in g.walkable

    def _bi_log(self, msg):
        self.game.msg = str(msg)[:60]

    # ---------- 动作（结束后回合） ----------
    def _bi_move(self, dx, dy):
        dx = (int(dx) > 0) - (int(dx) < 0)
        dy = (int(dy) > 0) - (int(dy) < 0)
        if (dx, dy) == (0, 0):
            g = self.game
            if g.map[g.py][g.px] == "__STAIR__":
                g._descend()
            else:
                g._auto_pickup()
            raise TurnEnd()
        self.game._move(dx, dy)
        raise TurnEnd()

    def _bi_move_to(self, tx, ty):
        import random as _r
        g = self.game
        tx, ty = int(tx), int(ty)
        # 目标就是当前格 → 触发交互
        if (tx, ty) == (g.px, g.py):
            if g.map[ty][tx] == "__STAIR__":
                g._descend()
            else:
                g._auto_pickup()
            raise TurnEnd()
        nxt = self._bfs_next(tx, ty)
        if nxt:
            g._move(nxt[0] - g.px, nxt[1] - g.py)
        else:
            # 不可达 → 随机走一步，避免无限循环
            dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
            _r.shuffle(dirs)
            for dx, dy in dirs:
                nx, ny = g.px + dx, g.py + dy
                if 0 <= nx < g.W and 0 <= ny < g.H and g.map[ny][nx] in g.walkable:
                    g._move(dx, dy)
                    break
        raise TurnEnd()

    def _bi_attack(self, x, y):
        import random as _r
        g = self.game
        x, y = int(x), int(y)
        for m in list(g.monsters):
            if m["x"] == x and m["y"] == y:
                if self._bi_distance(x, y) <= 1:
                    g._attack(m)
                else:
                    nxt = self._bfs_next(x, y)
                    if nxt:
                        g._move(nxt[0] - g.px, nxt[1] - g.py)
                    else:
                        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
                        _r.shuffle(dirs)
                        for dx, dy in dirs:
                            nx, ny = g.px + dx, g.py + dy
                            if 0 <= nx < g.W and 0 <= ny < g.H and g.map[ny][nx] in g.walkable:
                                g._move(dx, dy); break
                raise TurnEnd()
        raise TurnEnd()

    def _bi_pickup(self):
        self.game._auto_pickup()
        raise TurnEnd()

    # ---------- 每回合调用 step() ----------
    def step(self):
        self.globals["me"] = self._make_me()
        fn = self.globals.get("step")
        if not callable(fn):
            raise RLError("脚本必须定义 func step() { ... }")
        try:
            fn()
        except TurnEnd:
            pass

    # ---------- BFS 寻路下一步 ----------
    def _bfs_next(self, tx, ty):
        from collections import deque
        g = self.game
        start = (g.px, g.py)
        if start == (tx, ty): return None
        if not (0 <= tx < g.W and 0 <= ty < g.H): return None
        q = deque([start])
        parent = {start: None}
        while q:
            x, y = q.popleft()
            for dx, dy in ((0,-1),(0,1),(-1,0),(1,0)):
                nx, ny = x+dx, y+dy
                if (nx, ny) in parent: continue
                if not (0 <= nx < g.W and 0 <= ny < g.H): continue
                if g.map[ny][nx] not in g.walkable: continue
                parent[(nx, ny)] = (x, y)
                if (nx, ny) == (tx, ty):
                    cur = (nx, ny)
                    while parent[cur] and parent[cur] != start:
                        cur = parent[cur]
                    return cur
                q.append((nx, ny))
        return None
