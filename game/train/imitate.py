"""Тёплый старт (разрешение Алексея 10.10.2026): прежде эволюции сеть учится повторять
простого бота «агрессивный», потом эволюция в лиге делает её сильнее бота.

Бот здесь - только учитель на время обучения. Он получает то же честное наблюдение, что и
сеть, а запоминается пара «вход сети из этого наблюдения - что сделал бот». В игре бота нет:
танком управляет только сеть по своему наблюдению.
"""
import random

import numpy as np

from aikit.nn.layers import Dense, Sequential, Tanh
from aikit.nn.optim import Adam
from game.ai import bots
from game.ai.agents import Controller
from game.ai.features import features
from game.ai.match import MAP_POOL, arena_by_name
from game.core.world import TURRET_TURN, Options, World

TRAIN_LIMIT = 60 * 30


class Recording:
    """Обёртка бота: отдаёт его действие и запоминает (вход сети, действие)."""

    kind = "bot"

    def __init__(self, bot, sink):
        self.bot = bot
        self.sink = sink
        self.name = bot.name

    def reset(self, rng=None):
        self.bot.reset(rng)

    def act(self, obs, thoughts=None):
        a = self.bot.act(obs)
        self.sink.append((features(obs), (a.move, a.turn, a.turret / TURRET_TURN, 1.0 if a.fire else -1.0)))
        return a


def collect_job(job):
    """Работник: бои ботов, записываются оба танка. job = (номера боёв, зерно)."""
    idx, seed = job
    xs, ys = [], []
    for i in idx:
        rng = random.Random(f"{seed}:{i}")
        sink = []
        teacher = (bots.Rusher, bots.Rusher, bots.Camper)
        world = World.new(arena_by_name(rng.choice(MAP_POOL)), 2 if i % 5 == 4 else 1,
                          Options(time_limit=TRAIN_LIMIT))
        ctrls = []
        for t in world.tanks:
            kind = rng.choice(teacher) if t.team == 1 else bots.Rusher
            ctrls.append(Controller(Recording(kind(), sink), t.id, 3, rng=random.Random(f"{seed}:{i}:{t.id}")))
        while not world.over:
            world.step({c.tid: c.act(world) for c in ctrls if world.tanks[c.tid].alive})
        for x, y in sink:
            xs.append(x)
            ys.append(y)
    return np.array(xs, np.float32), np.array(ys, np.float32)


def collect(games, seed=0, pool=None, workers=2):
    parts = [list(range(k, games, workers)) for k in range(workers)]
    jobs = [(p, seed) for p in parts if p]
    res = pool.map(collect_job, jobs) if pool is not None else [collect_job(j) for j in jobs]
    return np.concatenate([r[0] for r in res]), np.concatenate([r[1] for r in res])


def targets(y):
    """Цели для tanh: ход и поворот -1/0/1 -> -0.8/0/0.8, башня как есть (до 0.95), огонь ±0.8."""
    t = y.copy()
    t[:, 0] *= 0.8
    t[:, 1] *= 0.8
    t[:, 2] = np.clip(t[:, 2], -0.95, 0.95)
    t[:, 3] *= 0.8
    return t


def fit(x, y, hidden, epochs=30, batch=256, lr=2e-3, seed=0, log=print):
    """Обучение с учителем: MSE на выходах tanh. Возвращает плоский вектор весов в порядке
    NetPolicy (W слоя построчно, потом сдвиги)."""
    rng = np.random.default_rng(seed)
    sizes = (x.shape[1], *hidden, 4)
    items = []
    for a, b in zip(sizes[:-1], sizes[1:]):
        items += [Dense(a, b, rng), Tanh()]
    net = Sequential(items)
    opt = Adam(net.params(), lr)
    t = targets(y)
    w = np.array([1.0, 1.0, 1.0, 2.0], np.float32)          # выстрел важнее: редкий и решающий
    n = len(x)
    for ep in range(epochs):
        order = rng.permutation(n)
        total = 0.0
        for s in range(0, n, batch):
            b = order[s:s + batch]
            out = net.forward(x[b])
            err = (out - t[b]) * w
            total += float((err * (out - t[b])).sum())
            net.backward(2 * err / len(b))
            opt.step()
        if ep % 5 == 4 or ep == epochs - 1:
            log(f"подражание: эпоха {ep + 1}, ошибка {total / n:.4f}")
    flat = []
    for layer in items:
        if isinstance(layer, Dense):
            flat += [layer.W.reshape(-1), layer.b]
    return np.concatenate(flat).astype(np.float64)


def agreement(params, hidden, x, y):
    """Как часто сеть делает то же, что бот: ход, поворот, выстрел (доли)."""
    from game.ai.net import NetPolicy
    net = NetPolicy(params, hidden)
    out = net.forward(x)
    move = np.where(out[:, 0] > 0.33, 1, np.where(out[:, 0] < -0.33, -1, 0))
    turn = np.where(out[:, 1] > 0.33, 1, np.where(out[:, 1] < -0.33, -1, 0))
    fire = out[:, 3] > 0
    return {"move": round(float((move == y[:, 0]).mean()), 3), "turn": round(float((turn == y[:, 1]).mean()), 3),
            "fire": round(float((fire == (y[:, 3] > 0)).mean()), 3)}
