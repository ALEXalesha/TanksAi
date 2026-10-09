"""Карта: клетки 1x1, стены, кирпичи, кусты, места появления команд.

Знаки в тексте карты:
    .  пол            #  стена (сталь, снаряд отскакивает)
    x  кирпич         *  куст (проезжий, за ним и в нём не видно)
    A a  команда 0    B b  команда 1 (A и B - первые танки команд, a и b - напарники)

Готовые карты и генератор симметричны поворотом на 180 градусов: клетка (c, r) у команды 0
- это клетка (W-1-c, H-1-r) у команды 1. Поэтому карта задаётся верхней половиной, нижняя
получается поворотом. Честность проверяет check_fair (mapgen.py).
"""
from game.core import geom

FLOOR, STEEL, BRICK, BUSH = 0, 1, 2, 3
CHARS = {".": FLOOR, "#": STEEL, "x": BRICK, "*": BUSH}
TILE_CHAR = {v: k for k, v in CHARS.items()}
SPAWN_CHARS = {"A": (0, 0), "a": (0, 1), "B": (1, 0), "b": (1, 1)}
ROTATED_SPAWN = {"A": "B", "a": "b", "B": "A", "b": "a"}
W, H = 24, 16


def solid_tile(t):
    """Сквозь что не проедешь и не пролетишь."""
    return t == STEEL or t == BRICK


def opaque_tile(t):
    """Сквозь что не видно."""
    return t != FLOOR


class Arena:
    """tiles - bytearray W*H по строкам; spawns[team] - список (x, y, угол корпуса)."""

    def __init__(self, width, height, tiles, spawns, name=""):
        self.W = width
        self.H = height
        self.tiles = bytearray(tiles)
        self.spawns = spawns
        self.name = name

    # --- разбор и запись ---

    @classmethod
    def from_rows(cls, rows, name=""):
        h = len(rows)
        w = len(rows[0])
        tiles = bytearray(w * h)
        found = {}
        for r, row in enumerate(rows):
            if len(row) != w:
                raise ValueError(f"строка {r}: длина {len(row)}, нужна {w}")
            for c, ch in enumerate(row):
                if ch in SPAWN_CHARS:
                    found[ch] = (c, r)
                    ch = "."
                if ch not in CHARS:
                    raise ValueError(f"неизвестный знак {ch!r} в ({c}, {r})")
                tiles[r * w + c] = CHARS[ch]
        spawns = {0: [], 1: []}
        for ch in sorted(found, key=lambda k: SPAWN_CHARS[k]):
            team, _ = SPAWN_CHARS[ch]
            c, r = found[ch]
            spawns[team].append((c + 0.5, r + 0.5, face_center(c, r, w, h)))
        if not spawns[0] or not spawns[1]:
            raise ValueError("на карте нужны места A и B")
        return cls(w, h, tiles, spawns, name)

    @classmethod
    def from_half(cls, top, name=""):
        """Верхняя половина карты; нижняя - она же, повёрнутая на 180 градусов."""
        bottom = ["".join(ROTATED_SPAWN.get(ch, ch) for ch in reversed(row)) for row in reversed(top)]
        return cls.from_rows(list(top) + bottom, name)

    def rows(self, with_spawns=True):
        out = [[TILE_CHAR[self.tiles[r * self.W + c]] for c in range(self.W)] for r in range(self.H)]
        if with_spawns:
            for team, lst in self.spawns.items():
                for k, (x, y, _) in enumerate(lst):
                    ch = [s for s, v in SPAWN_CHARS.items() if v == (team, k)][0]
                    out[int(y)][int(x)] = ch
        return ["".join(row) for row in out]

    def text(self):
        return "\n".join(self.rows())

    def copy(self):
        return Arena(self.W, self.H, self.tiles, {t: list(s) for t, s in self.spawns.items()}, self.name)

    # --- клетки ---

    def tile(self, c, r):
        if 0 <= c < self.W and 0 <= r < self.H:
            return self.tiles[r * self.W + c]
        return STEEL

    def solid(self, c, r):
        return solid_tile(self.tile(c, r))

    def opaque(self, c, r):
        return opaque_tile(self.tile(c, r))

    def center(self):
        return self.W / 2, self.H / 2


def face_center(c, r, w, h):
    """Угол корпуса на старте: к центру карты, с шагом 45 градусов."""
    a = geom.angle_of(w / 2 - (c + 0.5), h / 2 - (r + 0.5))
    step = geom.ANG // 8
    return (round(a / step) * step) % geom.ANG


# Готовые карты: верхняя половина 24x8, нижняя - поворот.
MAPS = {
    "arena": [
        "########################",
        "#......................#",
        "#.A....##.......**.....#",
        "#......##.......**..#..#",
        "#..xx.......##......#..#",
        "#..xx...*...##....xx...#",
        "#.a.....*.........xx...#",
        "#.......##.....##......#",
    ],
    "maze": [
        "########################",
        "#....#.........#.......#",
        "#.A..#..####...#..###..#",
        "#....#.....#.......#...#",
        "#.####..x..#..###..#.###",
        "#.......x.....#........#",
        "#.a...###..*..#..xxx...#",
        "#..........*...........#",
    ],
    "bushes": [
        "########################",
        "#..........***.........#",
        "#.A...**...***...##....#",
        "#.....**.........##....#",
        "#..........#...***.....#",
        "#..***.....#...***..xx.#",
        "#.a***..x......*....xx.#",
        "#.......x..............#",
    ],
    "forts": [
        "########################",
        "#......................#",
        "#.A...x....#...........#",
        "#.....x....#....*****..#",
        "#xxx.xx....#...........#",
        "#..........xxx....##...#",
        "#.a.............*.##...#",
        "#....######.....*......#",
    ],
}
MAP_NAMES = tuple(MAPS)


def builtin(name):
    return Arena.from_half(MAPS[name], name)
