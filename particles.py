"""particles.py — 短生命周期的视觉粒子"""
import random


class Particle:
    __slots__ = ("x", "y", "ch", "ttl", "color", "bold")
    def __init__(self, x, y, ch, ttl=3, color=0, bold=False):
        self.x, self.y = x, y
        self.ch = ch
        self.ttl = ttl
        self.color = color
        self.bold = bold


class Particles:
    def __init__(self):
        self.list = []

    def clear(self):
        self.list = []

    def tick(self):
        for p in self.list:
            p.ttl -= 1
        self.list = [p for p in self.list if p.ttl > 0]

    def add(self, x, y, ch, ttl=3, color=0, bold=False):
        self.list.append(Particle(x, y, ch, ttl, color, bold))

    # --------- 预设效果 ---------
    def burst(self, x, y, ch="*", n=6, color=2, radius=2):
        """在 (x,y) 周围撒 n 个粒子"""
        for _ in range(n):
            dx = random.randint(-radius, radius)
            dy = random.randint(-radius, radius)
            self.add(x + dx, y + dy, ch, ttl=random.randint(2, 4), color=color)

    def hit(self, x, y, color=2):
        """命中火花"""
        for dx, dy in ((0,-1),(0,1),(-1,0),(1,0)):
            if random.random() < 0.6:
                self.add(x + dx, y + dy, random.choice("+-*/"), ttl=2, color=color)

    def heal(self, x, y):
        for dx in (-1, 0, 1):
            self.add(x + dx, y - 1, "+", ttl=3, color=9, bold=True)

    def die(self, x, y, color=2):
        self.burst(x, y, ch="x", n=8, color=color, radius=1)
        self.add(x, y, "*", ttl=2, color=color, bold=True)

    def magic(self, x, y, color=7):
        self.burst(x, y, ch="~", n=10, color=color, radius=3)

    def levelup(self, x, y):
        for ch in ("*", "✧", "✦", "✶"):
            self.add(x + random.randint(-3, 3),
                     y + random.randint(-2, 2),
                     ch, ttl=4, color=3, bold=True)
