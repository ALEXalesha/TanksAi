# Мутанты для tools/mutate.py: (имя, файл, было, стало, проверки).
WO = "game/core/world.py"
TW = "tests/test_world.py"
MUTANTS = [
    ("world: назад как вперёд", WO, "v = FWD if move > 0 else -BACK", "v = FWD if move > 0 else -FWD", TW),
    ("world: корпус не крутится", WO, "t.hull = (t.hull + turn * HULL_TURN) % ang", "pass", TW),
    ("world: башня без предела", WO, "max(-TURRET_TURN, min(TURRET_TURN, int(a.turret)))", "int(a.turret)", TW),
    ("world: башня не держится за корпус", WO, "return (self.hull + self.turret) % geom.ANG",
     "return self.turret % geom.ANG", TW),
    ("world: сквозь стены", WO, "if k == STEEL or k == BRICK:\n                    nx", "if k == STEEL:\n                    nx", TW),
    ("world: без скольжения", WO, "elif self._free(t, t.x + dx, t.y):", "elif False:", TW),
    ("world: танки сквозь танки", WO, "if o is not t and o.lives > 0 and", "if False and", TW),
    ("world: без перезарядки", WO, "t.reload = RELOAD\n", "t.reload = 0\n", TW),
    ("world: перезарядка не идёт", WO, "                t.reload -= 1\n", "                pass\n", TW),
    ("world: снаряд не отскакивает", WO, "if s.bounces <= 0:", "if True:", TW),
    ("world: отскок без конца", WO, "                s.bounces -= 1\n", "", TW),
    ("world: отскок не меняет x", WO, "                    s.vx, sx = -s.vx, -sx\n", "                    pass\n", TW),
    ("world: отскок не меняет y", WO, "                    s.vy, sy = -s.vy, -sy\n", "                    pass\n", TW),
    ("world: кирпич не ломается", WO, "a.tiles[r * a.W + c] = FLOOR", "pass", TW),
    ("world: свой снаряд ранит сразу", WO, "(t.id == s.owner and not s.bounced)", "False", TW),
    ("world: огонь по своим", WO, "if t.team != s.team or t.id == s.owner:", "if True:", TW),
    ("world: попадание не считается", WO, "self.tanks[s.owner].hits += 1", "pass", TW),
    ("world: снаряды не гасят друг друга", WO, "                    gone.add(a.id)\n                    gone.add(b.id)\n",
     "                    pass\n", TW),
    ("world: снаряд вечный", WO, "if s.age >= SHELL_LIFE:", "if False:", TW),
    ("world: промах не считается", WO, "self.misses[s.owner] = self.misses.get(s.owner, 0) + 1", "pass", TW),
    ("world: по времени не ничья", WO, "self.winner = 0 if lives[0] > lives[1] else 1 if lives[1] > lives[0] else -1",
     "self.winner = 0 if lives[0] >= lives[1] else 1", TW),
    ("world: победа без уничтожения", WO, "if alive[0] and not alive[1]:", "if alive[0]:", TW),
    ("world: отпечаток без снарядов", WO, "s.bounces, s.age, int(s.bounced)))", "0, 0, 0))", TW),
]
GE = "game/core/geom.py"
MUTANTS += [
    ("geom: поворот не кратчайший", GE, "return (a - b + HALF) % ANG - HALF", "return (a - b) % ANG", TW),
]
RE = "game/core/replay.py"
MUTANTS += [
    ("replay: стоп-кадры не пишутся", RE, "if a.as_tuple() != (0, 0, 0, 0):", "if a.move:", TW),
]
VI = "game/core/vision.py"
TM = "tests/test_maps.py"
MUTANTS += [
    ("vision: кусты прозрачны", VI, "if not (0 <= c < W and 0 <= r < arena.H) or opaque_tile(tiles[r * W + c]):",
     "if not (0 <= c < W and 0 <= r < arena.H) or tiles[r * W + c] in (1, 2):", TM),
    ("vision: в кусте видно издали", VI, "if arena.tile(int(px), int(py)) == BUSH and", "if False and", TM),
    ("vision: бока не смотрятся", VI, "        if point_visible(arena, ex, ey, sx, sy):\n            return True\n", "", TM),
    ("vision: луч сквозь куст", VI, "        k = tiles[r * W + c]\n        if k:", "        k = tiles[r * W + c]\n        if k in (1, 2):", TM),
]
MG = "game/core/mapgen.py"
MUTANTS += [
    ("mapgen: симметрия не проверяется", MG, '"symmetric": rep["symmetric"],', '"symmetric": True,', TM),
    ("mapgen: карманы не проверяются", MG, '"connected": rep["connected"],', '"connected": True,', TM),
    ("mapgen: базы видят друг друга", MG, '"bases_hidden": rep["bases_hidden"],', '"bases_hidden": True,', TM),
    ("mapgen: укрытия не поровну", MG, '"cover": rep["cover"][0] == rep["cover"][1],', '"cover": True,', TM),
    ("mapgen: места не сверяются", MG, '"spawns_symmetric": rep["spawns_symmetric"],', '"spawns_symmetric": True,', TM),
    ("mapgen: путь до центра не сверяется", MG, '"to_centre": rep["to_centre"][0] == rep["to_centre"][1] < inf,',
     '"to_centre": rep["to_centre"][0] < inf,', TM),
    ("mapgen: близкие базы", MG, '"between_bases": rep["between_bases"] >= 2 * MIN_PATH,', '"between_bases": True,', TM),
    ("mapgen: карманы не заделываются", MG, "            arena.tiles[k] = STEEL\n", "            pass\n", TM),
    ("mapgen: диагональ сквозь угол", MG,
     "if dc and dr and (arena.solid(c + dc, r) or arena.solid(c, r + dr)):", "if False:", TM),
]
