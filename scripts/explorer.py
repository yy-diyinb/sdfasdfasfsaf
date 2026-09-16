# 示例脚本：探索 + 拾取 + 战斗 + 低血撤退
# step(api) 每回合被调用一次
# 调用任何一个动作（move / move_to / attack / pickup）后本回合结束

LOW_HP_RATIO = 0.35


def step(api):
    # 1) 血量低于阈值 → 优先撤退
    if api.hp < api.max_hp * LOW_HP_RATIO:
        m = api.nearest_monster()
        if m:
            name, mx, my, hp, lvl = m
            if api.distance_to(mx, my) <= 1:
                api.attack(mx, my)
                return
            _flee(api, mx, my)
            return

    # 2) 相邻怪物优先击杀
    m = api.nearest_monster()
    if m:
        name, mx, my, hp, lvl = m
        if api.distance_to(mx, my) <= 1:
            api.attack(mx, my)
            return

    # 3) 去捡最近的东西
    it = api.nearest_item()
    if it:
        name, ix, iy, cls = it
        if api.distance_to(ix, iy) == 0:
            api.pickup()
            return
        api.move_to(ix, iy)
        return

    # 4) 主动接近最近的怪
    if m:
        api.move_to(m[1], m[2])
        return

    # 5) 什么也没有，随机探索
    dx, dy = random.choice([(0, -1), (0, 1), (-1, 0), (1, 0)])
    api.move(dx, dy)


def _flee(api, mx, my):
    dx = 1 if api.px > mx else (-1 if api.px < mx else 0)
    dy = 1 if api.py > my else (-1 if api.py < my else 0)
    if (dx or dy) and api.is_walkable(api.px + dx, api.py + dy):
        api.move(dx, dy)
        return
    dx, dy = random.choice([(0, -1), (0, 1), (-1, 0), (1, 0)])
    api.move(dx, dy)
