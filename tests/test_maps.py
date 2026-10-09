"""Карты и честность: готовые и сгенерированные карты проходят проверку, нечестные - нет.
Видимость: стены и кусты закрывают обзор, из куста видно наружу."""
import math

import numpy as np
import pytest

from game.core import geom, mapgen, vision
from game.core.arena import BRICK, BUSH, FLOOR, MAP_NAMES, STEEL, Arena, builtin
from game.core.world import TANK_R


@pytest.mark.parametrize("name", MAP_NAMES)
def test_builtin_maps_are_fair(name):
    a = builtin(name)
    assert (a.W, a.H) == (24, 16)
    ok, rep = mapgen.check_fair(a)
    assert ok, rep
    assert len(a.spawns[0]) == len(a.spawns[1]) == 2


def test_generator_is_fair_and_repeatable():
    texts = set()
    for seed in range(25):
        a = mapgen.generate(seed)
        ok, rep = mapgen.check_fair(a)
        assert ok, (seed, rep)
        assert mapgen.generate(seed).text() == a.text()
        texts.add(a.text())
    assert len(texts) == 25


def test_rows_roundtrip_and_spawn_facing():
    a = builtin("forts")
    b = Arena.from_rows(a.rows())
    assert b.tiles == a.tiles and b.spawns == a.spawns
    x, y, hull = a.spawns[0][0]
    assert hull % (geom.ANG // 8) == 0
    cx, cy = a.center()
    assert geom.COS[hull] * (cx - x) + geom.SIN[hull] * (cy - y) > 0      # смотрит к центру


def fair_base():
    return builtin("arena")


def test_unfair_asymmetric_tile():
    a = fair_base()
    k = 3 * a.W + 10
    assert a.tiles[k] == FLOOR
    a.tiles[k] = STEEL
    ok, rep = mapgen.check_fair(a)
    assert not ok and not rep["symmetric"]


def test_unfair_cover_counts_even_if_symmetric_flag_ignored():
    a = fair_base()
    a.tiles[3 * a.W + 10] = BUSH                     # куст только у команды 0
    _, rep = mapgen.check_fair(a)
    assert rep["cover"][0] != rep["cover"][1]


def test_unfair_pocket():
    a = fair_base()
    # стальное кольцо вокруг (10,3) и такое же у противника - карта симметрична, но карман закрыт
    for c, r in ((9, 2), (10, 2), (11, 2), (9, 3), (11, 3), (9, 4), (10, 4), (11, 4)):
        a.tiles[r * a.W + c] = STEEL
        a.tiles[(a.H - 1 - r) * a.W + (a.W - 1 - c)] = STEEL
    ok, rep = mapgen.check_fair(a)
    assert rep["symmetric"] and not rep["connected"] and not ok


def test_unfair_visible_bases():
    rows = ["##########",
            "#A......b#",
            "#a......B#",
            "##########"]
    ok, rep = mapgen.check_fair(Arena.from_rows(rows))
    assert not rep["bases_hidden"] and not ok


def test_unfair_spawn_moved():
    a = fair_base()
    x, y, h = a.spawns[1][0]
    a.spawns[1][0] = (x - 1, y, h)
    ok, rep = mapgen.check_fair(a)
    assert not rep["spawns_symmetric"] and not ok


def test_unfair_bases_too_close():
    rows = ["########",
            "#A....b#",
            "#a....B#",
            "########"]
    _, rep = mapgen.check_fair(Arena.from_rows(rows))
    assert rep["between_bases"] < 2 * mapgen.MIN_PATH


def test_unequal_distance_to_centre():
    rows = ["##########",
            "#A.......#",
            "#........#",
            "#....###.#",
            "#....#.#B#",
            "##########"]
    ok, rep = mapgen.check_fair(Arena.from_rows([r for r in rows]))
    assert not ok


# --- видимость ---

VIS = [
    "##########",
    "#........#",
    "#...#....#",
    "#...*....#",
    "#........#",
    "##########",
]


def test_line_clear_walls_and_bushes():
    a = Arena.from_rows([r.replace("*", "*") for r in VIS[:1]] + VIS[1:2] + ["#A..#...B#"] + VIS[3:])
    assert vision.line_clear(a, 1.5, 1.5, 8.5, 1.5)
    assert not vision.line_clear(a, 1.5, 2.5, 8.5, 2.5)          # стена (4,2)
    assert not vision.line_clear(a, 1.5, 3.5, 8.5, 3.5)          # куст (4,3)
    assert vision.line_clear(a, 4.5, 3.5, 8.5, 3.5)              # из куста видно наружу
    assert vision.line_clear(a, 8.5, 3.5, 4.5, 3.5)              # клетка цели не закрывает


def test_tank_in_bush_hidden_unless_close():
    a = Arena.from_rows(["##########", "#A.......#", "#..*....B#", "##########"])
    assert not vision.tank_visible(a, 8.5, 1.5, 3.5, 2.5, TANK_R)
    assert vision.tank_visible(a, 4.5, 1.5, 3.5, 2.5, TANK_R)
    assert vision.tank_visible(a, 8.5, 1.5, 5.5, 2.5, TANK_R)


def test_tank_seen_by_its_side_around_corner():
    a = Arena.from_rows(["########", "#A.....#", "#..#...#", "#.....B#", "########"])
    # середина (3.6, 3.2) скрыта углом стены (3,2), но бок виден
    assert not vision.point_visible(a, 1.5, 1.5, 3.6, 3.2)
    assert vision.tank_visible(a, 1.5, 1.5, 3.6, 3.2, TANK_R)
    assert not vision.tank_visible(a, 1.5, 1.5, 4.5, 2.9, TANK_R)


def test_rays_agree_with_line_of_sight():
    a = builtin("maze")
    rng = np.random.default_rng(3)
    for _ in range(40):
        while True:
            x, y = rng.uniform(1, a.W - 1), rng.uniform(1, a.H - 1)
            if a.tile(int(x), int(y)) == FLOOR:
                break
        angles = np.linspace(0, 2 * math.pi, 24, endpoint=False)
        rays = vision.cast_rays(a, x, y, [(math.cos(q), math.sin(q)) for q in angles], 30.0)
        for ang, (d, k) in zip(angles, rays):
            assert k in (STEEL, BRICK, BUSH)
            ux, uy = math.cos(ang), math.sin(ang)
            # до входа в клетку путь чист (по тому же обходу клеток, что и видимость)...
            assert vision.line_clear(a, x, y, x + ux * (d - 1e-6), y + uy * (d - 1e-6))
            # ...а сразу за входом - та клетка, что назвал луч
            assert a.tile(int(x + ux * (d + 1e-6)), int(y + uy * (d + 1e-6))) == k
