"""Законы честности ИИ:

1. ИИ не получает данных о невидимом враге: враг (и его снаряды), переставленный в другое
   невидимое место, не меняет ни наблюдения, ни входа сети, ни решения.
2. Реакция с задержкой: враг, появившийся на шаге T, не влияет на решения раньше T + delay.
3. Политика получает только Observation - мира ей не дают.
"""
import random

import numpy as np
import pytest

from game.ai import bots
from game.ai.agents import Controller
from game.ai.features import features
from game.ai.net import NetPolicy, init_params
from game.ai.observe import Memory, Observation, observe
from game.core import vision
from game.core.arena import MAP_NAMES, Arena, builtin
from game.core.world import TANK_R, Action, World


def random_net(seed=0):
    return NetPolicy(init_params(np.random.default_rng(seed)) * 3)


def hidden_spots(world, me, other):
    """Свободные места, где other не виден из me и не мешает никому."""
    a = world.arena
    out = []
    for r in range(a.H):
        for c in range(a.W):
            x, y = c + 0.5, r + 0.5
            if a.solid(c, r) or vision.tank_visible(a, me.x, me.y, x, y, TANK_R):
                continue
            if any(t is not other and (t.x - x) ** 2 + (t.y - y) ** 2 < 1.0 for t in world.tanks):
                continue
            if any(a.solid(cc, rr) for cc in (c - 1, c, c + 1) for rr in (r - 1, r, r + 1)):
                continue
            out.append((x, y))
    return out


def decisions(obs):
    acts = []
    for pol in (bots.Rusher(), bots.Camper(), random_net(1)):
        pol.reset(random.Random(5))
        acts.append(pol.act(obs).as_tuple())
    return acts


def advance(world, seed, ticks):
    rng = random.Random(seed)
    for _ in range(ticks):
        world.step({t.id: Action(rng.choice((-1, 0, 1, 1)), rng.choice((-1, 0, 1)), rng.randint(-8, 8),
                                 rng.random() < 0.1) for t in world.tanks})
        if world.over:
            break


@pytest.mark.parametrize("name", MAP_NAMES)
@pytest.mark.parametrize("seed", range(4))
def test_moving_hidden_enemy_changes_nothing(name, seed):
    w = World.new(builtin(name), 2)
    advance(w, seed, 60 + 25 * seed)
    if w.over:
        pytest.skip("бой кончился")
    rng = random.Random(seed)
    checked = 0
    for me in w.tanks:
        if not me.alive:
            continue
        for other in w.tanks:
            if other.team == me.team or not other.alive:
                continue
            if vision.tank_visible(w.arena, me.x, me.y, other.x, other.y, TANK_R):
                continue
            mem = Memory()
            observe(w, me.id, mem)                       # память после этого шага
            snap = dict(mem.seen)
            obs1 = observe(w, me.id, Memory(dict(snap)))
            f1 = features(obs1)
            d1 = decisions(obs1)
            spots = hidden_spots(w, me, other)
            x0, y0, h0, t0 = other.x, other.y, other.hull, other.turret
            for x, y in rng.sample(spots, min(4, len(spots))):
                other.x, other.y = x, y
                other.hull = rng.randrange(720)
                other.turret = rng.randrange(720)
                obs2 = observe(w, me.id, Memory(dict(snap)))
                assert obs2 == obs1
                assert np.array_equal(features(obs2), f1)
                assert decisions(obs2) == d1
                checked += 1
            other.x, other.y, other.hull, other.turret = x0, y0, h0, t0
    assert checked > 0


def test_hidden_shell_changes_nothing():
    rows = ["############",
            "#A...#.....#",
            "#....#...B.#",
            "#....#.....#",
            "############"]
    w = World.new(Arena.from_rows(rows), 1)
    w.tanks[1].turret = 360                          # смотрит влево, в стену
    w.step({1: Action(fire=True)})
    assert w.shells
    obs1 = observe(w, 0, Memory())
    w.shells[0].y += 1.0
    w.shells[0].vx = -w.shells[0].vx
    obs2 = observe(w, 0, Memory())
    assert obs1 == obs2 and obs1.shells == ()
    assert decisions(obs1) == decisions(obs2)


def test_visible_enemy_is_seen_and_remembered():
    rows = ["############",
            "#A.........#",
            "#..........#",
            "#.......B..#",
            "############"]
    w = World.new(Arena.from_rows(rows), 1)
    mem = Memory()
    obs = observe(w, 0, mem)
    assert [e.id for e in obs.enemies] == [1] and obs.beliefs[0].visible
    rows2 = [r.replace(".......B..", "....#..B..") for r in rows]
    w2 = World.new(Arena.from_rows(rows2), 1)
    w2.tanks[1].x, w2.tanks[1].y = 9.5, 1.5
    w2.arena.tiles[1 * w2.arena.W + 6] = 1           # стена между
    obs2 = observe(w2, 0, mem)
    assert obs2.enemies == () and obs2.beliefs[0].x == w.tanks[1].x and not obs2.beliefs[0].visible
    w2.tanks[1].lives = 0
    obs3 = observe(w2, 0, mem)
    assert obs3.beliefs == () and obs3.enemy_count == 0


class Spy:
    kind = "spy"

    def __init__(self):
        self.seen = []

    def reset(self, rng=None):
        pass

    def act(self, obs, thoughts=None):
        self.seen.append(obs)
        return Action(1, 1, 3, False)


def test_policy_gets_only_observations():
    w = World.new(builtin("arena"), 1)
    spy = Spy()
    c = Controller(spy, 0, delay=4)
    for _ in range(40):
        w.step({0: c.act(w)})
    assert spy.seen and all(type(o) is Observation for o in spy.seen)
    for o in spy.seen:
        for v in vars(o).values():
            assert not isinstance(v, World)


@pytest.mark.parametrize("delay", (3, 6, 9))
def test_reaction_delay(delay):
    """Враг выезжает из-за стены на шаге T: до T + delay решения те же, что без него."""
    rows = ["################",
            "#..............#",
            "#..A.....#.....#",
            "#........#..B..#",
            "#..............#",
            "################"]
    T = 20

    def run(appear):
        w = World.new(Arena.from_rows(rows), 1)
        w.tanks[0].hull = 0
        c = Controller(bots.Rusher(), 0, delay=delay, period=1, rng=random.Random(1))
        acts = []
        for k in range(T + delay + 6):
            if appear and k == T:
                w.tanks[1].x, w.tanks[1].y = 13.5, 1.5        # вышел на открытое место
            acts.append(c.act(w).as_tuple())
            w.step({0: Action()})
            if k < T:
                w.tanks[1].x, w.tanks[1].y = 12.5, 3.5         # стоит за стеной
        return acts

    hidden, shown = run(False), run(True)
    assert hidden[:T + delay] == shown[:T + delay]
    assert hidden[T + delay:] != shown[T + delay:]
