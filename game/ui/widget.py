"""Виджет игры (create_widget по контракту): меню, поле боя с панелью, статистика.

Окно ему даёт оболочка (aikit.run_standalone или ИИ-Игротека). Тема и язык приходят из
ctx и меняются на лету по ctx.changed. Файлы - только в ctx.data_dir. Потоков нет: мир и
ИИ считаются по таймеру в главном потоке (шаг ИИ - доли миллисекунды), shutdown()
останавливает таймер.
"""
import json
import os

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QStackedWidget,
                               QVBoxLayout, QWidget)

from aikit import settings as st
from aikit import theme
from aikit.widgets import Combo, button, card, label, restyle, segmented
from game.ai.agents import LEVEL_NAMES, load_model, reaction_ms
from game.core.world import RELOAD, TICK_HZ
from game.ui.arena_view import TEAM_COLORS, ArenaView
from game.ui.i18n import translator
from game.ui.session import MAP_CHOICES, MODES, Session

SCHEMA = {
    "mode": ("duel", st.choice(*MODES)),
    "level": ("medium", st.choice(*LEVEL_NAMES)),
    "map": ("random", st.choice(*MAP_CHOICES)),
    "bounce": (True, st.boolean()),
    "bricks": (True, st.boolean()),
    "fog": (True, st.boolean()),
    "show_thoughts": (False, st.boolean()),
}
PASSPORT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "tanks.json")
MAX_STEPS_PER_FRAME = 4


def page_widget():
    w = QWidget()
    w.setObjectName("page")
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    return w


def load_passport():
    try:
        with open(PASSPORT, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


class MenuPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.addStretch(2)
        col = QVBoxLayout()
        col.setSpacing(10)
        col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        from PySide6.QtGui import QPixmap
        from game.ui.icon import render
        self.logo = QLabel()
        self.logo.setPixmap(QPixmap.fromImage(render(96)))
        col.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignHCenter)
        self.title = label("", "title")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.title)
        self.sub = label("", "muted", wrap=True)
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub.setFixedWidth(640)
        col.addWidget(self.sub, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(8)
        box = card()
        box.setMaximumWidth(680)
        grid = QGridLayout(box)
        grid.setContentsMargins(22, 18, 22, 18)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        self.captions = {}

        def row(r, key, widget):
            cap = label("", "muted")
            self.captions[key] = cap
            grid.addWidget(cap, r, 0)
            grid.addWidget(widget, r, 1)

        w, self.mode_buttons = segmented({m: "" for m in MODES}, lambda v: gw.change("mode", v))
        row(0, "mode", w)
        w, self.level_buttons = segmented({lv: "" for lv in LEVEL_NAMES}, lambda v: gw.change("level", v))
        row(1, "level", w)
        self.map_combo = Combo()
        for m in MAP_CHOICES:
            self.map_combo.addItem("", m)
        self.map_combo.currentIndexChanged.connect(lambda i: gw.change("map", MAP_CHOICES[i]))
        row(2, "map", self.map_combo)
        checks = QWidget()
        cl = QHBoxLayout(checks)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(16)
        self.checks = {}
        for key in ("bounce", "bricks", "fog"):
            cb = QCheckBox()
            cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            cb.toggled.connect(lambda on, k=key: gw.change(k, on))
            cl.addWidget(cb)
            self.checks[key] = cb
        cl.addStretch(1)
        grid.addWidget(checks, 3, 0, 1, 2)
        col.addWidget(box, 0, Qt.AlignmentFlag.AlignHCenter)
        self.note = label("", "hint", wrap=True)
        self.note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.note.setFixedWidth(640)
        col.addWidget(self.note, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(6)
        self.play_button = button("", "menuPrimary", lambda: gw.start_game())
        self.stats_button = button("", "menu", lambda: gw.show_page("stats"))
        col.addWidget(self.play_button, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(self.stats_button, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addLayout(col)
        outer.addStretch(3)
        foot = QHBoxLayout()
        foot.addStretch(1)
        self.theme_caption = label("", "hint")
        foot.addWidget(self.theme_caption)
        w, self.theme_buttons = segmented({th: "" for th in theme.THEMES}, gw.ctx.set_theme)
        foot.addWidget(w)
        foot.addSpacing(16)
        self.lang_caption = label("", "hint")
        foot.addWidget(self.lang_caption)
        w, self.lang_buttons = segmented({"ru": "RU", "en": "EN"}, gw.ctx.set_lang)
        foot.addWidget(w)
        foot.addStretch(1)
        outer.addLayout(foot)

    def retranslate(self, t):
        self.title.setText(t("title_game"))
        self.sub.setText(t("subtitle"))
        for k, cap in self.captions.items():
            cap.setText(t(k))
        for m, b in self.mode_buttons.items():
            b.setText(t(f"mode_{m}"))
        for lv, b in self.level_buttons.items():
            b.setText(t(f"level_{lv}"))
        for i, m in enumerate(MAP_CHOICES):
            self.map_combo.setItemText(i, t(f"map_{m}"))
        for k, cb in self.checks.items():
            cb.setText(t(k))
        self.play_button.setText(t("play"))
        self.stats_button.setText(t("stats"))
        self.theme_caption.setText(t("theme"))
        for th, b in self.theme_buttons.items():
            b.setText(t(f"theme_{th}"))
        self.lang_caption.setText(t("lang"))

    def sync(self, s, t, ctx):
        self.mode_buttons[s["mode"]].setChecked(True)
        self.level_buttons[s["level"]].setChecked(True)
        self.map_combo.blockSignals(True)
        self.map_combo.setCurrentIndex(MAP_CHOICES.index(s["map"]))
        self.map_combo.blockSignals(False)
        for k, cb in self.checks.items():
            cb.blockSignals(True)
            cb.setChecked(s[k])
            cb.blockSignals(False)
        self.checks["fog"].setEnabled(s["mode"] in ("duel", "team"))
        self.theme_buttons[ctx.theme].setChecked(True)
        self.lang_buttons[ctx.lang].setChecked(True)
        note = t("note_level", ms=reaction_ms(s["level"]))
        if load_model(s["level"]) is None:
            note += " " + t("note_no_model")
        keys = {"hotseat": "keys_hotseat", "watch": "keys_watch"}.get(s["mode"], "keys_solo")
        self.note.setText(note + "\n" + t(keys))


class PlayPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(12)
        self.arena = ArenaView()
        row.addWidget(self.arena, 1)
        panel = card()
        panel.setFixedWidth(270)
        col = QVBoxLayout(panel)
        col.setContentsMargins(16, 16, 16, 16)
        col.setSpacing(10)
        self.status = label("", "status", wrap=True)
        col.addWidget(self.status)
        self.clock = label("", "muted")
        col.addWidget(self.clock)
        self.tanks = label("", None, wrap=True)
        self.tanks.setTextFormat(Qt.TextFormat.RichText)
        col.addWidget(self.tanks)
        self.thoughts = QCheckBox()
        self.thoughts.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.thoughts.toggled.connect(lambda on: gw.change("show_thoughts", on))
        col.addWidget(self.thoughts)
        self.peek = label("", "hint", wrap=True)
        col.addWidget(self.peek)
        col.addStretch(1)
        self.pause_button = button("", None, gw.toggle_pause)
        self.again_button = button("", "primary", lambda: gw.start_game())
        self.menu_button = button("", None, lambda: gw.show_page("menu"))
        for b in (self.pause_button, self.again_button, self.menu_button):
            col.addWidget(b)
        self.keys = label("", "hint", wrap=True)
        col.addWidget(self.keys)
        row.addWidget(panel)


class StatsPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 30, 40, 30)
        self.heading = label("", "heading")
        outer.addWidget(self.heading)
        self.body = label("", None, wrap=True)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        outer.addWidget(self.body, 1)
        self.back = button("", "menu", lambda: gw.show_page("menu"))
        outer.addWidget(self.back, 0, Qt.AlignmentFlag.AlignLeft)

    def refresh(self, t, ctx):
        self.heading.setText(t("stats_title"))
        self.back.setText(t("back"))
        lines = []
        rows = sorted(ctx.stats.data.items())
        if not rows:
            lines.append(t("nothing_yet"))
        for key, e in rows:
            mode, _, level = key.partition("/")
            lines.append(f"<b>{t('mode_' + mode)} · {t('level_' + level)}</b>: {t('games')} {e['games']}, "
                         f"{t('wins')} {e['wins']}, {t('losses')} {e['losses']}, {t('draws')} {e['draws']}, "
                         f"{t('best_streak')} {e['best_streak']}")
        pp = load_passport()
        lines.append(f"<br><b>{t('passport')}</b>")
        if pp is None:
            lines.append(t("no_passport"))
        else:
            for c in pp["checks"]:
                if c["villain"] in ("rusher", "camper"):
                    lines.append(f"{t('level_' + c['subject'])} {t('vs_' + c['villain'])}: "
                                 f"{t('win_rate', p=round(c['win_rate'] * 100, 1))}, "
                                 f"{t('hits')} {c['hits_per_game']}, {t('misses')} {c['misses_per_game']}")
        self.body.setText("<br>".join(lines))


class GameWidget(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.t = translator(ctx.lang)
        self.settings = st.Settings(SCHEMA, ctx.file("settings.json"))
        self.session = None
        self.paused = False
        self.recorded = False
        self.ticks_done = 0
        self.clock = QElapsedTimer()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.menu = MenuPage(self)
        self.play = PlayPage(self)
        self.stats = StatsPage(self)
        self.pages = {"menu": self.menu, "play": self.play, "stats": self.stats}
        for p in self.pages.values():
            self.stack.addWidget(p)
        self.timer = QTimer(self)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self.frame)
        ctx.changed.connect(self.on_ctx)
        self.on_ctx("lang")

    # --- настройки и страницы ---

    def on_ctx(self, what):
        self.t = translator(self.ctx.lang)
        self.t.tables["ru"].setdefault("title_game", "Танчики")
        self.t.tables["en"].setdefault("title_game", "Tanks")
        self.menu.retranslate(self.t)
        self.play.arena.theme = self.ctx.theme
        self.play.arena.lang = self.ctx.lang
        for b in self.menu.lang_buttons.values():
            b.setMinimumWidth(48)
        self.sync()
        if self.current_page() == "stats":
            self.stats.refresh(self.t, self.ctx)
        self.play.arena.update()

    def change(self, key, value):
        self.settings.set(key, value)
        if key == "show_thoughts":
            self.play.arena.show_thoughts = value
            if self.session is not None:
                self.session.want_thoughts(value)
            self.play.arena.update()
        self.sync()

    def sync(self):
        s = self.settings
        self.menu.sync(s, self.t, self.ctx)
        t = self.t
        self.play.thoughts.blockSignals(True)
        self.play.thoughts.setChecked(s["show_thoughts"])
        self.play.thoughts.blockSignals(False)
        self.play.thoughts.setText(t("thoughts"))
        self.play.again_button.setText(t("again"))
        self.play.menu_button.setText(t("back"))
        self.play.pause_button.setText(t("resume") if self.paused else t("pause"))
        mode = self.session.mode if self.session else s["mode"]
        keys = {"hotseat": "keys_hotseat", "watch": "keys_watch"}.get(mode, "keys_solo")
        self.play.keys.setText(t(keys))
        self.play.peek.setText(t("peeked") if self.session is not None and self.session.peeked else "")
        self.update_panel()

    def current_page(self):
        for name, p in self.pages.items():
            if self.stack.currentWidget() is p:
                return name
        return None

    def show_page(self, name):
        if name != "play":
            self.timer.stop()
        if name == "stats":
            self.stats.refresh(self.t, self.ctx)
        self.stack.setCurrentWidget(self.pages[name])
        if name == "play" and self.session is not None and not self.paused:
            self.timer.start()

    # --- бой ---

    def start_game(self, seed=None, realtime=True):
        s = self.settings
        self.session = Session(s["mode"], s["level"], s["map"], s["bounce"], s["bricks"], s["fog"], seed)
        self.session.want_thoughts(s["show_thoughts"])
        self.recorded = False
        self.paused = False
        self.ticks_done = 0
        view = self.play.arena
        view.session = self.session
        view.effects = []
        view.keys.clear()
        view.show_thoughts = s["show_thoughts"]
        self.show_page("play")
        view.setFocus()
        self.clock.start()
        if not realtime:
            self.timer.stop()
        self.sync()

    def toggle_pause(self):
        if self.session is None or self.session.over:
            return
        self.paused = not self.paused
        if self.paused:
            self.timer.stop()
        else:
            self.clock.start()
            self.ticks_done = 0
            self.timer.start()
        self.sync()

    def frame(self):
        """Кадр таймера: столько шагов мира, сколько прошло времени (не больше 4 за кадр)."""
        if self.session is None or self.paused:
            return
        due = int(self.clock.elapsed() * TICK_HZ / 1000) - self.ticks_done
        n = max(0, min(due, MAX_STEPS_PER_FRAME))
        if due > MAX_STEPS_PER_FRAME:
            self.ticks_done += due - n          # отстали (окно двигали) - не догоняем рывком
        self.advance(n)
        self.play.arena.update()

    def advance(self, n=1):
        """n шагов мира (тесты зовут напрямую, без таймера)."""
        s = self.session
        view = self.play.arena
        for _ in range(n):
            if s.over:
                break
            events = s.step(view.human_actions())
            view.add_events(events)
            view.age_effects()
            self.ticks_done += 1
            for e in events:
                if e[0] == "shot":
                    self.ctx.sound.play("move")
                elif e[0] == "hit":
                    self.ctx.sound.play("capture")
        if s.over and not self.recorded:
            self.finish()
        self.update_panel()

    def finish(self):
        self.recorded = True
        self.timer.stop()
        s = self.session
        res = s.result()
        if res is not None:
            if not s.peeked:
                self.ctx.stats.record(s.stats_key(), res)
            self.ctx.sound.play(res)
        else:
            self.ctx.sound.play("win" if s.world.winner in (0, 1) else "draw")
        self.play.arena.update()
        self.sync()

    def update_panel(self):
        s = self.session
        t = self.t
        page = self.play
        if s is None:
            page.status.setText("")
            page.tanks.setText("")
            page.clock.setText("")
            return
        w = s.world
        if w.over:
            res = s.result()
            if res is not None:
                page.status.setText(t(res))
                restyle(page.status, {"win": "statusWin", "loss": "statusLoss", "draw": "statusDraw"}[res])
            else:
                text = t("draw") if w.winner == -1 else t("win_blue" if w.winner == 0 else "win_red")
                page.status.setText(text)
                restyle(page.status, "statusDraw" if w.winner == -1 else "status")
        else:
            page.status.setText(t(f"mode_{s.mode}"))
            restyle(page.status, "status")
        left = max(0, w.options.time_limit - w.tick) // TICK_HZ
        page.clock.setText(f"{t('time')}: {left // 60}:{left % 60:02d}")
        colors = TEAM_COLORS.get(self.ctx.theme, TEAM_COLORS["dark"])
        rows = []
        for tank in w.tanks:
            if tank.id in s.humans:
                name = t("you") if s.mode != "hotseat" else t("player1" if s.humans[tank.id] == 0 else "player2")
            elif s.human_team is not None and tank.team == s.human_team:
                name = t("ally")
            else:
                name = t("blue" if tank.team == 0 else "red") if s.mode == "watch" else t("enemy")
            hearts = "●" * tank.lives + "○" * (3 - tank.lives)
            ready = "" if tank.reload == 0 else f" · {t('reload')} {round(100 * (1 - tank.reload / RELOAD))}%"
            rows.append(f"<span style='color:{colors[tank.team]}'>■</span> <b>{name}</b> "
                        f"<span style='color:#ff6b6b'>{hearts}</span>{ready}<br>"
                        f"<span style='font-size:12px'>{t('hits')} {tank.hits} · "
                        f"{t('misses')} {w.misses.get(tank.id, 0)}</span>")
        page.tanks.setText("<br>".join(rows))

    def shutdown(self):
        """Закрытие окна: таймер стоп (потоков у игры нет)."""
        self.timer.stop()
        self.session = None
        self.play.arena.session = None

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(980, 700)


__all__ = ["GameWidget", "QFrame"]
