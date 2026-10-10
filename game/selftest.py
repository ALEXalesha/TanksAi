"""Самопроверка без экрана: python main.py --selftest итог.txt.

Нужна прежде всего собранному exe: он без консоли, поэтому итог пишется в файл. Окно
создаётся offscreen, данные игрока - во временной папке. Проверяется: мир (случайные бои с
повтором по записи), модели уровней, окно - бой «ИИ против ИИ» и бой против ИИ до конца.
"""
import os
import tempfile
import time
import traceback


def selftest(out_path):
    lines = []
    code = 0
    try:
        from aikit import offscreen
        offscreen.setup(force=True)
        home = tempfile.mkdtemp(prefix="tanksai-selftest-")
        os.environ["TANKSAI_HOME"] = home
        from PySide6.QtWidgets import QApplication

        import aikit
        from aikit.host import make_window
        from game import APP_NAME, GAME_INFO, create_widget
        from game.ai import bots
        from game.ai.agents import LEVEL_NAMES, load_model
        from game.ai.match import battle
        from game.core.replay import play_back
        from game.version import VERSION

        lines.append(f"TanksAi {VERSION} самопроверка (aikit {aikit.__version__})")
        lines.append(f"собранная версия: {'да' if aikit.frozen() else 'нет'}")
        t0 = time.time()
        for i, m in enumerate(("arena", "maze", "bushes", "forts")):
            r = battle(bots.Rusher, bots.Camper, f"self{i}", map_name=m, record=True)
            w = play_back(r.replay)
            if w.state_hash() != r.replay.final_hash:
                raise RuntimeError(f"повтор боя на карте {m} разошёлся")
        lines.append(f"мир: 4 боя ботов, повтор по записи сошёлся, {time.time() - t0:.2f} с")
        lines.append("модели: " + ", ".join(f"{lv} {'есть' if load_model(lv) else 'НЕТ'}" for lv in LEVEL_NAMES))

        app = QApplication.instance() or QApplication([])
        window, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=home)
        window.show()
        g = window.game
        for mode, level in (("watch", "strong"), ("duel", "medium")):
            g.change("mode", mode)
            g.change("level", level)
            g.start_game(seed=7, realtime=False)
            t1 = time.time()
            while not g.session.over:
                g.advance(100)
                app.processEvents()
                if time.time() - t1 > 120:
                    raise RuntimeError("бой идёт дольше 2 минут")
            image = window.grab().toImage()
            if image.isNull() or image.width() < 300:
                raise RuntimeError("окно не нарисовалось")
            lines.append(f"{mode}, ИИ {level}: {g.session.world.tick} шагов, итог «{g.play.status.text()}», "
                         f"кадр {image.width()}x{image.height()}, {time.time() - t1:.2f} с")
        t2 = time.time()
        window.close()
        app.processEvents()
        lines.append(f"окно закрыто за {time.time() - t2:.2f} с")
        lines.append("ИТОГ: работает")
    except Exception:  # noqa: BLE001 - любая ошибка должна попасть в файл
        lines.append("ИТОГ: ошибка")
        lines.append(traceback.format_exc())
        code = 1
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return code
