"""Видимость: что видно из точки. Одна и та же для ИИ и для тумана войны на экране игрока.

- Стены, кирпичи и кусты закрывают обзор. Клетка, где стоит смотрящий, обзор не закрывает:
  из куста видно наружу.
- Танк в кусте не виден, если он дальше BUSH_SEE клетки.
- Танк виден, если из глаза видна его середина или один из боков.
"""
import math

from game.core.arena import BUSH, opaque_tile

BUSH_SEE = 1.6



def line_clear(arena, x0, y0, x1, y1):
    """Отрезок не проходит сквозь непрозрачные клетки (кроме первой и последней).
    Обход клеток по Amanatides-Woo."""
    c, r = int(x0), int(y0)
    ce, re = int(x1), int(y1)
    if (c, r) == (ce, re):
        return True
    dx, dy = x1 - x0, y1 - y0
    step_c = 1 if dx > 0 else -1
    step_r = 1 if dy > 0 else -1
    inf = float("inf")
    t_dc = abs(1.0 / dx) if dx != 0 else inf
    t_dr = abs(1.0 / dy) if dy != 0 else inf
    if dx > 0:
        t_c = (c + 1 - x0) * t_dc
    elif dx < 0:
        t_c = (x0 - c) * t_dc
    else:
        t_c = inf
    if dy > 0:
        t_r = (r + 1 - y0) * t_dr
    elif dy < 0:
        t_r = (y0 - r) * t_dr
    else:
        t_r = inf
    W, tiles = arena.W, arena.tiles
    for _ in range(abs(ce - c) + abs(re - r) + 2):
        if t_c < t_r:
            c += step_c
            t_c += t_dc
        else:
            r += step_r
            t_r += t_dr
        if (c, r) == (ce, re):
            return True
        if not (0 <= c < W and 0 <= r < arena.H) or opaque_tile(tiles[r * W + c]):
            return False
    return True


def point_visible(arena, ex, ey, px, py):
    """Точка видна из глаза: путь чист, и если точка в кусте - она близко."""
    if arena.tile(int(px), int(py)) == BUSH and (px - ex) ** 2 + (py - ey) ** 2 > BUSH_SEE ** 2:
        return False
    return line_clear(arena, ex, ey, px, py)


def tank_visible(arena, ex, ey, tx, ty, radius):
    """Виден ли танк с серединой (tx, ty): середина или один из боков поперёк взгляда."""
    if point_visible(arena, ex, ey, tx, ty):
        return True
    dx, dy = tx - ex, ty - ey
    d = math.hypot(dx, dy)
    if d == 0:
        return True
    ox, oy = -dy / d * radius * 0.8, dx / d * radius * 0.8
    for sx, sy in ((tx + ox, ty + oy), (tx - ox, ty - oy)):
        if arena.solid(int(sx), int(sy)):
            continue
        if point_visible(arena, ex, ey, sx, sy):
            return True
    return False


def cast_ray(arena, x, y, ca, sa, max_dist):
    """Луч из (x, y) с направлением (ca, sa): (дальность до входа в первую непрозрачную
    клетку, что там; 0 - ничего ближе max_dist). Клетка смотрящего не считается. Тот же
    обход клеток, что в line_clear. Чистый Python: на 16 лучах быстрее numpy."""
    c, r = int(x), int(y)
    W, H, tiles = arena.W, arena.H, arena.tiles
    inf = math.inf
    if ca > 0:
        sc, tdc = 1, 1.0 / ca
        tc = (c + 1 - x) * tdc
    elif ca < 0:
        sc, tdc = -1, -1.0 / ca
        tc = (x - c) * tdc
    else:
        sc, tdc, tc = 0, inf, inf
    if sa > 0:
        sr, tdr = 1, 1.0 / sa
        tr = (r + 1 - y) * tdr
    elif sa < 0:
        sr, tdr = -1, -1.0 / sa
        tr = (y - r) * tdr
    else:
        sr, tdr, tr = 0, inf, inf
    while True:
        if tc < tr:
            t = tc
            c += sc
            tc += tdc
        else:
            t = tr
            r += sr
            tr += tdr
        if t >= max_dist:
            return max_dist, 0
        if not (0 <= c < W and 0 <= r < H):
            return t, 1
        k = tiles[r * W + c]
        if k:
            return t, k


def cast_rays(arena, x, y, dirs, max_dist):
    """Несколько лучей: dirs - [(cos, sin)]. Список (дальность, что там)."""
    return [cast_ray(arena, x, y, ca, sa, max_dist) for ca, sa in dirs]
