"""Рейтинг снимков обучения: каждый снимок играет с одной и той же «комиссией» - два бота и
несколько снимков-эталонов. Так видно, какой снимок сильнее в целом, а не только против
ботов (проверка в обучении смотрит только на ботов).

    python -m game.train.rank --games 16 --panel 50,150,300
"""
import os

for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_var] = "1"

import argparse  # noqa: E402
import glob  # noqa: E402
import json  # noqa: E402
import multiprocessing as mp  # noqa: E402
import random  # noqa: E402
import sys  # noqa: E402


def load(run, gen):
    from aikit.trainlog import load_snapshot
    arrays, meta = load_snapshot(os.path.join(run, f"gen{gen:04d}.npz"))
    return arrays["mean"].astype("float32")


def job(args):
    """(поколение, соперник, бои) -> очки снимка против соперника."""
    run, gen, opp, idx, hidden = args
    from game.ai import bots
    from game.ai.match import MAP_POOL, battle
    from game.ai.net import NetPolicy
    w = load(run, gen)
    if opp in ("rusher", "camper"):
        make_b = bots.Rusher if opp == "rusher" else bots.Camper
        delay_b = 6
    else:
        wb = load(run, int(opp))
        make_b = lambda: NetPolicy(wb, hidden)  # noqa: E731
        delay_b = 3
    pts = 0.0
    for i in idx:
        r = random.Random(f"rank:{i}")
        res = battle(lambda: NetPolicy(w, hidden), make_b, f"rank:{i}", 1, r.choice(MAP_POOL), 3, delay_b,
                     swap=i % 2 == 1)
        pts += {"W": 1.0, "D": 0.5, "L": 0.0}[res.outcome]
    return gen, opp, pts, len(idx)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m game.train.rank")
    ap.add_argument("--run", default=os.path.join("runs", "tanks"))
    ap.add_argument("--games", type=int, default=16)
    ap.add_argument("--panel", default="50,150,300")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--every", type=int, default=20)
    args = ap.parse_args(argv)
    gens = sorted(int(os.path.basename(p)[3:7]) for p in glob.glob(os.path.join(args.run, "gen*.npz")))
    gens = [g for g in gens if g % args.every == 0 or g == gens[-1]]
    panel = ["rusher", "camper"] + [p for p in args.panel.split(",") if p]
    jobs = [(args.run, g, opp, list(range(args.games)), (32, 32)) for g in gens for opp in panel]
    with mp.get_context("spawn").Pool(args.workers) as pool:
        res = pool.map(job, jobs)
    table = {}
    for g, opp, pts, n in res:
        table.setdefault(g, {})[opp] = round(pts / n, 3)
    for g in gens:
        row = table[g]
        row["mean"] = round(sum(row[o] for o in panel) / len(panel), 3)
        print(json.dumps({"gen": g, **row}, ensure_ascii=False), flush=True)
    with open(os.path.join(args.run, "rank.json"), "w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
