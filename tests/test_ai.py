"""ИИ: признаки, упреждение, рикошет, сеть, боты, серии боёв с зёрнами."""
import math
import random

import numpy as np

from game.ai import bots
from game.ai.features import N_FEATURES, features, fire_line, lead_point, seg_dist2
from game.ai.mapinfo import map_info
from game.ai.match import arena_by_name, battle, series, summary
from game.ai.net import NetPolicy, init_params, n_params, to_action
from game.ai.observe import Memory, observe
from game.core import vision
from game.core.arena import Arena, builtin
from game.core.world import SHELL_SPEED, TURRET_TURN, Action, World


def test_lead_point_hits_moving_target():
    for px, py, vx, vy in ((8, 0, 0, 0.08), (5, 5, -0.05, 0.02), (0, -6, 0.07, 0.0)):
        lx, ly = lead_point(px, py, vx, vy)
        t = math.hypot(lx, ly) / SHELL_SPEED
        assert abs(px + vx * t - lx) < 1e-6 and abs(py + vy * t - ly) < 1e-6
    assert lead_point(3, 4, 0, 0) == (3, 4)


def test_fire_line_bounces_off_steel_once():
    a = Arena.from_rows(["########",
                         "#A.....#",
                         "#......#",
                         "#.....B#",
                         "########"])
    segs = fire_line(a, 1.5, 1.5, 90)                # 45 градусов вниз-вправо
    assert len(segs) == 2
    x0, y0, x1, y1 = segs[0]
    assert abs(y1 - 4.0) < 1e-6 and abs(x1 - 4.0) < 1e-6   # о нижнюю стену в (4, 4)
    _, _, x2, y2 = segs[1]
    assert x2 > x1 and y2 < y1                       # после отскока - вверх-вправо


def test_ray_through_bush_for_shells():
    a = Arena.from_rows(["########", "#A.*..B#", "########"])
    assert vision.cast_ray(a, 1.5, 1.5, 1.0, 0.0, 30)[1] == 3       # взгляд упирается в куст
    d, k = vision.cast_ray(a, 1.5, 1.5, 1.0, 0.0, 30, True)         # снаряд летит дальше
    assert k == 1 and abs(d - 5.5) < 1e-9


def test_features_shape_and_bounds():
    w = World.new(builtin("bushes"), 2)
    rng = random.Random(2)
    mems = [Memory() for _ in w.tanks]
    for _ in range(300):
        w.step({t.id: Action(rng.choice((-1, 1, 1)), rng.choice((-1, 0, 1)), rng.randint(-8, 8),
                             rng.random() < 0.2) for t in w.tanks})
        for t in w.tanks:
            if t.alive:
                f = features(observe(w, t.id, mems[t.id]))
                assert f.shape == (N_FEATURES,) and np.all(np.isfinite(f))
                assert np.all(np.abs(f) <= 2.0)
        if w.over:
            break


def test_features_see_enemy_on_ray_and_aim():
    rows = ["############",
            "#A.........#",
            "#.......B..#",
            "############"]
    w = World.new(Arena.from_rows(rows), 1)
    t = w.tanks[0]
    t.x, t.y, t.hull, t.turret = 1.5, 2.5, 0, 0
    th = {}
    f = features(observe(w, 0, Memory()), th)
    assert f[3] > 0.5                                # луч 0 (вперёд) видит врага
    assert th["target"] == (8.5, 2.5) and th["target_visible"]
    assert abs(th["aim_error"]) < 1e-9


def test_mapinfo_cover_and_path():
    a = builtin("maze")
    info = map_info(a)
    here = info.cell(2.5, 2.5)
    goal = info.cell(21.5, 13.5)
    assert info.dist(here, goal) < 1 << 30
    k, steps = here, 0
    while k != goal and steps < 200:                 # по next_step доходим до цели
        k = info.next_step(k, goal)
        steps += 1
    assert k == goal
    threat = info.cell(12.5, 7.5)
    cover = info.cover_from(here, threat)
    assert cover is not None and not info.sees(threat, cover)


def test_net_shapes_actions_and_files(tmp_path):
    p = init_params(np.random.default_rng(0))
    assert p.size == n_params()
    net = NetPolicy(p)
    out = net.forward(np.zeros(N_FEATURES, np.float32))
    assert out.shape == (4,)
    assert to_action([0.5, -0.5, 1.0, 0.1]).as_tuple() == (1, -1, TURRET_TURN, 1)
    assert to_action([0.1, 0.2, -0.5, -0.1]).as_tuple() == (0, 0, -TURRET_TURN // 2, 0)
    path = str(tmp_path / "m.npz")
    net.save(path, {"x": 1})
    back = NetPolicy.load(path)
    assert np.array_equal(back.params, net.params) and back.meta == {"x": 1}


def test_rusher_destroys_idle_target():
    res = series(bots.Rusher, bots.Idle, 6, seed=3)
    s = summary(res)
    assert s["wins"] >= 5, s


def test_series_repeat_with_same_seed():
    a = [r.row() for r in series(bots.Rusher, bots.Camper, 4, seed=9)]
    b = [r.row() for r in series(bots.Rusher, bots.Camper, 4, seed=9)]
    assert a == b


def test_battle_replay_matches():
    from game.core.replay import play_back
    r = battle(bots.Rusher, bots.Rusher, seed=4, map_name="forts", record=True)
    w = play_back(r.replay)
    assert w.state_hash() == r.replay.final_hash and w.winner == r.replay.result


def test_generated_pool_maps_are_fair():
    from game.ai.match import MAP_POOL
    from game.core.mapgen import check_fair
    for name in MAP_POOL:
        assert check_fair(arena_by_name(name))[0], name
