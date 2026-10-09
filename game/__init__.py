"""TanksAi: танчики вид сверху против ИИ, который научился воевать сам.

Вход игры по контракту PythonAiGames: GAME_INFO и create_widget(ctx). Qt загружается
только в create_widget - правила, ИИ и обучение работают без него.
"""
from game.version import VERSION

GAME_INFO = {
    "id": "tanks",
    "title": {"ru": "Танчики", "en": "Tanks"},
    "summary": {"ru": "Танковый бой вид сверху против ИИ, который видит только то, что видно из его башни",
                "en": "Top-down tank battle against an AI that sees only what is visible from its turret"},
    "preview": "docs/preview.png",
    "version": VERSION,
}

APP_NAME = "TanksAi"


def create_widget(ctx):
    """ctx: aikit.Context. Виджет с меню, полем боя и панелями."""
    from game.ui.widget import GameWidget
    return GameWidget(ctx)
