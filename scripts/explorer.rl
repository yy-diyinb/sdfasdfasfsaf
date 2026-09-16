var last_x = -1;
var last_y = -1;
var stuck = 0;

func step() {
    auto_manage();

    if (me.x == last_x and me.y == last_y) { stuck += 1; }
    else { stuck = 0; last_x = me.x; last_y = me.y; }
    if (stuck > 8) { random_walk(); stuck = 0; return; }

    if (poisoned() and me.hp < me.max_hp * 0.7) {
        if (use_healing()) { return; }
    }
    if (me.hp < me.max_hp * 0.55) {
        if (use_healing()) { return; }
    }
    if (me.hp < me.max_hp * 0.4 and race_skill_ready()) {
        race_skill(); return;
    }
    if (me.hp < me.max_hp * 0.3) {
        var m0 = nearest_monster();
        if (m0 != null) {
            if (distance_to(m0.x, m0.y) <= 1) { attack(m0.x, m0.y); return; }
            flee_from(m0.x, m0.y); return;
        }
    }

    var m = nearest_monster();
    if (m != null and distance_to(m.x, m.y) <= 1) { attack(m.x, m.y); return; }

    var av = altar_value();
    var a  = nearest_altar();
    if (a != null and av >= 0 and av <= 5) {
        if (distance_to(a.x, a.y) == 0) { altar_sacrifice(); return; }
        if (reachable(a.x, a.y)) { move_to(a.x, a.y); return; }
    }

    var it = nearest_item();
    if (it != null) {
        if (distance_to(it.x, it.y) == 0) { pickup(); return; }
        move_to(it.x, it.y); return;
    }

    if (m != null and reachable(m.x, m.y)) { move_to(m.x, m.y); return; }

    var s = stairs();
    if (s != null) {
        if (distance_to(s.x, s.y) == 0) { move(0, 0); return; }
        move_to(s.x, s.y); return;
    }

    random_walk();
}

func flee_from(mx, my) {
    var dx = 0; var dy = 0;
    if (me.x > mx) { dx = 1; }
    if (me.x < mx) { dx = -1; }
    if (me.y > my) { dy = 1; }
    if (me.y < my) { dy = -1; }
    if ((dx != 0 or dy != 0) and is_walkable(me.x + dx, me.y + dy)) {
        move(dx, dy); return;
    }
    random_walk();
}

func random_walk() {
    var dirs = [[0, -1], [0, 1], [-1, 0], [1, 0]];
    var d = dirs[rand(4)];
    move(d[0], d[1]);
}
