"""Мозг танка: маленькая сеть на numpy, веса - один плоский вектор (так их удобно
менять эволюцией). Вход - features.py, выход - 4 числа tanh: ход, поворот корпуса,
поворот башни, выстрел."""
import json
import os

import numpy as np

from game.ai.features import N_FEATURES, features
from game.core.world import TURRET_TURN, Action

HIDDEN = (32, 32)
OUTPUTS = 4
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")


def sizes(hidden=HIDDEN):
    return (N_FEATURES, *hidden, OUTPUTS)


def n_params(hidden=HIDDEN):
    s = sizes(hidden)
    return sum(a * b + b for a, b in zip(s[:-1], s[1:]))


def init_params(rng, hidden=HIDDEN):
    """Веса с разбросом 1/sqrt(входов), сдвиги нулём; последний слой мельче - на старте
    сеть почти стоит на месте, а не крутится."""
    parts = []
    s = sizes(hidden)
    for i, (a, b) in enumerate(zip(s[:-1], s[1:])):
        scale = 1.0 / np.sqrt(a) * (0.5 if i == len(s) - 2 else 1.0)
        parts.append(rng.normal(size=a * b) * scale)
        parts.append(np.zeros(b))
    return np.concatenate(parts)


def to_action(out):
    m = 1 if out[0] > 0.33 else -1 if out[0] < -0.33 else 0
    t = 1 if out[1] > 0.33 else -1 if out[1] < -0.33 else 0
    return Action(m, t, int(round(float(out[2]) * TURRET_TURN)), bool(out[3] > 0))


class NetPolicy:
    """Политика-сеть. params - плоский вектор весов (float32 внутри)."""

    kind = "net"

    def __init__(self, params, hidden=HIDDEN, name="net"):
        self.hidden = tuple(hidden)
        self.name = name
        self.set_params(params)

    def set_params(self, params):
        params = np.asarray(params, dtype=np.float32)
        if params.size != n_params(self.hidden):
            raise ValueError(f"весов {params.size}, нужно {n_params(self.hidden)}")
        self.params = params
        self.layers = []
        k = 0
        s = sizes(self.hidden)
        for a, b in zip(s[:-1], s[1:]):
            W = params[k:k + a * b].reshape(a, b)
            k += a * b
            bias = params[k:k + b]
            k += b
            self.layers.append((W, bias))

    def reset(self, rng=None):
        pass

    def forward(self, x):
        h = x
        for W, b in self.layers:
            h = np.tanh(h @ W + b)
        return h

    def act(self, obs, thoughts=None):
        x = features(obs, thoughts)
        out = self.forward(x)
        if thoughts is not None:
            thoughts["outputs"] = [float(v) for v in out]
        return to_action(out)

    # --- файлы ---

    def save(self, path, meta=None):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            np.savez(f, params=self.params, hidden=np.array(self.hidden),
                     meta=np.array(json.dumps(meta or {}, ensure_ascii=False)))
        os.replace(tmp, path)

    @classmethod
    def load(cls, path, name=None):
        with np.load(path) as d:
            p = cls(d["params"], tuple(int(x) for x in d["hidden"]), name or os.path.basename(path))
            p.meta = json.loads(str(d["meta"]))
        return p
