"""Что умеет ИИ на деле: замеры поведения в боях без окна (для README).

    python tools/behaviour.py --games 40

- рикошет: доля попаданий снарядом после отскока;
- упреждение: при выстреле по видимой едущей цели ствол ближе к точке встречи, чем к самой цели;
- укрытие при перезарядке: доля шагов перезарядки, когда танка не видно ни одному врагу,
  против той же доли, когда заряжен.
Считается мир целиком (судья), сами ИИ при этом видят только своё.
"""
import argparse
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def measure(name_a, name_b, games, seed):
    from game.ai.agents import Controller, delay_of, make_policy
    from game.ai.features import lead_point
    from game.ai.match import MAP_POOL, arena_by_name
    from game.core import geom, vision
    from game.core.world import TANK_R, World
    st = {"hits": 0, "rico_hits": 0, "moving_shots": 0, "lead_shots": 0,
          "reload_ticks": 0, "reload_hidden": 0, "ready_ticks": 0, "ready_hidden": 0}
    for i in range(games):
        rng = random.Random(f"{seed}:{i}")
        w = World.new(arena_by_name(rng.choice(MAP_POOL)), 1)
        a_team = i % 2
        ctrls = []
        for t in w.tanks:
            name = name_a if t.team == a_team else name_b
            ctrls.append(Controller(make_policy(name), t.id, delay_of(name), rng=random.Random(f"{seed}:{i}:{t.id}")))
        prev = {t.id: (t.x, t.y) for t in w.tanks}
        while not w.over:
            acts = {c.tid: c.act(w) for c in ctrls if w.tanks[c.tid].alive}
            before = {t.id: (t.x, t.y) for t in w.tanks}
            ev = w.step(acts)
            for e in ev:
                if e[0] == "hit" and w.tanks[e[1]].team == a_team and w.tanks[e[2]].team != a_team:
                    st["hits"] += 1
                    st["rico_hits"] += bool(e[3])
                if e[0] == "shot" and w.tanks[e[1]].team == a_team:
                    me = w.tanks[e[1]]
                    for o in w.tanks:
                        if o.team == me.team or not o.alive:
                            continue
                        if not vision.tank_visible(w.arena, me.x, me.y, o.x, o.y, TANK_R):
                            continue
                        vx, vy = o.x - prev[o.id][0], o.y - prev[o.id][1]
                        if vx * vx + vy * vy < 1e-4:
                            continue
                        st["moving_shots"] += 1
                        lx, ly = lead_point(o.x - me.x, o.y - me.y, vx, vy)
                        e_lead = abs(geom.diff(geom.angle_of(lx, ly), me.aim))
                        e_now = abs(geom.diff(geom.angle_of(o.x - me.x, o.y - me.y), me.aim))
                        st["lead_shots"] += e_lead < e_now
            for t in w.tanks:
                if t.team != a_team or not t.alive:
                    continue
                seen = any(o.alive and o.team != t.team and
                           vision.tank_visible(w.arena, o.x, o.y, t.x, t.y, TANK_R) for o in w.tanks)
                key = "reload" if t.reload > 0 else "ready"
                st[key + "_ticks"] += 1
                st[key + "_hidden"] += not seen
            prev = before
    out = dict(st)
    out["rico_share"] = round(st["rico_hits"] / max(1, st["hits"]), 3)
    out["lead_share"] = round(st["lead_shots"] / max(1, st["moving_shots"]), 3)
    out["hidden_reloading"] = round(st["reload_hidden"] / max(1, st["reload_ticks"]), 3)
    out["hidden_ready"] = round(st["ready_hidden"] / max(1, st["ready_ticks"]), 3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=40)
    ap.add_argument("--seed", type=int, default=77)
    args = ap.parse_args()
    for a, b in (("strong", "strong"), ("strong", "rusher"), ("rusher", "rusher"), ("camper", "rusher")):
        print(json.dumps({"subject": a, "villain": b, **measure(a, b, args.games, args.seed)}, ensure_ascii=False),
              flush=True)


if __name__ == "__main__":
    main()
