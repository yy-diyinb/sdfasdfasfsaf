#!/usr/bin/env python3
"""从本地 NetHack 源码提取资源：符号、怪物、物品、文本"""
import re, json
from pathlib import Path

BASE = Path(__file__).parent
RAW_DIR = BASE / "raw"
OUT_DIR = BASE / "data"
RAW_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)

SRC_DIR = BASE / "nethack-3.6.7"

LOCAL_FILES = {
    "symbols":     SRC_DIR / "dat" / "symbols",
    "monst.c":     SRC_DIR / "src" / "monst.c",
    "objects.c":   SRC_DIR / "src" / "objects.c",
    "data.base":   SRC_DIR / "dat" / "data.base",
    "oracles.txt": SRC_DIR / "dat" / "oracles.txt",
    "rumors.tru":  SRC_DIR / "dat" / "rumors.tru",
    "rumors.fal":  SRC_DIR / "dat" / "rumors.fal",
    "engrave.txt": SRC_DIR / "dat" / "engrave.txt",
    "epitaph.txt": SRC_DIR / "dat" / "epitaph.txt",
    "bogusmon.txt":SRC_DIR / "dat" / "bogusmon.txt",
}

DEFAULT_SYMBOLS = {
    "S_stone":" ","S_vwall":"|","S_hwall":"-",
    "S_tlcorn":"-","S_trcorn":"-","S_blcorn":"-","S_brcorn":"-",
    "S_crwall":"+","S_tuwall":"-","S_tdwall":"-","S_tlwall":"-","S_trwall":"-",
    "S_ndoor":"+","S_vodoor":"+","S_hodoor":"+","S_vcdoor":"|","S_hcdoor":"|",
    "S_room":".","S_corr":"#","S_litcorr":"#",
    "S_upstair":"<","S_dnstair":">","S_upladder":"<","S_dnladder":">",
    "S_altar":"_","S_grave":"|","S_throne":"\\","S_sink":"}","S_fountain":"{",
    "S_pool":"}","S_lava":"}","S_water":"}","S_ice":".","S_mud":".","S_grass":'"',"S_rope":"\\",
    "S_ant":"a","S_blob":"b","S_cockatrice":"c","S_dog":"d","S_eye":"e","S_feline":"f",
    "S_gremlin":"g","S_humanoid":"h","S_imp":"i","S_jelly":"j","S_kobold":"k",
    "S_leprechaun":"l","S_mimic":"m","S_nymph":"n","S_orc":"o","S_piercer":"p",
    "S_quadruped":"q","S_rodent":"r","S_spider":"s","S_trapper":"t","S_unicorn":"u",
    "S_vortex":"v","S_worm":"w","S_xan":"x","S_light":"y","S_zruty":"z",
    "S_human":"@","S_giant":"H","S_dragon":"D","S_demon":"&","S_golem":"'","S_ghost":" ",
    "S_weapon":")","S_armor":"[","S_ring":"=","S_amulet":'"',"S_tool":"(",
    "S_food":"%","S_potion":"!","S_scroll":"?","S_spellbook":"+","S_wand":"/",
    "S_gem":"*","S_gold":"$","S_ball":"0","S_chain":"_","S_venom":".",
    "S_vbeam":"|","S_hbeam":"-","S_lslant":"\\","S_rslant":"/","S_digbeam":"*",
    "S_explode1":"/","S_explode2":"|","S_explode3":"\\","S_explode4":"-",
    "S_swarm":"*","S_zap":"|","S_cloud":"#",
}


def load_local(name):
    cached = RAW_DIR / name
    if cached.exists() and cached.stat().st_size > 0:
        print(f"  [=] {name} 使用缓存")
        return cached.read_text(errors="replace")
    src = LOCAL_FILES.get(name)
    if src and src.exists():
        print(f"  [>] 从 {src} 复制")
        text = src.read_text(errors="replace")
        cached.write_text(text)
        return text
    print(f"  [!] 找不到 {name}: {src}")
    return None


# ========== 符号 ==========
def decode_val(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        v = v[1:-1]
    if "\\" in v:
        try:
            v = v.encode("latin-1").decode("unicode_escape")
        except Exception:
            pass
    return v if v != "" else " "


def parse_symbols(text):
    modes = {"default": dict(DEFAULT_SYMBOLS)}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("start:"):
            current = line.split(":", 1)[1].strip()
            modes[current] = dict(DEFAULT_SYMBOLS)
            continue
        if line.startswith("finish"):
            current = None
            continue
        if current is None:
            continue
        m = re.match(r"(\S+?)\s*:\s*(.*)$", line)
        if m:
            modes[current][m.group(1)] = decode_val(m.group(2))
    return modes


# ========== 怪物 / 物品 ==========
def parse_monsters(text):
    out = []
    pat = re.compile(r'MON\(\s*"([^"]+)"\s*,\s*(\w+)\s*,\s*LVL\(\s*(\d+)', re.DOTALL)
    for m in pat.finditer(text):
        out.append({"name": m.group(1), "symbol_key": m.group(2), "level": int(m.group(3))})
    return out


def parse_objects(text):
    class_symbol = {
        "WEAPON": ")", "ARMOR": "[", "RING": "=", "AMULET": '"',
        "TOOL": "(", "FOOD": "%", "POTION": "!", "SCROLL": "?",
        "SPBOOK": "+", "WAND": "/", "COIN": "$", "GEM": "*",
        "ROCK": "*", "BALL": "0", "CHAIN": "_", "VENOM": ".",
    }
    items, seen = [], set()
    pat = re.compile(r'\b(' + '|'.join(class_symbol.keys()) + r')\s*\(\s*"([^"]+)"', re.DOTALL)
    for m in pat.finditer(text):
        cls, name = m.group(1), m.group(2)
        if (cls, name) in seen:
            continue
        seen.add((cls, name))
        items.append({
            "class": cls, "name": name,
            "symbol_key": "S_" + cls.lower(),
            "char": class_symbol[cls],
        })
    return items


# ========== 文本 ==========
def parse_data_base(text):
    """第一行名字，缩进行描述，空行或 # 分隔"""
    entries = {}
    cur_name = None
    cur_lines = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            if cur_name:
                entries[cur_name] = " ".join(cur_lines)
                cur_name = None; cur_lines = []
            continue
        if raw[:1] in ("\t", " ") and cur_name is not None:
            cur_lines.append(line.strip())
        else:
            if cur_name:
                entries[cur_name] = " ".join(cur_lines)
            cur_name = line.strip()
            cur_lines = []
    if cur_name:
        entries[cur_name] = " ".join(cur_lines)
    return entries


def parse_oracles(text):
    """oracles.txt：条目之间用 '-----' 分隔"""
    oracles, buf = [], []
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("#"):
            continue
        s = line.strip()
        if s and set(s) == {"-"} and len(s) >= 3:
            if buf:
                oracles.append(" ".join(buf)); buf = []
            continue
        if not s:
            continue
        buf.append(s)
    if buf:
        oracles.append(" ".join(buf))
    return oracles


def parse_simple_lines(text):
    """每行一条：过滤注释与空行"""
    out = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


# ========== 主流程 ==========
def main():
    print("[*] 提取 NetHack 资源（本地源码）")
    print(f"    源码目录: {SRC_DIR}")

    raw = {}
    for name in LOCAL_FILES:
        text = load_local(name)
        if text:
            raw[name] = text

    out = {}

    if "symbols" in raw:
        print("[*] 解析符号表 ...")
        out["symbols"] = parse_symbols(raw["symbols"])
        for mode, syms in out["symbols"].items():
            print(f"    {mode}: {len(syms)} 个符号")

    if "monst.c" in raw:
        print("[*] 解析怪物数据 ...")
        out["monsters"] = parse_monsters(raw["monst.c"])
        print(f"    {len(out['monsters'])} 种怪物")

    if "objects.c" in raw:
        print("[*] 解析物品数据 ...")
        out["items"] = parse_objects(raw["objects.c"])
        print(f"    {len(out['items'])} 种物品")

    if "data.base" in raw:
        print("[*] 解析 data.base ...")
        out["descriptions"] = parse_data_base(raw["data.base"])
        print(f"    {len(out['descriptions'])} 条描述")

    if "oracles.txt" in raw:
        print("[*] 解析 oracles.txt ...")
        out["oracles"] = parse_oracles(raw["oracles.txt"])
        print(f"    {len(out['oracles'])} 条神谕")

    if "rumors.tru" in raw:
        out["rumors_true"] = parse_simple_lines(raw["rumors.tru"])
        print(f"[*] rumors.tru: {len(out['rumors_true'])} 条")
    if "rumors.fal" in raw:
        out["rumors_false"] = parse_simple_lines(raw["rumors.fal"])
        print(f"[*] rumors.fal: {len(out['rumors_false'])} 条")
    if "engrave.txt" in raw:
        out["engravings"] = parse_simple_lines(raw["engrave.txt"])
        print(f"[*] engrave.txt: {len(out['engravings'])} 条")
    if "epitaph.txt" in raw:
        out["epitaphs"] = parse_simple_lines(raw["epitaph.txt"])
        print(f"[*] epitaph.txt: {len(out['epitaphs'])} 条")
    if "bogusmon.txt" in raw:
        out["bogus_monsters"] = parse_simple_lines(raw["bogusmon.txt"])
        print(f"[*] bogusmon.txt: {len(out['bogus_monsters'])} 条")

    if not out:
        print("[!] 没提取到任何数据")
        return

    f = OUT_DIR / "nethack_data.json"
    f.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"[+] 已写出 {f}")


if __name__ == "__main__":
    main()
