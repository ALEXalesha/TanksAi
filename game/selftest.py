"""Самопроверка без экрана: python main.py --selftest итог.txt.

Нужна прежде всего собранному exe: он без консоли, поэтому итог пишется в файл.
"""
import traceback


def selftest(out_path):
    lines = []
    code = 0
    try:
        import aikit
        from game.version import VERSION
        lines.append(f"TanksAi {VERSION} самопроверка (aikit {aikit.__version__})")
        lines.append("ИТОГ: работает")
    except Exception:  # noqa: BLE001 - любая ошибка должна попасть в файл
        lines.append("ИТОГ: ошибка")
        lines.append(traceback.format_exc())
        code = 1
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return code
