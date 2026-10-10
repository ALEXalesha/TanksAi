"""Кадры для README и списка игр - окно без экрана (Qt offscreen), данные во временной папке.

    python tools/make_previews.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    from aikit import offscreen
    offscreen.setup(force=True)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from aikit.host import make_window
    from game import APP_NAME, GAME_INFO, create_widget
    home = tempfile.mkdtemp(prefix="tanksai-shots-")
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=home)
    w.resize(1280, 720)
    w.show()
    g = w.game
    docs = os.path.join(ROOT, "docs")

    def shot(name):
        app.processEvents()
        w.grab().save(os.path.join(docs, name))
        print(name)

    shot("preview_menu.png")
    g.change("map", "forts")
    g.change("mode", "watch")
    g.change("level", "strong")
    g.change("show_thoughts", True)
    g.start_game(seed=21, realtime=False)
    g.advance(170)
    shot("preview.png")
    g.change("show_thoughts", False)
    g.change("mode", "duel")
    g.change("map", "bushes")
    g.change("fog", True)
    g.start_game(seed=5, realtime=False)
    g.advance(200)
    shot("preview_duel.png")
    g.change("mode", "team")
    g.change("map", "maze")
    ctx.set_theme("light")
    g.start_game(seed=3, realtime=False)
    g.advance(260)
    shot("preview_team_light.png")
    ctx.set_theme("dark")
    w.close()


if __name__ == "__main__":
    main()
