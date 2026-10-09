"""ИИ за рулём танка: наблюдение, память, задержка реакции, решение раз в PERIOD шагов.

Controller.act(world) - каждый шаг:
1. observe() - что видно сейчас (память обновляется сразу);
2. наблюдение кладётся в очередь; решение принимается по наблюдению delay шагов назад -
   так ИИ «замечает» врага с опозданием, как человек. Своё положение, башню и перезарядку
   танк знает сразу (это его собственная машина), опаздывает только мир вокруг;
3. решение держится PERIOD шагов.

Уровни: новичок, средний, сильный - снимки обучения и задержка реакции.
"""
import os
from collections import deque
from dataclasses import replace

from game.ai import bots
from game.ai.observe import Memory, observe
from game.core.world import TICK_HZ, Action

PERIOD = 2
LEVELS = {
    # задержка реакции в шагах (30 шагов = 1 с) и модель
    "novice": {"delay": 9, "model": "tanks-novice.npz"},     # 0.30 с
    "medium": {"delay": 6, "model": "tanks-medium.npz"},     # 0.20 с
    "strong": {"delay": 3, "model": "tanks-strong.npz"},     # 0.10 с
}
LEVEL_NAMES = tuple(LEVELS)


def reaction_ms(level):
    return round(LEVELS[level]["delay"] * 1000 / TICK_HZ)


class Controller:
    def __init__(self, policy, tid, delay=3, period=PERIOD, rng=None):
        self.policy = policy
        self.tid = tid
        self.delay = delay
        self.period = period
        self.memory = Memory()
        self.queue = deque(maxlen=delay + 1)
        self.current = Action()
        self.thoughts = None            # словарь последнего решения, если want_thoughts
        self.want_thoughts = False
        self.decisions = 0
        policy.reset(rng)

    def act(self, world):
        now = observe(world, self.tid, self.memory)
        self.queue.append(now)
        if (world.tick + self.tid) % self.period == 0:
            old = self.queue[0]
            if old is not now:
                old = replace(old, tick=now.tick, me=now.me, reload=now.reload, speed=now.speed)
            th = {} if self.want_thoughts else None
            self.current = self.policy.act(old, th)
            if th is not None:
                th["seen_at"] = self.queue[0].tick
                self.thoughts = th
            self.decisions += 1
        return self.current


def model_path(level):
    from game.ai.net import MODEL_DIR
    return os.path.join(MODEL_DIR, LEVELS[level]["model"])


_MODELS = {}


def load_model(level):
    """Сеть уровня или None, если модель ещё не обучена."""
    path = model_path(level)
    if path not in _MODELS:
        from game.ai.net import NetPolicy
        _MODELS[path] = NetPolicy.load(path, level) if os.path.exists(path) else None
    return _MODELS[path]


def make_policy(name):
    """Политика по имени: 'rusher', 'camper', 'idle' или уровень сети. Уровень без
    обученной модели - бот (новичок и средний - осторожный, сильный - агрессивный)."""
    if name == "rusher":
        return bots.Rusher()
    if name == "camper":
        return bots.Camper()
    if name == "idle":
        return bots.Idle()
    if name in LEVELS:
        net = load_model(name)
        if net is not None:
            from game.ai.net import NetPolicy
            return NetPolicy(net.params, net.hidden, name)
        return bots.Rusher(name) if name == "strong" else bots.Camper(name)
    raise ValueError(f"неизвестный игрок {name!r}")


def delay_of(name):
    return LEVELS[name]["delay"] if name in LEVELS else LEVELS["medium"]["delay"]
