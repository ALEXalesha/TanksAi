"""Нейроэволюция (эволюционная стратегия с парами ±шум, как OpenAI-ES) в лиге.

Каждое поколение:
1. Соперники поколения - одни на всех кандидатов (так шум честнее): агрессивный бот,
   осторожный бот и снимки прошлых поколений (лига), чтобы сеть не зациклилась на одной
   тактике. Один бой из четырёх - 2 на 2 с общей наградой команды.
2. Кандидаты: среднее ± sigma * шум. Каждый играет те же бои (карта, сторона, соперник).
3. Оценка боя: исход (+1, 0, -1), разница попаданий, доля времени, когда ствол смотрел на
   видимого врага, и сколько продержался при поражении. Награда может знать больше, чем
   сеть: в бою сеть всё равно видит только своё наблюдение.
4. Шаг Adam по рангам оценок; снимок состояния после каждого поколения.
"""
import math
import random
import time
from dataclasses import dataclass

import numpy as np

from game.ai import bots
from game.ai.agents import Controller
from game.ai.match import MAP_POOL, arena_by_name
from game.ai.net import HIDDEN, NetPolicy, init_params, n_params
from game.core import geom, vision
from game.core.world import TANK_R, Options, World

TRAIN_LIMIT = 60 * 30          # бой в обучении - до 60 секунд
CANDIDATE_DELAY = 3
BOT_DELAY = 6


@dataclass
class Config:
    pairs: int = 12            # кандидатов = 2 * pairs
    games: int = 4             # боёв на кандидата в поколении
    sigma: float = 0.05
    lr: float = 0.03
    decay: float = 0.005
    league_every: int = 15     # каждые N поколений среднее идёт в лигу
    league_size: int = 6
    eval_every: int = 10
    eval_games: int = 20
    hidden: tuple = HIDDEN
    miss_penalty: float = 0.0  # штраф за снаряд мимо: без него сеть учится сыпать снарядами
    league_share: float = 0.4  # доля боёв с лигой (остальное - боты поровну)


def make_opponent(spec):
    kind = spec[0]
    if kind == "rusher":
        return bots.Rusher()
    if kind == "camper":
        return bots.Camper()
    return NetPolicy(spec[1], tuple(spec[2]))


def play(params, hidden, opp, seed, per_team, map_name, swap, delay_b=BOT_DELAY, miss_penalty=0.0):
    """Один бой кандидата. Возвращает (оценка, исход 'W'/'D'/'L')."""
    world = World.new(arena_by_name(map_name), per_team, Options(time_limit=TRAIN_LIMIT))
    team_a = 1 if swap else 0
    ctrls = []
    for t in world.tanks:
        if t.team == team_a:
            ctrls.append(Controller(NetPolicy(params, hidden), t.id, CANDIDATE_DELAY,
                                    rng=random.Random(f"{seed}:{t.id}")))
        else:
            ctrls.append(Controller(make_opponent(opp), t.id, delay_b, rng=random.Random(f"{seed}:{t.id}")))
    mine = [t for t in world.tanks if t.team == team_a]
    theirs = [t for t in world.tanks if t.team != team_a]
    seen = aimed = alive_ticks = 0
    while not world.over:
        world.step({c.tid: c.act(world) for c in ctrls if world.tanks[c.tid].alive})
        if world.tick % 3:
            continue
        for t in mine:
            if not t.alive:
                continue
            alive_ticks += 1
            for e in theirs:
                if e.alive and vision.tank_visible(world.arena, t.x, t.y, e.x, e.y, TANK_R):
                    seen += 1
                    err = geom.diff(geom.angle_of(e.x - t.x, e.y - t.y), t.aim)
                    if abs(err) <= 10:
                        aimed += 1
                    break
    if world.winner == -1:
        out, base = "D", 0.0
    elif world.winner == team_a:
        out, base = "W", 1.0
    else:
        out, base = "L", -1.0
    hits_a = sum(t.hits for t in mine)
    hits_b = sum(t.hits for t in theirs)
    survive = alive_ticks / max(1, len(mine) * world.tick / 3)
    misses = sum(world.misses.get(t.id, 0) for t in mine)
    score = base + 0.25 * (hits_a - hits_b) / per_team + 0.3 * (aimed / seen if seen else 0.0)
    score -= miss_penalty * misses / per_team
    if out == "L":
        score += 0.3 * survive
    return score, out


def evaluate_candidate(job):
    """Задача работника: все бои одного кандидата. job = (params, hidden, бои)."""
    params, hidden, games, penalty = job
    total = 0.0
    outs = []
    for opp, seed, per_team, map_name, swap in games:
        s, o = play(params, hidden, opp, seed, per_team, map_name, swap, miss_penalty=penalty)
        total += s
        outs.append(o)
    return total / len(games), "".join(outs)


class Adam:
    def __init__(self, n, lr, b1=0.9, b2=0.999):
        self.m = np.zeros(n)
        self.v = np.zeros(n)
        self.t = 0
        self.lr, self.b1, self.b2 = lr, b1, b2

    def step(self, g):
        self.t += 1
        self.m = self.b1 * self.m + (1 - self.b1) * g
        self.v = self.b2 * self.v + (1 - self.b2) * g * g
        mh = self.m / (1 - self.b1 ** self.t)
        vh = self.v / (1 - self.b2 ** self.t)
        return self.lr * mh / (np.sqrt(vh) + 1e-8)


def centered_ranks(x):
    r = np.empty(len(x))
    r[np.argsort(x)] = np.arange(len(x))
    return r / (len(x) - 1) - 0.5


class Evolution:
    def __init__(self, cfg=None, seed=0):
        self.cfg = cfg or Config()
        self.rng = np.random.default_rng(seed)
        self.mean = init_params(self.rng, self.cfg.hidden)
        self.adam = Adam(self.mean.size, self.cfg.lr)
        self.gen = 0
        self.league = []            # [(поколение, веса)]
        self.history = []           # строки журнала
        self.games_played = 0
        self.seconds = 0.0
        self.best = None            # (оценка, поколение, веса)

    @property
    def n(self):
        return n_params(self.cfg.hidden)

    def opponents(self, rng):
        """Соперники и бои поколения: [(соперник, зерно, игроков в команде, карта, сторона)]."""
        out = []
        for g in range(self.cfg.games):
            roll = rng.random()
            share = self.cfg.league_share if self.league else 0.0
            if roll < share:
                gen, w = self.league[rng.randrange(len(self.league))]
                opp = ("net", w.astype(np.float32), list(self.cfg.hidden))
            elif roll < share + (1 - share) / 2:
                opp = ("rusher",)
            else:
                opp = ("camper",)
            per_team = 2 if g == self.cfg.games - 1 else 1
            out.append((opp, f"g{self.gen}:{g}", per_team, rng.choice(MAP_POOL), rng.random() < 0.5))
        return out

    def generation(self, pool=None):
        t0 = time.perf_counter()
        cfg = self.cfg
        rng = random.Random(f"gen{self.gen}")
        games = self.opponents(rng)
        eps = self.rng.normal(size=(cfg.pairs, self.n))
        cands = []
        for e in eps:
            cands.append(self.mean + cfg.sigma * e)
            cands.append(self.mean - cfg.sigma * e)
        jobs = [(c.astype(np.float32), cfg.hidden, games, cfg.miss_penalty) for c in cands]
        res = pool.map(evaluate_candidate, jobs) if pool is not None else [evaluate_candidate(j) for j in jobs]
        fit = np.array([r[0] for r in res])
        ranks = centered_ranks(fit)
        g = np.zeros(self.n)
        for i, e in enumerate(eps):
            g += (ranks[2 * i] - ranks[2 * i + 1]) * e
        g /= (2 * cfg.pairs * cfg.sigma)
        self.mean = self.mean + self.adam.step(g) - cfg.lr * cfg.decay * self.mean
        self.gen += 1
        self.games_played += len(jobs) * len(games)
        if self.gen % cfg.league_every == 0:
            self.league.append((self.gen, self.mean.copy()))
            fixed = [x for x in self.league if x[0] < 0]          # эталоны из прошлого обучения
            grown = [x for x in self.league if x[0] >= 0]
            self.league = fixed + grown[-cfg.league_size:]
        outs = "".join(r[1] for r in res)
        dt = time.perf_counter() - t0
        self.seconds += dt
        row = {"gen": self.gen, "fit_mean": round(float(fit.mean()), 3), "fit_max": round(float(fit.max()), 3),
               "wins": round(outs.count("W") / len(outs), 3), "losses": round(outs.count("L") / len(outs), 3),
               "seconds": round(dt, 1), "games": len(jobs) * len(games)}
        self.history.append(row)
        return row

    # --- снимок ---

    def state(self):
        arrays = {"mean": self.mean, "adam_m": self.adam.m, "adam_v": self.adam.v}
        for k, (g, w) in enumerate(self.league):
            arrays[f"league{k}"] = w
        if self.best is not None:
            arrays["best"] = self.best[2]
        meta = {"gen": self.gen, "adam_t": self.adam.t, "league_gens": [g for g, _ in self.league],
                "history": self.history, "games": self.games_played, "seconds": self.seconds,
                "best": None if self.best is None else [self.best[0], self.best[1]],
                "rng": self.rng.bit_generator.state, "cfg": self.cfg.__dict__}
        return arrays, meta

    def restore(self, arrays, meta):
        self.mean = arrays["mean"]
        self.adam.m, self.adam.v, self.adam.t = arrays["adam_m"], arrays["adam_v"], meta["adam_t"]
        self.league = [(g, arrays[f"league{k}"]) for k, g in enumerate(meta["league_gens"])]
        self.gen = meta["gen"]
        self.history = meta["history"]
        self.games_played = meta["games"]
        self.seconds = meta["seconds"]
        if meta.get("best"):
            self.best = (meta["best"][0], meta["best"][1], arrays["best"])
        self.rng.bit_generator.state = meta["rng"]


def warm(_):
    """Работник заранее строит карты пула (генератор) - пути и видимость считаются по ходу."""
    import os
    for m in MAP_POOL:
        arena_by_name(m)
    return os.getpid()


def eval_job(job):
    """Проверка: params против соперника на фиксированных боях. (очки, боёв)."""
    params, hidden, opp, idx = job
    from game.ai.match import battle
    pts = 0.0
    if isinstance(opp, str):
        make_b, delay_b = (lambda: make_opponent((opp,))), BOT_DELAY
    else:
        wb = opp
        make_b, delay_b = (lambda: NetPolicy(wb, hidden)), CANDIDATE_DELAY
    for i in idx:
        r = random.Random(f"eval:{i}")
        res = battle(lambda: NetPolicy(params, hidden), make_b, f"eval:{i}", 1,
                     r.choice(MAP_POOL), CANDIDATE_DELAY, delay_b, swap=i % 2 == 1)
        pts += {"W": 1.0, "D": 0.5, "L": 0.0}[res.outcome]
    return pts, len(idx)


def evaluate(params, hidden, games, pool=None, workers=2, panel=()):
    """Доля очков против агрессивного и осторожного ботов и против сетей-эталонов panel
    [(имя, веса)] - на одних и тех же боях. 'panel' - среднее по эталонам."""
    out = {}
    opps = [("rusher", "rusher"), ("camper", "camper")] + [(name, w.astype(np.float32)) for name, w in panel]
    jobs, owners = [], []
    for name, opp in opps:
        for k in range(workers):
            part = list(range(k, games, workers))
            if part:
                jobs.append((params.astype(np.float32), hidden, opp, part))
                owners.append(name)
    res = pool.map(eval_job, jobs) if pool is not None else [eval_job(j) for j in jobs]
    sums = {}
    for name, (pts, n) in zip(owners, res):
        a, b = sums.get(name, (0.0, 0))
        sums[name] = (a + pts, b + n)
    for name, (pts, n) in sums.items():
        out[name] = round(pts / n, 3)
    if panel:
        out["panel"] = round(sum(out[name] for name, _ in panel) / len(panel), 3)
    return out


def forecast(sec_per_gen, gens, eval_sec, evals):
    total = sec_per_gen * gens + eval_sec * evals
    return {"sec_per_gen": round(sec_per_gen, 1), "generations": gens, "evals": evals,
            "hours": round(total / 3600, 2), "ready_at": time.strftime("%H:%M", time.localtime(time.time() + total))}


__all__ = ["Config", "Evolution", "evaluate", "forecast", "math"]
