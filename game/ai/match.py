"""Бой между ИИ без окна: для обучения, паспорта и тестов.

Бой i серии с зерном seed: карта и стороны берутся из random.Random(f"{seed}:{i}"), чётные
бои испытуемый играет за команду 0, нечётные - за команду 1. Поэтому любой бой можно
пересчитать отдельно и сверить с паспортом.
"""
import random
from dataclasses import dataclass

from game.ai.agents import Controller
from game.core import mapgen
from game.core.arena import MAP_NAMES, builtin
from game.core.replay import Recorder
from game.core.world import Options, World

GEN_SEEDS = (11, 23, 37, 41, 59, 67)
MAP_POOL = MAP_NAMES + tuple(f"gen:{s}" for s in GEN_SEEDS)
_ARENAS = {}


def arena_by_name(name):
    a = _ARENAS.get(name)
    if a is None:
        a = builtin(name) if not name.startswith("gen:") else mapgen.generate(int(name[4:]), name)
        _ARENAS[name] = a
    return a


@dataclass
class Result:
    outcome: str          # 'W', 'D', 'L' - для стороны A
    hits_a: int
    hits_b: int
    shots_a: int
    shots_b: int
    lives_a: int
    lives_b: int
    ticks: int
    map_name: str
    replay: object = None

    def row(self):
        return [self.outcome, self.hits_a, self.hits_b, self.shots_a, self.shots_b, self.ticks]


def battle(make_a, make_b, seed, per_team=1, map_name=None, delay_a=3, delay_b=3, swap=None,
           time_limit=None, options=None, record=False):
    """make_a, make_b - фабрики политик (у каждого танка своя). Возвращает Result."""
    rng = random.Random(f"{seed}")
    if map_name is None:
        map_name = rng.choice(MAP_POOL)
    if swap is None:
        swap = rng.random() < 0.5
    opts = options or Options()
    if time_limit is not None:
        opts = Options(opts.bounce, opts.bricks, time_limit)
    world = World.new(arena_by_name(map_name), per_team, opts)
    rec = Recorder(world, seed) if record else None
    team_a = 1 if swap else 0
    ctrls = []
    for t in world.tanks:
        mine = t.team == team_a
        pol = make_a() if mine else make_b()
        ctrls.append(Controller(pol, t.id, delay_a if mine else delay_b,
                                rng=random.Random(f"{seed}:{t.id}")))
    stepper = rec or world
    while not world.over:
        stepper.step({c.tid: c.act(world) for c in ctrls if world.tanks[c.tid].alive})
    side = [t for t in world.tanks if t.team == team_a]
    other = [t for t in world.tanks if t.team != team_a]
    if world.winner == -1:
        out = "D"
    else:
        out = "W" if world.winner == team_a else "L"
    return Result(out, sum(t.hits for t in side), sum(t.hits for t in other),
                  sum(t.shots for t in side), sum(t.shots for t in other),
                  sum(t.lives for t in side), sum(t.lives for t in other), world.tick, map_name,
                  rec.replay if rec else None)


def series(make_a, make_b, games, seed, per_team=1, delay_a=3, delay_b=3, indices=None, time_limit=None):
    """Серия боёв: бой i - зерно f'{seed}:{i}', сторона по чётности. Список Result."""
    idx = range(games) if indices is None else indices
    out = []
    for i in idx:
        r = random.Random(f"{seed}:{i}")
        out.append(battle(make_a, make_b, f"{seed}:{i}", per_team, r.choice(MAP_POOL), delay_a, delay_b,
                          swap=i % 2 == 1, time_limit=time_limit))
    return out


def summary(results):
    n = max(len(results), 1)
    w = sum(r.outcome == "W" for r in results)
    d = sum(r.outcome == "D" for r in results)
    shots = sum(r.shots_a for r in results)
    hits = sum(r.hits_a for r in results)
    return {"games": len(results), "wins": w, "draws": d, "losses": len(results) - w - d,
            "win_rate": round(w / n, 4), "score": round((w + d / 2) / n, 4),
            "hits_per_game": round(hits / n, 3), "taken_per_game": round(sum(r.hits_b for r in results) / n, 3),
            "misses_per_game": round((shots - hits) / n, 3), "accuracy": round(hits / shots, 4) if shots else 0.0,
            "avg_seconds": round(sum(r.ticks for r in results) / n / 30, 2)}
