"""Танчики против ИИ, который научился воевать сам.

    python main.py                         # игра
    python main.py --offscreen             # без экрана (проверки)
    python main.py --selftest итог.txt     # самопроверка без экрана, итог в файл
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Танчики против ИИ")
    ap.add_argument("--selftest", metavar="ФАЙЛ", nargs="?", const="selftest.txt",
                    help="без окна сыграть бой через окно и записать итог в файл")
    ap.add_argument("--offscreen", action="store_true", help="без экрана")
    args = ap.parse_args(argv)
    if args.selftest:
        from game.selftest import selftest
        return selftest(args.selftest)
    if args.offscreen:
        from aikit import offscreen
        offscreen.setup(force=True)
    import aikit
    from game import APP_NAME, GAME_INFO, create_widget
    from game.ui.icon import app_icon
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841 - иконке нужно приложение
    return aikit.run_standalone(GAME_INFO, create_widget, APP_NAME, icon=app_icon())


if __name__ == "__main__":
    sys.exit(main())
