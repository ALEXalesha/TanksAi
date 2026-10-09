"""Простые боты для проверок силы и для лиги обучения. Они честные так же, как сеть:
получают только Observation.

- Rusher («агрессивный»): едет к врагу (к месту, где видел, иначе к его базе) и стреляет,
  как только враг на линии огня.
- Camper («осторожный»): стоит на своём посту и стреляет, если видит; пока перезаряжается -
  отходит в ближнее укрытие, потом возвращается.
"""
import random

from game.ai.features import lead_point, pick_targets
from game.ai.mapinfo import map_info
from game.core import geom, vision
from game.core.world import HULL_TURN, TURRET_TURN, Action

FIRE_TOL = 3            # единиц угла (1.5 градуса)


def steer(me, x, y, period):
    """Повернуть корпус к точке и ехать, когда смотрим почти на неё."""
    want = geom.angle_of(x - me.x, y - me.y)
    d = geom.diff(want, me.hull)
    turn = 0 if abs(d) <= HULL_TURN // 2 else (1 if d > 0 else -1)
    move = 1 if abs(d) < geom.ANG // 10 else 0
    return move, turn


def turret_to(me, want, turn, period):
    """Сколько повернуть башню за шаг, чтобы за period шагов ствол смотрел на want
    (поворот корпуса тащит башню за собой - он вычитается)."""
    aim = (me.hull + me.turret) % geom.ANG
    d = geom.diff(want, aim) - turn * HULL_TURN * period
    per = d / period
    return max(-TURRET_TURN, min(TURRET_TURN, int(round(per))))


class Bot:
    kind = "bot"
    period = 2

    def __init__(self, name):
        self.name = name
        self.rng = None

    def reset(self, rng=None):
        self.rng = rng or random.Random(0)

    def jitter(self):
        """Рука бота дрожит на градус-два: иначе два одинаковых бота на симметричной карте
        стреляют точно навстречу и снаряды гасят друг друга бесконечно."""
        return self.rng.randint(-3, 3)

    def aim_at_visible(self, obs):
        """(желаемый угол ствола, можно ли стрелять) по ближнему видимому врагу или None."""
        me = obs.me
        vis = [b for b in pick_targets(obs) if b.visible]
        if not vis:
            return None
        b = vis[0]
        lx, ly = lead_point(b.x - me.x, b.y - me.y, b.vx, b.vy)
        want = (geom.angle_of(lx, ly) + self.jitter()) % geom.ANG
        aim = (me.hull + me.turret) % geom.ANG
        clear = vision.line_clear(obs.arena, me.x, me.y, b.x, b.y)
        return want, clear and abs(geom.diff(want, aim)) <= FIRE_TOL and obs.reload == 0


class Rusher(Bot):
    def __init__(self, name="rusher"):
        super().__init__(name)
        self.checked = set()
        self.roam = None

    def reset(self, rng=None):
        super().reset(rng)
        self.checked = set()
        self.roam = None

    def act(self, obs, thoughts=None):
        me = obs.me
        info = map_info(obs.arena)
        here = info.cell(me.x, me.y)
        # цели, которые ещё стоит проверить: видимые и места встреч, где он ещё не был
        targets = [b for b in pick_targets(obs) if b.visible or (b.id, b.tick) not in self.checked]
        if targets:
            b = targets[0]
            gx, gy = b.x, b.y
            if not b.visible and (gx - me.x) ** 2 + (gy - me.y) ** 2 < 2.0:
                self.checked.add((b.id, b.tick))         # приехал - никого: искать дальше
        else:
            if self.roam is None:
                spawns = [p for p in obs.enemy_spawns if (p[0] - me.x) ** 2 + (p[1] - me.y) ** 2 > 4]
                if spawns:
                    self.roam = info.cell(*self.rng.choice(spawns))
                else:
                    cells = [int(k) for k in range(info.n) if info.passable[k]]
                    self.roam = self.rng.choice(cells)
            gx, gy = info.centre(self.roam)
            if here == self.roam:
                cells = [int(k) for k in range(info.n) if info.passable[k]]
                self.roam = self.rng.choice(cells)
        goal = info.nearest_passable(info.cell(gx, gy))
        move, turn = 0, 0
        close = targets and targets[0].visible and (gx - me.x) ** 2 + (gy - me.y) ** 2 < 9
        if here != goal and not close:
            nx, ny = info.centre(info.next_step(here, goal))
            move, turn = steer(me, nx, ny, self.period)
        shot = self.aim_at_visible(obs)
        if shot is not None:
            want, fire = shot
        else:
            want, fire = geom.angle_of(gx - me.x, gy - me.y), False
        if thoughts is not None:
            thoughts.update(target=(gx, gy) if targets else None, path=info.centre(info.next_step(here, goal)))
        return Action(move, turn, turret_to(me, want, turn, self.period), fire)


class Camper(Bot):
    def __init__(self, name="camper"):
        super().__init__(name)
        self.post = None

    def reset(self, rng=None):
        super().reset(rng)
        self.post = None

    def act(self, obs, thoughts=None):
        me = obs.me
        info = map_info(obs.arena)
        here = info.cell(me.x, me.y)
        if self.post is None:
            self.post = here
        targets = pick_targets(obs)
        shot = self.aim_at_visible(obs)
        move = turn = 0
        goal = self.post
        if targets and obs.reload > 0:
            threat = info.nearest_passable(info.cell(targets[0].x, targets[0].y))
            cover = info.cover_from(here, threat, limit=4)
            if cover is not None and info.sees(here, threat):
                goal = cover
        if here != goal:
            nx, ny = info.centre(info.next_step(here, goal))
            move, turn = steer(me, nx, ny, self.period)
        if shot is not None:
            want, fire = shot
        elif targets:
            want, fire = geom.angle_of(targets[0].x - me.x, targets[0].y - me.y), False
        else:
            cx, cy = obs.arena.center()
            want, fire = geom.angle_of(cx - me.x, cy - me.y), False
        if thoughts is not None:
            thoughts.update(target=(targets[0].x, targets[0].y) if targets else None,
                            cover=info.centre(goal) if goal != self.post else None)
        return Action(move, turn, turret_to(me, want, turn, self.period), fire)


class Idle(Bot):
    """Стоит и ничего не делает - мишень для проверок."""

    def __init__(self, name="idle"):
        super().__init__(name)

    def act(self, obs, thoughts=None):
        return Action()
