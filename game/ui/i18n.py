"""Строки окна на русском и английском."""
from aikit.i18n import Translator

RU = {
    "subtitle": "Танковый бой вид сверху. ИИ видит только то, что видно из его башни, и замечает врага с опозданием, как человек.",
    "mode": "Режим", "level": "Уровень ИИ", "map": "Карта",
    "mode_duel": "1 на 1", "mode_team": "2 на 2", "mode_hotseat": "Вдвоём", "mode_watch": "ИИ против ИИ",
    "level_novice": "Новичок", "level_medium": "Средний", "level_strong": "Сильный",
    "map_random": "Случайная", "map_arena": "Арена", "map_maze": "Лабиринт", "map_bushes": "Кусты",
    "map_forts": "Крепости", "map_generated": "Новая",
    "bounce": "Рикошет от стен", "bricks": "Кирпичи ломаются", "fog": "Туман войны",
    "thoughts": "Мысли ИИ", "play": "В бой", "stats": "Статистика", "back": "Меню",
    "pause": "Пауза", "resume": "Дальше", "again": "Ещё раз", "theme": "Тема", "lang": "Язык",
    "theme_dark": "Тёмная", "theme_light": "Светлая",
    "keys_solo": "Езда: WASD или стрелки. Башня: мышь (без захвата курсора) или Q/E. Огонь: пробел или левая кнопка.",
    "keys_hotseat": "Синий: WASD, башня Q/E, огонь пробел. Красный: стрелки, башня , и ., огонь Enter.",
    "keys_watch": "Смотрите, как воюют ИИ. «Мысли ИИ» показывают лучи, прицел и где ИИ думает, что враг.",
    "note_level": "Реакция ИИ: {ms} мс.",
    "note_no_model": "Сеть ещё не обучена - играет бот.",
    "you": "Вы", "ally": "Напарник", "enemy": "ИИ", "player1": "Синий", "player2": "Красный",
    "blue": "Синие", "red": "Красные",
    "lives": "Жизни", "reload": "Перезарядка", "time": "Время", "hits": "Попадания", "misses": "Промахи",
    "win": "Победа!", "loss": "Поражение", "draw": "Ничья",
    "win_blue": "Победили синие", "win_red": "Победили красные",
    "peeked": "Бой с «Мыслями ИИ» не идёт в статистику.",
    "stats_title": "Статистика", "games": "Боёв", "wins": "Побед", "losses": "Поражений", "draws": "Ничьих",
    "best_streak": "Лучшая серия", "passport": "Паспорт модели", "no_passport": "Паспорта ещё нет: модель не обучена.",
    "vs_rusher": "против агрессивного бота", "vs_camper": "против осторожного бота",
    "win_rate": "{p}% побед", "nothing_yet": "Боёв пока не было.",
    "thinks_here": "думает, что враг здесь", "seen_ago": "видел {s} с назад",
}

EN = {
    "subtitle": "A top-down tank battle. The AI sees only what is visible from its turret and notices you with a delay, like a person.",
    "mode": "Mode", "level": "AI level", "map": "Map",
    "mode_duel": "1 vs 1", "mode_team": "2 vs 2", "mode_hotseat": "Two players", "mode_watch": "AI vs AI",
    "level_novice": "Novice", "level_medium": "Medium", "level_strong": "Strong",
    "map_random": "Random", "map_arena": "Arena", "map_maze": "Maze", "map_bushes": "Bushes",
    "map_forts": "Forts", "map_generated": "New",
    "bounce": "Ricochet off walls", "bricks": "Breakable bricks", "fog": "Fog of war",
    "thoughts": "AI thoughts", "play": "Battle", "stats": "Statistics", "back": "Menu",
    "pause": "Pause", "resume": "Resume", "again": "Again", "theme": "Theme", "lang": "Language",
    "theme_dark": "Dark", "theme_light": "Light",
    "keys_solo": "Drive: WASD or arrows. Turret: mouse (the cursor is never captured) or Q/E. Fire: Space or left button.",
    "keys_hotseat": "Blue: WASD, turret Q/E, fire Space. Red: arrows, turret , and ., fire Enter.",
    "keys_watch": "Watch the AIs fight. \"AI thoughts\" show the rays, the aim and where the AI thinks the enemy is.",
    "note_level": "AI reaction: {ms} ms.",
    "note_no_model": "The network is not trained yet - a bot plays.",
    "you": "You", "ally": "Ally", "enemy": "AI", "player1": "Blue", "player2": "Red",
    "blue": "Blue", "red": "Red",
    "lives": "Lives", "reload": "Reload", "time": "Time", "hits": "Hits", "misses": "Misses",
    "win": "Victory!", "loss": "Defeat", "draw": "Draw",
    "win_blue": "Blue wins", "win_red": "Red wins",
    "peeked": "A battle with \"AI thoughts\" does not count in the statistics.",
    "stats_title": "Statistics", "games": "Battles", "wins": "Wins", "losses": "Losses", "draws": "Draws",
    "best_streak": "Best streak", "passport": "Model passport", "no_passport": "No passport yet: the model is not trained.",
    "vs_rusher": "vs the aggressive bot", "vs_camper": "vs the cautious bot",
    "win_rate": "{p}% wins", "nothing_yet": "No battles yet.",
    "thinks_here": "thinks the enemy is here", "seen_ago": "seen {s} s ago",
}


def translator(lang):
    return Translator({"ru": RU, "en": EN}, lang)
