"""Вход сети из наблюдения (только Observation и карта, мира здесь нет).

Направления - в системе корпуса: «вперёд» и «вправо». Блоки входа:
- 16 лучей вокруг корпуса: дальность до стены, куст, кирпич; враг, союзник, снаряд на луче
  (если он виден и ближе стены) - 6 чисел на луч;
- свой танк: скорость, угол башни, перезарядка, жизни;
- цель (ближний видимый враг или последний, кого видел; иначе база противника): где, давно ли
  видел, ошибка прицела прямо и с упреждением, чиста ли линия, попадёт ли выстрел прямо и
  рикошетом, куда ехать по пути к цели;
- второй враг (2 на 2), союзник;
- опасность: ближний летящий в тебя снаряд;
- укрытие: ближняя клетка, которой не видно из места цели, и куда к ней ехать.
"""
import math

import numpy as np

from game.ai.mapinfo import map_info
from game.core import geom, vision
from game.core.arena import BRICK, BUSH, STEEL
from game.core.world import FWD, LIVES, RELOAD, SHELL_SPEED, TANK_R

N_RAYS = 16
RANGE = 16.0
RAY_DIRS = tuple(geom.ANG * k // N_RAYS for k in range(N_RAYS))
PER_RAY = 6
N_FEATURES = N_RAYS * PER_RAY + 6 + 15 + 6 + 5 + 5 + 3
AGE_SCALE = 90.0        # шагов: через 3 секунды память «старая»
SHELL_HIT_R = 0.3


def to_hull(dx, dy, hull):
    c, s = geom.COS[hull], geom.SIN[hull]
    return dx * c + dy * s, -dx * s + dy * c


def ray_circle(ox, oy, ux, uy, cx, cy, r):
    """Расстояние вдоль луча до круга или None."""
    px, py = cx - ox, cy - oy
    t = px * ux + py * uy
    if t < 0:
        return None
    d2 = px * px + py * py - t * t
    if d2 > r * r:
        return None
    return max(0.0, t - math.sqrt(r * r - d2))


def lead_point(px, py, vx, vy):
    """Куда стрелять, чтобы попасть в цель, которая в (px, py) от ствола и едет (vx, vy)
    клеток за шаг. Решение |p + v t| = S t; нет решения - в саму цель."""
    s2 = SHELL_SPEED * SHELL_SPEED
    a = vx * vx + vy * vy - s2
    b = 2 * (px * vx + py * vy)
    c = px * px + py * py
    t = None
    if abs(a) < 1e-12:
        if b < 0:
            t = -c / b
    else:
        disc = b * b - 4 * a * c
        if disc >= 0:
            sq = math.sqrt(disc)
            cands = [x for x in ((-b - sq) / (2 * a), (-b + sq) / (2 * a)) if x > 0]
            if cands:
                t = min(cands)
    if t is None or t > 120:
        return px, py
    return px + vx * t, py + vy * t


def seg_dist2(ax, ay, bx, by, px, py):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    qx, qy = ax + dx * t - px, ay + dy * t - py
    return qx * qx + qy * qy


def fire_line(arena, x, y, aim):
    """Путь снаряда из (x, y) по стволу: до стены, отскок от стали, до следующей стены.
    Список отрезков [(x0, y0, x1, y1)]."""
    ux, uy = geom.COS[aim], geom.SIN[aim]
    d, kind = vision.cast_ray(arena, x, y, ux, uy, 30.0, True)
    hx, hy = x + ux * d, y + uy * d
    segs = [(x, y, hx, hy)]
    if kind == STEEL:
        # как в world._fly: какая соседняя клетка - сталь, по той оси и отскок
        oc, orow = int(hx - ux * 1e-6), int(hy - uy * 1e-6)
        c, r = int(hx + ux * 1e-6), int(hy + uy * 1e-6)
        flip_x = arena.solid(c, orow)
        flip_y = arena.solid(oc, r)
        if not flip_x and not flip_y:
            flip_x = flip_y = True
        if flip_x:
            ux = -ux
        if flip_y:
            uy = -uy
        d2, _ = vision.cast_ray(arena, hx + ux * 1e-6, hy + uy * 1e-6, ux, uy, 30.0, True)
        segs.append((hx, hy, hx + ux * d2, hy + uy * d2))
    return segs


def pick_targets(obs):
    """Цели по важности: видимые (ближние первыми), потом по свежести памяти."""
    me = obs.me
    bs = list(obs.beliefs)
    bs.sort(key=lambda b: (not b.visible, -b.tick if not b.visible else 0,
                           (b.x - me.x) ** 2 + (b.y - me.y) ** 2))
    return bs


def features(obs, thoughts=None):
    """Вектор входа сети (float32, N_FEATURES). thoughts - словарь, куда сложить то, что
    показывают «Мысли ИИ» (лучи, цель, прицел, укрытие)."""
    me = obs.me
    arena = obs.arena
    info = map_info(arena)
    hull = me.hull
    aim = (me.hull + me.turret) % geom.ANG
    f = np.zeros(N_FEATURES, dtype=np.float32)
    k = 0

    # --- лучи ---
    rays = []
    for rel in RAY_DIRS:
        a = (hull + rel) % geom.ANG
        ux, uy = geom.COS[a], geom.SIN[a]
        d, kind = vision.cast_ray(arena, me.x, me.y, ux, uy, RANGE)
        enemy = ally = shell = None
        for e in obs.enemies:
            t = ray_circle(me.x, me.y, ux, uy, e.x, e.y, TANK_R)
            if t is not None and t < d and (enemy is None or t < enemy):
                enemy = t
        for e in obs.allies:
            t = ray_circle(me.x, me.y, ux, uy, e.x, e.y, TANK_R)
            if t is not None and t < d and (ally is None or t < ally):
                ally = t
        for s in obs.shells:
            if s.mine:
                continue
            t = ray_circle(me.x, me.y, ux, uy, s.x, s.y, SHELL_HIT_R)
            if t is not None and t < d and (shell is None or t < shell):
                shell = t
        f[k] = d / RANGE
        f[k + 1] = kind == BUSH
        f[k + 2] = kind == BRICK
        f[k + 3] = 0.0 if enemy is None else 1.0 - enemy / RANGE
        f[k + 4] = 0.0 if ally is None else 1.0 - ally / RANGE
        f[k + 5] = 0.0 if shell is None else 1.0 - shell / RANGE
        k += PER_RAY
        rays.append((a, d, kind, enemy))

    # --- свой танк ---
    f[k] = obs.speed / FWD
    f[k + 1] = geom.SIN[me.turret]
    f[k + 2] = geom.COS[me.turret]
    f[k + 3] = obs.reload / RELOAD
    f[k + 4] = obs.reload == 0
    f[k + 5] = me.lives / LIVES
    k += 6

    # --- цель ---
    targets = pick_targets(obs)
    here = info.cell(me.x, me.y)
    if targets:
        b = targets[0]
        tx, ty, known, visible = b.x, b.y, 1.0, float(b.visible)
        age = min(1.0, (obs.tick - b.tick) / AGE_SCALE)
        vx, vy = (b.vx, b.vy) if b.visible else (0.0, 0.0)
    else:
        sx, sy = min(obs.enemy_spawns, key=lambda p: (p[0] - me.x) ** 2 + (p[1] - me.y) ** 2)
        tx, ty, known, visible, age, vx, vy = sx, sy, 0.0, 0.0, 1.0, 0.0, 0.0
    dx, dy = tx - me.x, ty - me.y
    fx, fy = to_hull(dx, dy, hull)
    dist = math.hypot(dx, dy)
    to_t = geom.angle_of(dx, dy)
    err = geom.diff(to_t, aim)
    lx, ly = lead_point(dx, dy, vx, vy)
    lead_err = geom.diff(geom.angle_of(lx, ly), aim)
    los = vision.line_clear(arena, me.x, me.y, tx, ty)
    direct = rico = 0.0
    segs = []
    if known:
        segs = fire_line(arena, me.x, me.y, aim)
        r2 = (TANK_R + 0.05) ** 2
        if seg_dist2(*segs[0], tx, ty) < r2:
            direct = 1.0
        elif len(segs) > 1 and seg_dist2(*segs[1], tx, ty) < r2:
            rico = 1.0
    goal = info.nearest_passable(info.cell(tx, ty))
    step = info.next_step(here, goal)
    sx_, sy_ = info.centre(step)
    pa = geom.diff(geom.angle_of(sx_ - me.x, sy_ - me.y), hull)
    plen = info.dist(here, goal)
    f[k:k + 15] = (known, visible, age, fx / RANGE, fy / RANGE, min(dist, 2 * RANGE) / RANGE,
                   geom.SIN[err % geom.ANG], geom.COS[err % geom.ANG], geom.SIN[lead_err % geom.ANG],
                   float(los), direct, rico, geom.SIN[pa % geom.ANG], geom.COS[pa % geom.ANG],
                   min(plen, 120) / 120.0)
    k += 15

    # --- второй враг ---
    if len(targets) > 1:
        b2 = targets[1]
        d2x, d2y = b2.x - me.x, b2.y - me.y
        g2, r2_ = to_hull(d2x, d2y, hull)
        e2 = geom.diff(geom.angle_of(d2x, d2y), aim)
        f[k:k + 6] = (1.0, float(b2.visible), min(1.0, (obs.tick - b2.tick) / AGE_SCALE),
                      g2 / RANGE, r2_ / RANGE, geom.SIN[e2 % geom.ANG])
    k += 6

    # --- опасность ---
    best = None
    for s in obs.shells:
        if s.mine:
            continue
        rx, ry = s.x - me.x, s.y - me.y
        v2 = s.vx * s.vx + s.vy * s.vy
        tstar = -(rx * s.vx + ry * s.vy) / v2 if v2 else -1
        if tstar <= 0:
            continue
        miss = math.hypot(rx + s.vx * tstar, ry + s.vy * tstar)
        if miss > 2.0:
            continue
        if best is None or tstar < best[0]:
            best = (tstar, miss, rx, ry)
    if best is not None:
        tstar, miss, rx, ry = best
        hx_, hy_ = to_hull(rx, ry, hull)
        n = math.hypot(hx_, hy_) or 1.0
        f[k:k + 5] = (1.0, min(tstar, 30) / 30, min(miss, 2.0) / 2.0, hx_ / n, hy_ / n)
    k += 5

    # --- укрытие ---
    threat = info.nearest_passable(info.cell(tx, ty))
    cover = info.cover_from(here, threat) if known else None
    in_cover = not info.sees(here, threat)
    if cover is not None:
        cs = info.next_step(here, cover)
        cx_, cy_ = info.centre(cs)
        ca = geom.diff(geom.angle_of(cx_ - me.x, cy_ - me.y), hull)
        f[k:k + 5] = (float(in_cover), 1.0, geom.SIN[ca % geom.ANG], geom.COS[ca % geom.ANG],
                      min(info.dist(here, cover), 40) / 40.0)
    else:
        f[k] = float(in_cover)
    k += 5

    # --- союзник ---
    if obs.allies:
        al = obs.allies[0]
        ax_, ay_ = to_hull(al.x - me.x, al.y - me.y, hull)
        f[k:k + 3] = (1.0, ax_ / RANGE, ay_ / RANGE)
    k += 3
    assert k == N_FEATURES

    if thoughts is not None:
        thoughts.update(rays=rays, target=(tx, ty) if known else None, target_visible=bool(visible),
                        target_age=obs.tick - targets[0].tick if targets else None,
                        lead=(me.x + lx, me.y + ly) if known else None, fire_line=segs,
                        cover=info.centre(cover) if cover is not None else None,
                        path=info.centre(step), aim_error=geom.degrees(err))
    return f
