"""Бой в окне без Qt: мир, ИИ, люди, запись. Окно только рисует и передаёт клавиши.

Режимы:
- duel - 1 на 1 против ИИ;
- team - 2 на 2: ты и ИИ-напарник против двух ИИ;
- hotseat - вдвоём за одним ПК;
- watch - «ИИ против ИИ».

Человек видит то же, что и ИИ: противника - только в прямой видимости своей команды
(туман войны, выключается в настройках). В «вдвоём» и «ИИ против ИИ» видно всё.
"""
import random

from game.ai.agents import Controller, delay_of, make_policy
from game.ai.match import MAP_POOL, arena_by_name
from game.core import geom, mapgen, vision
from game.core.replay import Recorder
from game.core.world import HULL_TURN, TANK_R, TURRET_TURN, Action, Options, World

MODES = ("duel", "team", "hotseat", "watch")
MAP_CHOICES = ("random", "arena", "maze", "bushes", "forts", "generated")


def pick_arena(choice, rng):
    if choice == "random":
        return arena_by_name(rng.choice(MAP_POOL))
    if choice == "generated":
        return mapgen.generate(rng.randrange(10 ** 6), "generated")
    return arena_by_name(choice)


class Session:
    def __init__(self, mode="duel", level="medium", map_choice="random", bounce=True, bricks=True,
                 fog=True, seed=None, enemy_level=None):
        if mode not in MODES:
            raise ValueError(mode)
        self.seed = random.randrange(10 ** 9) if seed is None else seed
        rng = random.Random(self.seed)
        self.mode = mode
        self.level = level
        arena = pick_arena(map_choice, rng)
        per_team = 2 if mode == "team" else 1
        self.world = World.new(arena, per_team, Options(bounce=bounce, bricks=bricks))
        self.recorder = Recorder(self.world, self.seed)
        self.fog = fog and mode in ("duel", "team")
        self.humans = {}                      # id танка -> номер игрока (0 или 1)
        self.controllers = {}
        if mode in ("duel", "team"):
            self.humans[0] = 0
        elif mode == "hotseat":
            self.humans[0] = 0
            self.humans[1] = 1
        enemy_level = enemy_level or level
        for t in self.world.tanks:
            if t.id in self.humans:
                continue
            lv = level if t.team == 0 else enemy_level
            if mode == "watch" and t.team == 0:
                lv = level
            self.controllers[t.id] = Controller(make_policy(lv), t.id, delay_of(lv),
                                                rng=random.Random(f"{self.seed}:{t.id}"))
        self.human_team = 0 if self.humans else None
        self.peeked = False                   # смотрел «Мысли ИИ» в бою с ИИ - бой вне статистики

    @property
    def over(self):
        return self.world.over

    def human_tank(self, player=0):
        for tid, p in self.humans.items():
            if p == player:
                return self.world.tanks[tid]
        return None

    def step(self, human_actions):
        """human_actions: {номер игрока: Action}. Один шаг мира. Возвращает события."""
        if self.world.over:
            return []
        acts = {}
        for tid, c in self.controllers.items():
            if self.world.tanks[tid].alive:
                acts[tid] = c.act(self.world)
        for tid, p in self.humans.items():
            if self.world.tanks[tid].alive:
                acts[tid] = human_actions.get(p, Action())
        return self.recorder.step(acts)

    def want_thoughts(self, on):
        for c in self.controllers.values():
            c.want_thoughts = on
            if not on:
                c.thoughts = None
        if on and self.mode in ("duel", "team"):
            self.peeked = True

    def visible(self, tank):
        """Видит ли человек этот танк (туман войны)."""
        if not self.fog or tank.team == self.human_team:
            return True
        for t in self.world.tanks:
            if t.team == self.human_team and t.alive and vision.tank_visible(
                    self.world.arena, t.x, t.y, tank.x, tank.y, TANK_R):
                return True
        return False

    def shell_visible(self, shell):
        if not self.fog or shell.team == self.human_team:
            return True
        return any(t.team == self.human_team and t.alive and
                   vision.point_visible(self.world.arena, t.x, t.y, shell.x, shell.y)
                   for t in self.world.tanks)

    def result(self):
        """Итог для человека: 'win', 'loss', 'draw' или None (бой идёт, или людей нет)."""
        w = self.world.winner
        if w is None or self.human_team is None or self.mode == "hotseat":
            return None
        if w == -1:
            return "draw"
        return "win" if w == self.human_team else "loss"

    def stats_key(self):
        return f"{self.mode}/{self.level}"


def aim_action(tank, want, move=0, turn=0):
    """Поворот башни за шаг, чтобы ствол смотрел на угол want (мышь)."""
    d = geom.diff(want, tank.aim) - turn * HULL_TURN
    return Action(move, turn, max(-TURRET_TURN, min(TURRET_TURN, d)), False)
