"""Что ИИ знает о карте заранее - то же, что видит игрок на экране: где стены и кусты.

Для пар клеток (строками, по требованию):
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
    """Строки матриц dist и see считаются по требованию и запоминаются: окно не ждёт
    полного пересчёта карты, а обучение всё равно быстро набирает нужные строки."""

    def __init__(self, arena):
        self.arena = arena.copy()
        self.W, self.H = arena.W, arena.H
        n = self.W * self.H
        self.n = n
        self.passable = np.array([not arena.solid(k % self.W, k // self.W) for k in range(n)])
        self._dist = {}
        self._see = {}
        self.neigh = []
        for k in range(n):
            if not self.passable[k]:
                self.neigh.append(())
                continue
            c, r = k % self.W, k // self.W
            self.neigh.append(tuple(nr * self.W + nc for nc, nr, _ in mapgen.neighbours(arena, c, r)))

    def dist_row(self, k):
        """Длины путей от клетки k до всех клеток (путь симметричен: и до k от всех)."""
        row = self._dist.get(k)
        if row is None:
            if self.passable[k]:
                row = np.array(mapgen.distances(self.arena, (k % self.W, k // self.W)), dtype=np.int64)
            else:
                row = np.full(self.n, INF, dtype=np.int64)
            self._dist[k] = row
        return row

    def see_row(self, k):
        """Какие клетки видны из середины клетки k (видимость симметрична)."""
        row = self._see.get(k)
        if row is None:
            ax, ay = k % self.W + 0.5, k // self.W + 0.5
            a = self.arena
            row = np.array([self.passable[j] and vision.line_clear(a, ax, ay, j % self.W + 0.5, j // self.W + 0.5)
                            for j in range(self.n)])
            row[k] = True
            self._see[k] = row
        return row

    def dist(self, a, b):
        row = self._dist.get(a)
        return int(row[b]) if row is not None else int(self.dist_row(b)[a])

    def sees(self, a, b):
        row = self._see.get(a)
        return bool(row[b]) if row is not None else bool(self.see_row(b)[a])

    def cell(self, x, y):
        c = min(max(int(x), 0), self.W - 1)
        r = min(max(int(y), 0), self.H - 1)
        return r * self.W + c

    def centre(self, k):
        return k % self.W + 0.5, k // self.W + 0.5

    def next_step(self, here, goal):
        """Соседняя клетка на кратчайшем пути от here к goal (или here, если пути нет)."""
        row = self.dist_row(goal)
        best, bd = here, row[here]
        for nb in self.neigh[here]:
            d = row[nb]
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
        d = self.dist_row(here)
        hidden = (~self.see_row(threat)) & self.passable & (d <= limit * 2)
        if not hidden.any():
            return None
        idx = np.flatnonzero(hidden)
        return int(idx[np.argmin(d[idx])])


def key(arena):
    return bytes(arena.tiles) + bytes([arena.W, arena.H])


def map_info(arena):
    """MapInfo по карте с кешем. Ключ - клетки карты, так что после разрушенного кирпича
    пути считаются заново (разрушение видно всем на экране)."""
    k = key(arena)
    info = _CACHE.get(k)
    if info is None:
        if len(_CACHE) > 32:
            _CACHE.clear()
        info = _CACHE[k] = MapInfo(arena)
    return info
