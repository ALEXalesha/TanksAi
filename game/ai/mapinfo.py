"""Что ИИ знает о карте заранее - то же, что видит игрок на экране: где стены и кусты.

Для каждой пары клеток считается один раз на карту:
- dist[a, b] - длина пути танка (прямо 2, по диагонали 3; кирпич - преграда);
- see[a, b] - видна ли середина клетки b из середины клетки a (стены, кирпичи, кусты).

Из этого берутся направление пути к цели и ближайшее укрытие - клетка, которой не видно
из того места, где ИИ думает, что стоит враг. О танках здесь ничего нет.
"""
import numpy as np

from game.core import mapgen, vision

INF = 1 << 30
_CACHE = {}


class MapInfo:
    def __init__(self, arena):
        self.W, self.H = arena.W, arena.H
        n = self.W * self.H
        self.n = n
        self.passable = np.array([not arena.solid(k % self.W, k // self.W) for k in range(n)])
        dist = np.full((n, n), INF, dtype=np.int32)
        for k in range(n):
            if self.passable[k]:
                dist[k] = mapgen.distances(arena, (k % self.W, k // self.W))
        self.dist = dist
        see = np.zeros((n, n), dtype=bool)
        cells = [k for k in range(n) if self.passable[k]]
        for i, a in enumerate(cells):
            ax, ay = a % self.W + 0.5, a // self.W + 0.5
            see[a, a] = True
            for b in cells[i + 1:]:
                v = vision.line_clear(arena, ax, ay, b % self.W + 0.5, b // self.W + 0.5)
                see[a, b] = see[b, a] = v
        self.see = see
        self.neigh = []
        for k in range(n):
            if not self.passable[k]:
                self.neigh.append(())
                continue
            c, r = k % self.W, k // self.W
            self.neigh.append(tuple(nr * self.W + nc for nc, nr, _ in mapgen.neighbours(arena, c, r)))

    def cell(self, x, y):
        c = min(max(int(x), 0), self.W - 1)
        r = min(max(int(y), 0), self.H - 1)
        return r * self.W + c

    def centre(self, k):
        return k % self.W + 0.5, k // self.W + 0.5

    def next_step(self, here, goal):
        """Соседняя клетка на кратчайшем пути от here к goal (или here, если пути нет)."""
        best, bd = here, self.dist[here, goal]
        for nb in self.neigh[here]:
            d = self.dist[nb, goal]
            if d < bd:
                best, bd = nb, d
        return best

    def nearest_passable(self, k):
        if self.passable[k]:
            return k
        c, r = k % self.W, k // self.W
        best, bd = k, INF
        for j in np.flatnonzero(self.passable):
            d = abs(j % self.W - c) + abs(j // self.W - r)
            if d < bd:
                best, bd = int(j), d
        return best

    def cover_from(self, here, threat, limit=12):
        """Ближайшая по пути клетка, которой не видно из клетки threat. None - если нет
        в пределах limit клеток пути."""
        d = self.dist[here]
        hidden = (~self.see[threat]) & self.passable & (d <= limit * 2)
        if not hidden.any():
            return None
        idx = np.flatnonzero(hidden)
        return int(idx[np.argmin(d[idx])])


def key(arena):
    return bytes(arena.tiles) + bytes([arena.W, arena.H])


def map_info(arena):
    """MapInfo по карте с кешем. Кирпичи считаются по исходной карте: разрушенный кирпич
    путь не открывает (ИИ так проще и не хитрее игрока)."""
    k = key(arena)
    info = _CACHE.get(k)
    if info is None:
        if len(_CACHE) > 32:
            _CACHE.clear()
        info = _CACHE[k] = MapInfo(arena)
    return info
