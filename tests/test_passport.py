"""Паспорт модели: все проверки на месте, числа сходятся, и малая выборка пересчитывается
с теми же зёрнами - бой в бой."""
import json
import os

import pytest

from game.ai.agents import LEVEL_NAMES, load_model
from game.ai.net import n_params
from game.train.passport import CHECKS, PASSPORT, replay_rows

REPLAY = 2


@pytest.fixture(scope="module")
def passport():
    if not os.path.exists(PASSPORT):
        pytest.skip("модель ещё не обучена")
    with open(PASSPORT, encoding="utf-8") as f:
        return json.load(f)


def find(pp, a, b):
    return next(c for c in pp["checks"] if c["subject"] == a and c["villain"] == b)


def test_passport_has_every_check_and_training_facts(passport):
    for a, b, seed in CHECKS:
        c = find(passport, a, b)
        assert c["games"] == passport["games_per_check"] >= 200 and c["seed"] == seed
        assert c["wins"] + c["draws"] + c["losses"] == c["games"]
        assert len(c["sample"]) >= REPLAY
    tr = passport["training"]
    assert tr["generations"] > 0 and tr["games"] > 0 and tr["seconds"] > 0
    net = passport["network"]
    assert net["parameters"] == n_params(tuple(net["hidden"]))
    for lv in LEVEL_NAMES:
        model = load_model(lv)
        assert model is not None and model.params.size == net["parameters"]
        assert passport["levels"][lv]["generation"] == model.meta["generation"]


@pytest.mark.slow
@pytest.mark.parametrize("a,b,seed", CHECKS)
def test_sample_replays_with_same_seeds(passport, a, b, seed):
    c = find(passport, a, b)
    assert replay_rows(a, b, seed, range(REPLAY)) == c["sample"][:REPLAY]
