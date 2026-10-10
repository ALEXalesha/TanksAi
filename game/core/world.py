"""Мир боя: танки, снаряды, стены и разрушение на постоянном шаге TICK_HZ раз в секунду.

Шаг мира не знает времени на часах и случайных чисел: всё, что меняет бой, - действия
танков. Поэтому бой повторяется по записи действий до бита (replay.py), а одинаковое зерно
у ИИ даёт одинаковый бой.

Порядок шага: повороты, движение (танки по номеру), выстрелы, полёт снарядов (3 подшага:
стены, отскок, кирпичи, танки), снаряд о снаряд, срок жизни снарядов, перезарядка, конец боя.
"""
import hashlib
import struct
from dataclasses import dataclass, field

from game.core import geom
from game.core.arena import BRICK, FLOOR, STEEL

TICK_HZ = 30
FWD = 0.085            # клеток за шаг вперёд (2.55 клетки в секунду)
BACK = 0.055           # назад медленнее
HULL_TURN = 6          # единиц угла за шаг: 3 градуса, 90 градусов в секунду
TURRET_TURN = 8        # башня быстрее: 120 градусов в секунду
TANK_R = 0.36
SHELL_R = 0.07
SHELL_SPEED = 0.27     # клеток за шаг (8.1 в секунду)
SUBSTEPS = 3
SHELL_LIFE = 100       # шагов
RELOAD = 45            # шагов между выстрелами (1.5 с)
LIVES = 3
TIME_LIMIT = 90 * TICK_HZ
HIT2 = (TANK_R + SHELL_R) ** 2


@dataclass
class Action:
    """move: -1 назад, 0, 1 вперёд; turn: -1 влево (против часовой), 0, 1 вправо;
    turret: поворот башни в единицах угла за шаг, от -TURRET_TURN до TURRET_TURN; fire."""
    move: int = 0
    turn: int = 0
    turret: int = 0
    fire: bool = False

    def clamp(self):
        return Action(max(-1, min(1, int(self.move))), max(-1, min(1, int(self.turn))),
                      max(-TURRET_TURN, min(TURRET_TURN, int(self.turret))), bool(self.fire))

    def as_tuple(self):
        return (self.move, self.turn, self.turret, int(self.fire))


IDLE = Action()


@dataclass
class Options:
    bounce: bool = True          # снаряд отскакивает от стали один раз
    bricks: bool = True          # кирпичи разрушаются; иначе они как сталь
    time_limit: int = TIME_LIMIT

    def as_dict(self):
        return {"bounce": self.bounce, "bricks": self.bricks, "time_limit": self.time_limit}


@dataclass(slots=True)
class Tank:
    id: int
    team: int
    x: float
    y: float
    hull: int
    turret: int = 0              # относительно корпуса
    lives: int = LIVES
    reload: int = 0
    speed: float = 0.0           # пройдено за последний шаг вдоль корпуса (со знаком)
    shots: int = 0
    hits: int = 0

    @property
    def alive(self):
        return self.lives > 0

    @property
    def aim(self):
        """Куда смотрит ствол (абсолютный угол)."""
        return (self.hull + self.turret) % geom.ANG


@dataclass(slots=True)
class Shell:
    id: int
    owner: int
    team: int
    x: float
    y: float
    vx: float
    vy: float
    bounces: int
    bounced: bool = False
    age: int = 0
    hit: bool = False            # попал в танк противника (для счёта промахов)


@dataclass
class World:
    arena: object
    options: Options = field(default_factory=Options)
    tanks: list = field(default_factory=list)
    shells: list = field(default_factory=list)
    tick: int = 0
    winner: object = None        # None - бой идёт; 0 или 1 - команда; -1 - ничья
    events: list = field(default_factory=list)
    next_shell: int = 0
    misses: dict = field(default_factory=dict)

    @classmethod
    def new(cls, arena, per_team=1, options=None):
        arena = arena.copy()
        w = cls(arena, options or Options())
        for k in range(per_team):
            for team in (0, 1):
                x, y, a = arena.spawns[team][k]
                w.tanks.append(Tank(len(w.tanks), team, x, y, a))
        w.misses = {t.id: 0 for t in w.tanks}
        return w

    @property
    def over(self):
        return self.winner is not None

    def team_alive(self, team):
        return any(t.alive for t in self.tanks if t.team == team)

    # --- шаг ---

    def step(self, actions):
        """actions: {id танка: Action}; кого нет - стоит. Возвращает события шага."""
        if self.over:
            return []
        self.events = []
        tanks = self.tanks
        acts = []
        for t in tanks:
            a = actions.get(t.id) if t.lives > 0 else None
            if a is None:
                acts.append((0, 0, 0, False))
                continue
            acts.append((max(-1, min(1, int(a.move))), max(-1, min(1, int(a.turn))),
                         max(-TURRET_TURN, min(TURRET_TURN, int(a.turret))), bool(a.fire)))
        ang = geom.ANG
        for t, (_, turn, tur, _) in zip(tanks, acts):
            if t.lives > 0:
                if turn:
                    t.hull = (t.hull + turn * HULL_TURN) % ang
                if tur:
                    t.turret = (t.turret + tur) % ang
        for t, (move, _, _, _) in zip(tanks, acts):
            if t.lives > 0 and move:
                self._drive(t, move)
            else:
                t.speed = 0.0
        for t, (_, _, _, fire) in zip(tanks, acts):
            if fire and t.lives > 0 and t.reload == 0:
                self._fire(t)
        for s in list(self.shells):
            self._fly(s)
        self._shell_vs_shell()
        for s in list(self.shells):
            s.age += 1
            if s.age >= SHELL_LIFE:
                self._remove(s, "expire")
        for t in self.tanks:
            if t.reload > 0:
                t.reload -= 1
        self.tick += 1
        self._check_end()
        return self.events

    def _drive(self, t, move):
        t.speed = 0.0
        if move == 0:
            return
        v = FWD if move > 0 else -BACK
        dx = geom.COS[t.hull] * v
        dy = geom.SIN[t.hull] * v
        if self._free(t, t.x + dx, t.y + dy):
            t.x += dx
            t.y += dy
            t.speed = v
        elif self._free(t, t.x + dx, t.y):           # скольжение вдоль стены
            t.x += dx
            t.speed = v * abs(geom.COS[t.hull])
        elif self._free(t, t.x, t.y + dy):
            t.y += dy
            t.speed = v * abs(geom.SIN[t.hull])

    def _free(self, t, x, y):
        """Танк с серединой (x, y) не задевает стен и других танков. Танк всегда внутри
        стальной рамки карты, поэтому клетки вокруг него - в пределах карты."""
        a = self.arena
        tiles, W = a.tiles, a.W
        r = TANK_R
        r2 = r * r
        for row in range(int(y - r), int(y + r) + 1):
            base = row * W
            for col in range(int(x - r), int(x + r) + 1):
                k = tiles[base + col]
                if k == STEEL or k == BRICK:
                    nx = x if col <= x <= col + 1 else (col if x < col else col + 1)
                    ny = y if row <= y <= row + 1 else (row if y < row else row + 1)
                    if (x - nx) * (x - nx) + (y - ny) * (y - ny) < r2:
                        return False
        d2 = 4 * r2
        for o in self.tanks:
            if o is not t and o.lives > 0 and (o.x - x) * (o.x - x) + (o.y - y) * (o.y - y) < d2:
                return False
        return True

    def _fire(self, t):
        a = t.aim
        s = Shell(self.next_shell, t.id, t.team, t.x, t.y,
                  geom.COS[a] * SHELL_SPEED, geom.SIN[a] * SHELL_SPEED,
                  1 if self.options.bounce else 0)
        self.next_shell += 1
        self.shells.append(s)
        t.reload = RELOAD
        t.shots += 1
        self.events.append(("shot", t.id, s.id))

    def _fly(self, s):
        a = self.arena
        tiles, W = a.tiles, a.W
        sx, sy = s.vx / SUBSTEPS, s.vy / SUBSTEPS
        for _ in range(SUBSTEPS):
            ox, oy = s.x, s.y
            nx, ny = ox + sx, oy + sy
            c, r = int(nx), int(ny)
            tile = tiles[r * W + c]           # снаряд внутри стальной рамки карты
            if tile == BRICK and self.options.bricks:
                a.tiles[r * a.W + c] = FLOOR
                self.events.append(("brick", c, r))
                self._remove(s, "brick")
                return
            if tile == STEEL or tile == BRICK:
                if s.bounces <= 0:
                    self._remove(s, "wall")
                    return
                oc, orow = int(ox), int(oy)
                flip_x = a.solid(c, orow)
                flip_y = a.solid(oc, r)
                if not flip_x and not flip_y:
                    flip_x = flip_y = True          # точно в угол
                if flip_x:
                    s.vx, sx = -s.vx, -sx
                if flip_y:
                    s.vy, sy = -s.vy, -sy
                s.bounces -= 1
                s.bounced = True
                self.events.append(("bounce", s.id))
                continue                            # этот подшаг стоит на месте
            s.x, s.y = nx, ny
            for t in self.tanks:
                if t.lives <= 0 or (t.id == s.owner and not s.bounced):
                    continue
                if (t.x - nx) * (t.x - nx) + (t.y - ny) * (t.y - ny) < HIT2:
                    if t.team != s.team or t.id == s.owner:
                        t.lives -= 1
                        if t.team != s.team:
                            s.hit = True
                            self.tanks[s.owner].hits += 1
                        self.events.append(("hit", s.owner, t.id, s.bounced))
                        if not t.alive:
                            self.events.append(("destroyed", t.id))
                    self._remove(s, "tank")
                    return

    def _shell_vs_shell(self):
        gone = set()
        sh = self.shells
        for i in range(len(sh)):
            for j in range(i + 1, len(sh)):
                a, b = sh[i], sh[j]
                if (a.x - b.x) ** 2 + (a.y - b.y) ** 2 < (3 * SHELL_R) ** 2:
                    gone.add(a.id)
                    gone.add(b.id)
        for s in list(sh):
            if s.id in gone:
                self._remove(s, "shell")

    def _remove(self, s, why):
        self.shells.remove(s)
        if not s.hit:
            self.misses[s.owner] = self.misses.get(s.owner, 0) + 1
        self.events.append(("gone", s.id, why))

    def _check_end(self):
        alive = [self.team_alive(0), self.team_alive(1)]
        if alive[0] and not alive[1]:
            self.winner = 0
        elif alive[1] and not alive[0]:
            self.winner = 1
        elif not alive[0] and not alive[1]:
            self.winner = -1
        elif self.tick >= self.options.time_limit:
            lives = [sum(t.lives for t in self.tanks if t.team == k) for k in (0, 1)]
            self.winner = 0 if lives[0] > lives[1] else 1 if lives[1] > lives[0] else -1

    # --- отпечаток ---

    def state_hash(self):
        """Отпечаток всего состояния: два мира с одинаковым отпечатком неотличимы."""
        h = hashlib.sha1()
        h.update(bytes(self.arena.tiles))
        h.update(struct.pack("<ii", self.tick, -2 if self.winner is None else self.winner))
        for t in self.tanks:
            h.update(struct.pack("<iiddiiiidii", t.id, t.team, t.x, t.y, t.hull, t.turret, t.lives,
                                 t.reload, t.speed, t.shots, t.hits))
        for s in self.shells:
            h.update(struct.pack("<iiiddddiii", s.id, s.owner, s.team, s.x, s.y, s.vx, s.vy,
                                 s.bounces, s.age, int(s.bounced)))
        return h.hexdigest()
