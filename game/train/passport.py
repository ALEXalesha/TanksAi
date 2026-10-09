"""Паспорт модели: проверки силы (spec §3) и сведения об обучении.

    python -m game.train.passport                # 200 боёв на проверку, 2 процесса
    python -m game.train.passport --games 40

Бой i проверки - зерно f"{seed}:{i}", карта из пула по этому зерну, стороны меняются через
бой. Первые SAMPLE боёв записываются поштучно: тесты пересчитывают их с теми же зёрнами.
"""
import os

for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_var] = "1"

import argparse  # noqa: E402
import json  # noqa: E402
import multiprocessing as mp  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

SAMPLE = 6
PASSPORT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "tanks.json")
# (испытуемый, соперник, зерно)
CHECKS = [
    ("strong", "rusher", 301), ("strong", "camper", 302),
    ("medium", "rusher", 311), ("medium", "camper", 312),
    ("novice", "rusher", 321), ("novice", "camper", 322),
    ("strong", "medium", 331), ("strong", "novice", 332), ("medium", "novice", 333),
]


def run_part(job):
    a, b, seed, indices = job
    from game.ai.agents import delay_of, make_policy
    from game.ai.match import series
    res = series(lambda: make_policy(a), lambda: make_policy(b), 0, seed, 1, delay_of(a), delay_of(b),
                 indices=indices)
    return [(i, r.row()) for i, r in zip(indices, res)]


def replay_rows(a, b, seed, indices):
    return [row for _, row in run_part((a, b, seed, list(indices)))]


def run_check(pool, workers, a, b, seed, games):
    parts = [list(range(k, games, workers)) for k in range(workers)]
    jobs = [(a, b, seed, p) for p in parts if p]
    res = pool.map(run_part, jobs) if pool else [run_part(j) for j in jobs]
    rows = sorted((x for r in res for x in r), key=lambda x: x[0])
    rows = [r for _, r in rows]
    n = len(rows)
    w = sum(r[0] == "W" for r in rows)
    d = sum(r[0] == "D" for r in rows)
    hits = sum(r[1] for r in rows)
    shots = sum(r[3] for r in rows)
    return {"subject": a, "villain": b, "seed": seed, "games": n, "wins": w, "draws": d, "losses": n - w - d,
            "win_rate": round(w / n, 4), "score": round((w + d / 2) / n, 4),
            "hits_per_game": round(hits / n, 3), "taken_per_game": round(sum(r[2] for r in rows) / n, 3),
            "misses_per_game": round((shots - hits) / n, 3), "accuracy": round(hits / shots, 4) if shots else 0.0,
            "avg_seconds": round(sum(r[5] for r in rows) / n / 30, 2), "sample": rows[:SAMPLE]}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m game.train.passport")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--run", default=os.path.join("runs", "tanks"))
    args = ap.parse_args(argv)
    from aikit.trainlog import load_snapshot
    from game.ai.agents import LEVELS, load_model, reaction_ms
    from game.ai.net import n_params
    t0 = time.time()
    checks = []
    with mp.get_context("spawn").Pool(args.workers) as pool:
        for a, b, seed in CHECKS:
            c = run_check(pool, args.workers, a, b, seed, args.games)
            checks.append(c)
            print(json.dumps({k: v for k, v in c.items() if k != "sample"}, ensure_ascii=False), flush=True)
    snap = load_snapshot(os.path.join(args.run, "snapshot.npz"))
    meta = snap[1] if snap else {}
    levels = {}
    for lv in LEVELS:
        net = load_model(lv)
        levels[lv] = {"reaction_ms": reaction_ms(lv), "generation": (net.meta or {}).get("generation") if net else None}
    cfg = meta.get("cfg", {})
    out = {
        "games_per_check": args.games,
        "checks": checks,
        "levels": levels,
        "network": {"hidden": cfg.get("hidden"), "parameters": n_params(tuple(cfg.get("hidden", (32, 32))))},
        "training": {"method": "OpenAI-ES (pairs ±noise), league of past snapshots + 2 bots",
                     "generations": meta.get("gen"), "games": meta.get("games"),
                     "seconds": round(meta.get("seconds", 0)), "workers": 2},
        "passport_seconds": round(time.time() - t0),
    }
    with open(PASSPORT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"паспорт: {PASSPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
