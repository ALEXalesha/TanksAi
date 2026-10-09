"""Обучение по команде:

    python -m game.train --imitate 300                # тёплый старт: сеть повторяет бота (300 боёв)
    python -m game.train --trial                      # пробные 2 поколения и прогноз времени
    python -m game.train --gens 300                   # обучение (снимок после каждого поколения)
    python -m game.train --gens 300 --resume          # продолжить со снимка
    python -m game.train --publish                    # уровни из снимков -> game/models

Потоки ограничены: каждый работник считает в одном потоке BLAS, работников --workers
(по умолчанию 2 - ПК делят и другие задачи). Журнал и снимки - в --run (runs/tanks).
"""
import os

for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_var] = "1"

import argparse  # noqa: E402
import json  # noqa: E402
import multiprocessing as mp  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m game.train")
    ap.add_argument("--run", default=os.path.join("runs", "tanks"))
    ap.add_argument("--gens", type=int, default=300)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--pairs", type=int, default=12)
    ap.add_argument("--games", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--imitate", type=int, metavar="БОЁВ", help="тёплый старт: подражание боту")
    ap.add_argument("--init", help="начать эволюцию с весов (например, runs/tanks/imitate.npz)")
    ap.add_argument("--trial", action="store_true", help="2 поколения и прогноз времени")
    ap.add_argument("--publish", action="store_true", help="уровни из снимков в game/models")
    args = ap.parse_args(argv)

    from aikit.trainlog import TrainLog, load_snapshot, save_snapshot
    from game.train.evolve import Config, Evolution, evaluate, forecast, warm

    if args.publish:
        from game.train.publish import publish
        return publish(args.run)

    cfg = Config(pairs=args.pairs, games=args.games)
    ev = Evolution(cfg, seed=args.seed)
    snap = os.path.join(args.run, "snapshot.npz")
    log = TrainLog(os.path.join(args.run, "train.log"))
    if args.init and not (args.resume and os.path.exists(snap)):
        arrays, meta = load_snapshot(args.init)
        ev.mean = arrays["mean"].astype("float64")
        log(f"веса из {args.init}: {meta}")
    if args.resume and os.path.exists(snap):
        arrays, meta = load_snapshot(snap)
        ev.restore(arrays, meta)
        log(f"продолжаю с поколения {ev.gen}")

    with mp.get_context("spawn").Pool(args.workers) as pool:
        t0 = time.perf_counter()
        pool.map(warm, range(args.workers))
        log(f"карты готовы за {time.perf_counter() - t0:.1f} с, работников {args.workers}")
        if args.imitate:
            from game.train import imitate
            t1 = time.perf_counter()
            x, y = imitate.collect(args.imitate, args.seed, pool, args.workers)
            log(f"подражание: {args.imitate} боёв ботов, {len(x)} решений за {time.perf_counter() - t1:.0f} с")
            cut = len(x) * 9 // 10
            params = imitate.fit(x[:cut], y[:cut], cfg.hidden, log=log)
            agree = imitate.agreement(params, cfg.hidden, x[cut:], y[cut:])
            score = evaluate(params, cfg.hidden, cfg.eval_games, pool, args.workers)
            log(f"подражание: совпадение с ботом на отложенных {agree}, проверка {score}")
            save_snapshot(os.path.join(args.run, "imitate.npz"), {"mean": params},
                          {"games": args.imitate, "decisions": int(len(x)), "agreement": agree, "eval": score,
                           "seconds": round(time.perf_counter() - t1)})
            return 0
        if args.trial:
            rows = [ev.generation(pool) for _ in range(2)]
            t1 = time.perf_counter()
            score = evaluate(ev.mean, cfg.hidden, 8, pool, args.workers)
            eval_sec = (time.perf_counter() - t1) / 8 * cfg.eval_games
            per_gen = sum(r["seconds"] for r in rows) / len(rows)
            fc = forecast(per_gen, args.gens, eval_sec, args.gens // cfg.eval_every)
            print(json.dumps({"rows": rows, "trial_eval": score, "forecast": fc}, ensure_ascii=False))
            return 0
        while ev.gen < args.gens:
            row = ev.generation(pool)
            if ev.gen % cfg.eval_every == 0:
                score = evaluate(ev.mean, cfg.hidden, cfg.eval_games, pool, args.workers)
                row["eval"] = score
                total = score["rusher"] + score["camper"]
                if ev.best is None or total >= ev.best[0]:
                    ev.best = (total, ev.gen, ev.mean.copy())
                save_snapshot(os.path.join(args.run, f"gen{ev.gen:04d}.npz"), {"mean": ev.mean},
                              {"gen": ev.gen, "eval": score})
            log(json.dumps(row, ensure_ascii=False))
            arrays, meta = ev.state()
            save_snapshot(snap, arrays, meta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
