"""Наблюдение ИИ: только то, что видно из его танка, и его память.

observe(world, tank_id, memory) - единственное место, где ИИ касается мира. Дальше ИИ
работает с Observation: свой танк, карта (её видит и игрок), танки противника и снаряды,
которые видны прямо сейчас (vision.tank_visible), союзники (их место известно по рации) и
память - где и когда видел каждого противника. Закон-тест: противник, переставленный в
другое невидимое место, не меняет наблюдение (tests/test_honesty.py).
"""
from dataclasses import dataclass, field

from game.core import vision
from game.core.world import SHELL_R, TANK_R


@dataclass(frozen=True)
class Seen:
    id: int
    x: float
    y: float
    hull: int
    turret: int
    lives: int


@dataclass(frozen=True)
class SeenShell:
    x: float
    y: float
    vx: float
    vy: float
    mine: bool          # снаряд своей команды


@dataclass(frozen=True)
class Belief:
    """Где ИИ думает, что противник: место последней встречи, оценка скорости, когда видел."""
    id: int
    x: float
    y: float
    vx: float
    vy: float
    tick: int
    visible: bool


@dataclass(frozen=True)
class Observation:
    tick: int
    me: Seen
    team: int
    reload: int
    speed: float
    arena: object
    enemies: tuple          # Seen - только видимые
    allies: tuple           # Seen
    shells: tuple           # SeenShell - только видимые
    beliefs: tuple          # Belief по каждому противнику, которого хоть раз видел
    enemy_spawns: tuple     # где появляются противники - видно на карте
    enemy_count: int        # сколько противников в живых - видно по счёту на экране


@dataclass
class Memory:
    """Память одного ИИ. Обновляется только из видимого."""
    seen: dict = field(default_factory=dict)        # id -> Belief

    def update(self, tick, enemies, alive_ids):
        for e in enemies:
            old = self.seen.get(e.id)
            vx = vy = 0.0
            if old is not None and old.visible and 0 < tick - old.tick <= 3:
                dt = tick - old.tick
                vx, vy = (e.x - old.x) / dt, (e.y - old.y) / dt
            self.seen[e.id] = Belief(e.id, e.x, e.y, vx, vy, tick, True)
        shown = {e.id for e in enemies}
        for k, b in list(self.seen.items()):
            if k not in alive_ids:
                del self.seen[k]                     # уничтожен - это видно всем
            elif k not in shown and b.visible:
                self.seen[k] = Belief(b.id, b.x, b.y, b.vx, b.vy, b.tick, False)


def _seen(t):
    return Seen(t.id, t.x, t.y, t.hull, t.turret, t.lives)


def observe(world, tid, memory):
    me = world.tanks[tid]
    arena = world.arena
    enemies = []
    alive_enemy_ids = set()
    for t in world.tanks:
        if t.team == me.team or not t.alive:
            continue
        alive_enemy_ids.add(t.id)
        if vision.tank_visible(arena, me.x, me.y, t.x, t.y, TANK_R):
            enemies.append(_seen(t))
    allies = tuple(_seen(t) for t in world.tanks if t.team == me.team and t.id != tid and t.alive)
    shells = []
    for s in world.shells:
        if vision.point_visible(arena, me.x, me.y, s.x, s.y):
            shells.append(SeenShell(s.x, s.y, s.vx, s.vy, s.team == me.team))
    memory.update(world.tick, enemies, alive_enemy_ids)
    spawns = tuple((x, y) for x, y, _ in arena.spawns[1 - me.team])
    return Observation(world.tick, _seen(me), me.team, me.reload, me.speed, arena, tuple(enemies), allies,
                       tuple(shells), tuple(sorted(memory.seen.values(), key=lambda b: b.id)), spawns,
                       len(alive_enemy_ids))


__all__ = ["Observation", "Memory", "Belief", "Seen", "SeenShell", "observe", "SHELL_R"]
