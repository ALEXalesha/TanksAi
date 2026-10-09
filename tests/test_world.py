"""Мир боя: движение, стены, выстрелы, отскок, кирпичи, попадания, конец боя, повтор."""
import random

from hypothesis import given, strategies as st

from game.core import geom
from game.core.arena import BRICK, FLOOR, Arena, builtin, MAP_NAMES
from game.core.replay import Recorder, Replay, play_back
from game.core.world import (BACK, FWD, HULL_TURN, LIVES, RELOAD, SHELL_LIFE, SHELL_SPEED, TANK_R,
                             TURRET_TURN, Action, Options, World)

OPEN = [
    "############",
    "#..........#",
    "#.A......B.#",
    "#..........#",
    "############",
]


def world(rows=OPEN, per_team=1, **opts):
    return World.new(Arena.from_rows(rows), per_team, Options(**opts))


def put(t, x, y, hull=0, turret=0):
    t.x, t.y, t.hull, t.turret = x, y, hull, turret


def run(w, actions, n):
    for _ in range(n):
        w.step(actions)


# --- углы ---

def test_angle_tables_and_diff():
    for a in range(0, geom.ANG, 7):
        assert abs(geom.COS[a] ** 2 + geom.SIN[a] ** 2 - 1) < 1e-11
    assert geom.COS[0] == 1 and geom.SIN[geom.ANG // 4] == 1      # y вниз: четверть оборота - вниз
    assert geom.diff(10, geom.ANG - 10) == 20
    assert geom.diff(geom.ANG - 10, 10) == -20
    assert geom.angle_of(0, 1) == geom.ANG // 4
    assert geom.angle_of(-1, 0) == geom.HALF


# --- движение ---

def test_forward_back_turn_and_turret():
    w = world()
    t = w.tanks[0]
    put(t, 3.5, 2.5, 0)
    w.step({0: Action(move=1)})
    assert abs(t.x - (3.5 + FWD)) < 1e-12 and t.y == 2.5 and t.speed == FWD
    w.step({0: Action(move=-1)})
    assert abs(t.x - (3.5 + FWD - BACK)) < 1e-12 and t.speed == -BACK
    w.step({0: Action(turn=1)})
    assert t.hull == HULL_TURN
    w.step({0: Action(turn=-1, turret=5)})
    assert t.hull == 0 and t.turret == 5 and t.aim == 5
    w.step({0: Action(turret=100)})                  # больше предела - обрезается
    assert t.turret == 5 + TURRET_TURN
    w.step({0: Action(turn=1)})                      # башня держится за корпус
    assert t.aim == HULL_TURN + 5 + TURRET_TURN


def touches_wall(w, t):
    a = w.arena
    for r in range(int(t.y - 1), int(t.y + 2)):
        for c in range(int(t.x - 1), int(t.x + 2)):
            if a.solid(c, r):
                nx = min(max(t.x, c), c + 1)
                ny = min(max(t.y, r), r + 1)
                if (t.x - nx) ** 2 + (t.y - ny) ** 2 < TANK_R ** 2 - 1e-12:
                    return True
    return False


def test_wall_stops_tank_and_it_slides_along():
    w = world()
    t = w.tanks[0]
    put(t, 2.0, 2.5, geom.HALF)                       # к левой стене
    run(w, {0: Action(move=1)}, 60)
    assert not touches_wall(w, t)
    assert abs(t.x - (1 + TANK_R)) < FWD + 1e-9
    assert t.speed == 0.0
    put(t, 2.0, 2.5, geom.HALF + geom.ANG // 12)      # наискосок вверх-влево: едет вдоль стены
    y0 = t.y
    run(w, {0: Action(move=1)}, 20)
    assert t.y < y0 - 0.2 and not touches_wall(w, t)


def test_tanks_do_not_overlap():
    w = world()
    a, b = w.tanks
    put(a, 3.5, 2.5, 0)
    put(b, 5.5, 2.5, geom.HALF)
    run(w, {0: Action(move=1), 1: Action(move=1)}, 60)
    assert (a.x - b.x) ** 2 + (a.y - b.y) ** 2 >= (2 * TANK_R) ** 2


# --- выстрелы ---

def test_fire_reload_and_shell_flight():
    w = world()
    t = w.tanks[0]
    put(t, 2.5, 1.5, geom.ANG // 4)                    # вниз, вдаль от противника
    put(w.tanks[1], 9.5, 3.5)
    ev = w.step({0: Action(fire=True)})
    assert ("shot", 0, 0) in ev and len(w.shells) == 1 and t.reload == RELOAD - 1
    s = w.shells[0]
    assert abs(s.vy - SHELL_SPEED) < 1e-12 and abs(s.y - (1.5 + SHELL_SPEED)) < 1e-12
    for _ in range(RELOAD - 2):
        w.step({0: Action(fire=True)})
    assert t.shots == 1
    w.step({0: Action(fire=True)})
    w.step({0: Action(fire=True)})
    assert t.shots == 2


def test_hit_takes_life_and_three_hits_destroy():
    w = world()
    a, b = w.tanks
    put(a, 2.5, 2.5, 0)
    put(b, 8.5, 2.5, geom.HALF)
    hits = 0
    for _ in range(400):
        ev = w.step({0: Action(fire=True)})
        hits += sum(1 for e in ev if e[0] == "hit")
        if w.over:
            break
    assert hits == LIVES and b.lives == 0 and not b.alive and a.hits == LIVES
    assert w.winner == 0 and w.misses[0] == 0


def test_shell_bounces_once_then_dies():
    w = world()
    a, b = w.tanks
    put(a, 5.5, 2.5, geom.ANG // 4)                    # вниз в стену
    put(b, 10.5, 1.5)
    w.step({0: Action(fire=True)})
    s = w.shells[0]
    run(w, {}, 6)
    assert s.bounced and s.vy < 0
    run(w, {}, 20)
    assert s not in w.shells and w.misses[0] == 1


def test_no_bounce_option():
    w = world(bounce=False)
    put(w.tanks[0], 5.5, 2.5, geom.ANG // 4)
    w.step({0: Action(fire=True)})
    run(w, {}, 6)
    assert not w.shells


def test_own_ricochet_hurts_owner_but_shell_from_centre_does_not():
    w = world()
    a = w.tanks[0]
    put(a, 5.5, 2.5, geom.ANG // 4)                    # стреляет вниз в стену, снаряд вернётся
    put(w.tanks[1], 10.5, 1.5)
    w.step({0: Action(fire=True)})
    assert a.lives == LIVES
    run(w, {}, 15)
    assert a.lives == LIVES - 1 and a.hits == 0


def test_brick_breaks_or_acts_as_steel():
    rows = ["#########",
            "#A..x..B#",
            "#########"]
    w = World.new(Arena.from_rows(rows), 1, Options())
    put(w.tanks[0], 1.5, 1.5, 0)
    w.step({0: Action(fire=True)})
    seen = []
    for _ in range(15):
        seen += w.step({})
    assert w.arena.tile(4, 1) == FLOOR and ("brick", 4, 1) in seen and not w.shells
    w = World.new(Arena.from_rows(rows), 1, Options(bricks=False))
    put(w.tanks[0], 1.5, 1.5, 0)
    w.step({0: Action(fire=True)})
    run(w, {}, 12)
    assert w.arena.tile(4, 1) == BRICK and w.shells and w.shells[0].bounced


def test_ally_absorbs_shell_without_damage():
    rows = ["##########",
            "#A......B#",
            "#a......b#",
            "##########"]
    w = World.new(Arena.from_rows(rows), 2, Options())
    a, b, ally, b2 = w.tanks
    assert (a.team, b.team, ally.team, b2.team) == (0, 1, 0, 1)
    put(a, 1.5, 1.5, 0)
    put(ally, 3.5, 1.5)
    w.step({0: Action(fire=True)})
    run(w, {}, 10)
    assert ally.lives == LIVES and not w.shells


def test_shells_destroy_each_other():
    w = world()
    a, b = w.tanks
    put(a, 2.5, 2.5, 0)
    put(b, 9.5, 2.5, 0, geom.HALF)
    w.step({0: Action(fire=True), 1: Action(fire=True)})
    run(w, {}, 15)
    assert a.lives == b.lives == LIVES and not w.shells


def test_shell_expires():
    rows = ["#" * 60, "#A" + "." * 57 + "#", "#" + "." * 57 + "B#", "#" * 60]
    w = World.new(Arena.from_rows(rows), 1, Options())
    put(w.tanks[0], 1.5, 1.5, 0)
    w.step({0: Action(fire=True)})
    run(w, {}, SHELL_LIFE - 2)
    assert w.shells
    run(w, {}, 1)
    assert not w.shells and w.misses[0] == 1


def test_time_limit_by_lives_or_draw():
    w = world(time_limit=10)
    run(w, {}, 10)
    assert w.over and w.winner == -1
    w = world(time_limit=10)
    w.tanks[1].lives = 2
    run(w, {}, 10)
    assert w.winner == 0


# --- свойства на случайных боях ---

def random_actions(rng, ids):
    return {i: Action(rng.choice((-1, 0, 1, 1)), rng.choice((-1, 0, 1)),
                      rng.randint(-TURRET_TURN, TURRET_TURN), rng.random() < 0.1) for i in ids}


def random_battle(seed, name="arena", per_team=1, ticks=600, recorder=False):
    w = World.new(builtin(name), per_team)
    rec = Recorder(w, seed) if recorder else None
    rng = random.Random(seed)
    hashes = []
    for _ in range(ticks):
        acts = random_actions(rng, range(len(w.tanks)))
        (rec or w).step(acts)
        hashes.append(w.state_hash())
        if w.over:
            break
    return w, rec, hashes


@given(st.integers(0, 10 ** 6), st.sampled_from(MAP_NAMES), st.sampled_from((1, 2)))
def test_invariants_on_random_battles(seed, name, per_team):
    w = World.new(builtin(name), per_team)
    rng = random.Random(seed)
    for _ in range(150):
        w.step(random_actions(rng, range(len(w.tanks))))
        for t in w.tanks:
            assert 0 <= t.lives <= LIVES and 0 <= t.reload <= RELOAD
            if t.alive:
                assert not touches_wall(w, t)
                for o in w.tanks:
                    if o is not t and o.alive:
                        assert (o.x - t.x) ** 2 + (o.y - t.y) ** 2 >= (2 * TANK_R) ** 2 - 1e-9
        for s in w.shells:
            assert 0 < s.x < w.arena.W and 0 < s.y < w.arena.H
            assert not w.arena.solid(int(s.x), int(s.y))
        if w.over:
            break


def test_same_actions_same_battle():
    _, _, h1 = random_battle(7, "forts", 2)
    _, _, h2 = random_battle(7, "forts", 2)
    _, _, h3 = random_battle(8, "forts", 2)
    assert h1 == h2 and h1 != h3


def test_replay_reproduces_every_tick():
    w, rec, hashes = random_battle(11, "bushes", 2, ticks=900, recorder=True)
    text = rec.replay.to_json()
    again = Replay.from_json(text)
    seen = []
    w2 = play_back(again, on_tick=lambda x: seen.append(x.state_hash()))
    assert seen == hashes
    assert w2.state_hash() == w.state_hash()
    if w.over:
        assert again.final_hash == w.state_hash() and again.result == w.winner
