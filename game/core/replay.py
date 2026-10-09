"""Запись боя: карта, настройки и действия каждого шага. Повтор по записи даёт тот же бой
до бита: шаг мира зависит только от действий (world.py)."""
import json
from dataclasses import dataclass, field

from game.core.arena import Arena
from game.core.world import Action, Options, World


@dataclass
class Replay:
    map_rows: list
    map_name: str = ""
    per_team: int = 1
    options: dict = field(default_factory=dict)
    seed: int = 0
    ticks: list = field(default_factory=list)     # [[(id, move, turn, turret, fire), ...], ...]
    result: object = None
    final_hash: str = ""

    def to_json(self):
        return json.dumps(self.__dict__, ensure_ascii=False)

    @classmethod
    def from_json(cls, text):
        d = json.loads(text)
        d["ticks"] = [[tuple(a) for a in tick] for tick in d["ticks"]]
        return cls(**d)

    def world(self):
        arena = Arena.from_rows(self.map_rows, self.map_name)
        return World.new(arena, self.per_team, Options(**self.options))


class Recorder:
    """Ведёт бой и пишет его: rec.step(actions) вместо world.step(actions)."""

    def __init__(self, world, seed=0):
        self.world = world
        self.replay = Replay(world.arena.rows(), world.arena.name, len(world.tanks) // 2,
                             world.options.as_dict(), seed)

    def step(self, actions):
        tick = []
        for tid in sorted(actions):
            a = actions[tid].clamp()
            if a.as_tuple() != (0, 0, 0, 0):
                tick.append((tid, *a.as_tuple()))
        self.replay.ticks.append(tick)
        events = self.world.step(actions)
        if self.world.over:
            self.replay.result = self.world.winner
            self.replay.final_hash = self.world.state_hash()
        return events


def play_back(replay, upto=None, on_tick=None):
    """Мир после повтора записи (или первых upto шагов). on_tick(world) - после каждого шага."""
    w = replay.world()
    for k, tick in enumerate(replay.ticks):
        if upto is not None and k >= upto:
            break
        w.step({tid: Action(m, t, tu, bool(f)) for tid, m, t, tu, f in tick})
        if on_tick is not None:
            on_tick(w)
    return w
