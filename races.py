"""races.py — 种族特质：局外选择，带入局内"""
import json
from pathlib import Path

RACE_FILE = Path(__file__).parent / "data" / "race.json"

# ============ 种族定义 ============
# hp: max_hp 加成
# atk: 攻击加成
# def: 防御加成
# exp_mul: 经验倍率
# skill: 主动技能（每 X 回合冷却）
RACES = {
    "human": {
        "name": "人类",
        "sym": "☺",
        "desc": "均衡 · 经验丰富",
        "hp": 0, "atk": 0, "def": 0,
        "exp_mul": 1.25,
        "skill": {
            "name": "专注",
            "cooldown": 15,
            "desc": "立即获得 {amount} 点经验",
            "amount": 15,
        },
    },
    "elf": {
        "name": "精灵",
        "sym": "❋",
        "desc": "迅捷 · 感知敏锐",
        "hp": -4, "atk": 1, "def": 0,
        "exp_mul": 1.0,
        "skill": {
            "name": "轻灵步",
            "cooldown": 8,
            "desc": "闪现到 8 格内任意空地",
            "amount": 8,
        },
    },
    "dwarf": {
        "name": "矮人",
        "sym": "⛏",
        "desc": "坚韧 · 重甲专精",
        "hp": 15, "atk": 0, "def": 3,
        "exp_mul": 1.0,
        "skill": {
            "name": "盾墙",
            "cooldown": 12,
            "desc": "本层减伤 +{amount}",
            "amount": 6,
        },
    },
    "orc": {
        "name": "兽人",
        "sym": "♆",
        "desc": "狂暴 · 攻击强化",
        "hp": 5, "atk": 3, "def": -1,
        "exp_mul": 1.0,
        "skill": {
            "name": "狂暴",
            "cooldown": 10,
            "desc": "本层攻击 +{amount}，但防御 -3",
            "amount": 6,
        },
    },
    "goblin": {
        "name": "地精",
        "sym": "⚚",
        "desc": "狡诈 · 得分迅速",
        "hp": -2, "atk": 1, "def": 1,
        "exp_mul": 0.85,
        "skill": {
            "name": "偷窃",
            "cooldown": 6,
            "desc": "偷取最近怪物 {amount} 分",
            "amount": 25,
        },
    },
    "dragonborn": {
        "name": "龙裔",
        "sym": "▲",
        "desc": "龙血 · 范围吐息",
        "hp": 5, "atk": 1, "def": 1,
        "exp_mul": 0.95,
        "skill": {
            "name": "龙息",
            "cooldown": 12,
            "desc": "对半径 4 内所有怪物造成 {amount} 伤害",
            "amount": 20,
        },
    },
}


def load_player_race():
    """读取玩家在局外选择的种族；没选返回 human"""
    if not RACE_FILE.exists():
        return "human"
    try:
        d = json.loads(RACE_FILE.read_text(encoding="utf-8"))
        key = d.get("race", "human")
        return key if key in RACES else "human"
    except Exception:
        return "human"


def save_player_race(key):
    if key not in RACES:
        return
    RACE_FILE.parent.mkdir(exist_ok=True)
    RACE_FILE.write_text(json.dumps({"race": key}, ensure_ascii=False), encoding="utf-8")


def get(key):
    return RACES.get(key, RACES["human"])
