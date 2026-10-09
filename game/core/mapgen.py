"""Генератор симметричных карт и проверка честности.

Честная карта (check_fair):
- симметрична поворотом на 180 градусов (клетки и места команд);
- все проезжие клетки связаны (нет закрытых карманов), кирпичи считаются стеной;
- базы на равном расстоянии: путь от каждой базы до центра одинаковый, путь между базами
  не короче MIN_PATH;
- укрытия поровну: стен, кирпичей и кустов на половине каждой команды одинаково;
- с базы не видно базу противника.
"""
import random
from collections import deque

from game.core import vision
from game.core.arena import BRICK, BUSH, FLOOR, H, STEEL, W, Arena, solid_tile

MIN_PATH = 14
SPAWNS = {"A": (2, 2), "a": (2, 6)}


def neighbours(arena, c, r):
    """Соседи для пути танка: 8 направлений, по диагонали - только если оба боковых свободны."""
    for dc in (-1, 0, 1):
        for dr in (-1, 0, 1):
            if dc == 0 and dr == 0:
                continue
            nc, nr = c + dc, r + dr
            if arena.solid(nc, nr):
                continue
            if dc and dr and (arena.solid(c + dc, r) or arena.solid(c, r + dr)):
                continue
            yield nc, nr, (3 if dc and dr else 2)


def distances(arena, start):
    """Длина пути (в полуклетках: прямо 2, по диагонали 3) от клетки start до всех клеток.
    Дейкстра с малыми весами - корзинами."""
    INF = 1 << 30
    dist = [INF] * (arena.W * arena.H)
    c0, r0 = start
    dist[r0 * arena.W + c0] = 0
    buckets = {0: deque([start])}
    d = 0
    left = 1
    while left:
        q = buckets.get(d)
        if not q:
            d += 1
            continue
        c, r = q.popleft()
        left -= 1
        if dist[r * arena.W + c] != d:
            continue
        for nc, nr, w in neighbours(arena, c, r):
            nd = d + w
            k = nr * arena.W + nc
            if nd < dist[k]:
                dist[k] = nd
                buckets.setdefault(nd, deque()).append((nc, nr))
                left += 1
    return dist


def spawn_cell(spawn):
    return int(spawn[0]), int(spawn[1])


def check_fair(arena):
    """(честно ли, отчёт {проверка: значение}); rep["failed"] - какие проверки не прошли."""
    rep = {}
    w, h = arena.W, arena.H
    rep["symmetric"] = all(arena.tiles[r * w + c] == arena.tiles[(h - 1 - r) * w + (w - 1 - c)]
                           for r in range(h) for c in range(w))
    sp0 = [spawn_cell(s) for s in arena.spawns[0]]
    sp1 = [spawn_cell(s) for s in arena.spawns[1]]
    rep["spawns_symmetric"] = (len(sp0) == len(sp1)
                               and all((w - 1 - c, h - 1 - r) == o for (c, r), o in zip(sp0, sp1)))
    rep["spawns_free"] = all(arena.tile(c, r) == FLOOR for c, r in sp0 + sp1)
    d0 = distances(arena, sp0[0])
    passable = [k for k in range(w * h) if not solid_tile(arena.tiles[k])]
    rep["connected"] = all(d0[k] < (1 << 30) for k in passable)
    # центр - проезжие клетки в квадрате 4x4 посередине карты
    centre = [(c, r) for c in range(w // 2 - 2, w // 2 + 2) for r in range(h // 2 - 2, h // 2 + 2)
              if not arena.solid(c, r)]
    d1 = distances(arena, sp1[0])
    inf = 1 << 30
    rep["to_centre"] = (min([d0[r * w + c] for c, r in centre] or [inf]),
                        min([d1[r * w + c] for c, r in centre] or [inf]))
    rep["between_bases"] = min(d0[r * w + c] for c, r in sp1)
    half = [[0, 0, 0], [0, 0, 0]]
    for r in range(h):
        for c in range(w):
            t = arena.tiles[r * w + c]
            if t in (STEEL, BRICK, BUSH) and 0 < c < w - 1 and 0 < r < h - 1:
                side = 0 if (c < w // 2) else 1
                half[side][(STEEL, BRICK, BUSH).index(t)] += 1
    rep["cover"] = tuple(tuple(x) for x in half)
    rep["bases_hidden"] = all(not vision.line_clear(arena, a[0] + 0.5, a[1] + 0.5, b[0] + 0.5, b[1] + 0.5)
                              for a in sp0 for b in sp1)
    passed = {
        "symmetric": rep["symmetric"],
        "spawns_symmetric": rep["spawns_symmetric"],
        "spawns_free": rep["spawns_free"],
        "connected": rep["connected"],
        "to_centre": rep["to_centre"][0] == rep["to_centre"][1] < inf,
        "between_bases": rep["between_bases"] >= 2 * MIN_PATH,
        "cover": rep["cover"][0] == rep["cover"][1],
        "bases_hidden": rep["bases_hidden"],
    }
    rep["failed"] = [k for k, v in passed.items() if not v]
    return not rep["failed"], rep


def _blob(rng):
    kind = rng.random()
    if kind < 0.40:
        tile = STEEL
    elif kind < 0.65:
        tile = BRICK
    else:
        tile = BUSH
    shapes = [[(0, 0), (1, 0)], [(0, 0), (0, 1)], [(0, 0), (1, 0), (0, 1), (1, 1)],
              [(0, 0), (1, 0), (2, 0)], [(0, 0), (0, 1), (0, 2)], [(0, 0), (1, 0), (1, 1)],
              [(0, 0), (1, 0), (2, 0), (3, 0)]]
    return tile, rng.choice(shapes)


def _try(rng, name):
    grid = [["." for _ in range(W)] for _ in range(H // 2)]
    for c in range(W):
        grid[0][c] = "#"
    for r in range(H // 2):
        grid[r][0] = grid[r][W - 1] = "#"
    keep = set()
    for c, r in SPAWNS.values():
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                keep.add((c + dc, r + dr))
    chars = {STEEL: "#", BRICK: "x", BUSH: "*"}
    for _ in range(rng.randint(12, 18)):
        tile, shape = _blob(rng)
        c0 = rng.randint(1, W - 2)
        r0 = rng.randint(1, H // 2 - 1)
        cells = [(c0 + dc, r0 + dr) for dc, dr in shape]
        if any(not (1 <= c <= W - 2 and 1 <= r <= H // 2 - 1) or (c, r) in keep for c, r in cells):
            continue
        for c, r in cells:
            grid[r][c] = chars[tile]
    for ch, (c, r) in SPAWNS.items():
        grid[r][c] = ch
    arena = Arena.from_half(["".join(row) for row in grid], name)
    # закрытые карманы - в сталь (с обеих сторон сразу: карта остаётся симметричной)
    d = distances(arena, spawn_cell(arena.spawns[0][0]))
    for k in range(W * H):
        if not solid_tile(arena.tiles[k]) and d[k] >= (1 << 30):
            arena.tiles[k] = STEEL
    return arena


def generate(seed, name=None):
    """Честная карта по зерну. Перебирает варианты, пока проверка не пройдёт."""
    rng = random.Random(seed)
    for _ in range(500):
        arena = _try(rng, name or f"gen-{seed}")
        ok, _ = check_fair(arena)
        if ok:
            return arena
    raise RuntimeError(f"зерно {seed}: честная карта не нашлась")
