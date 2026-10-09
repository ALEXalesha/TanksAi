"""Уровни из снимков обучения -> game/models.

Сильный - снимок с лучшей проверкой против ботов. Средний и новичок - ранние снимки лиги:
первый, чья проверка набрала не меньше MEDIUM и NOVICE от лучшей. Так у уровней разный
опыт, а не только задержка реакции.
"""
import glob
import os

from aikit.trainlog import load_snapshot
from game.ai.agents import model_path
from game.ai.net import NetPolicy

MEDIUM = 0.75
NOVICE = 0.45


def snapshots(run):
    out = []
    for path in sorted(glob.glob(os.path.join(run, "gen*.npz"))):
        snap = load_snapshot(path)
        if snap is None:
            continue
        arrays, meta = snap
        ev = meta["eval"]
        out.append((meta["gen"], ev["rusher"] + ev["camper"], ev, arrays["mean"]))
    return out


def choose(snaps):
    """{уровень: (поколение, проверка, веса)} по правилам выше."""
    best = max(snaps, key=lambda s: (s[1], s[0]))
    levels = {"strong": best}
    for level, share in (("medium", MEDIUM), ("novice", NOVICE)):
        early = [s for s in snaps if s[1] >= share * best[1] and s[0] <= best[0]]
        levels[level] = min(early, key=lambda s: s[0]) if early else snaps[0]
    return {k: (v[0], v[2], v[3]) for k, v in levels.items()}


def publish(run):
    snaps = snapshots(run)
    if not snaps:
        print(f"в {run} нет снимков gen*.npz")
        return 1
    final = load_snapshot(os.path.join(run, "snapshot.npz"))
    cfg = final[1]["cfg"] if final else {}
    hidden = tuple(cfg.get("hidden", (32, 32)))
    for level, (gen, ev, w) in choose(snaps).items():
        NetPolicy(w, hidden, level).save(model_path(level), {"level": level, "generation": gen, "eval": ev})
        print(f"{level}: поколение {gen}, проверка {ev}")
    return 0
