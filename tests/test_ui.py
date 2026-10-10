"""Окно без экрана (Qt offscreen): меню, режимы, клавиши и мышь без захвата курсора, туман,
«Мысли ИИ», статистика, темы, языки, место окна, остановка за 2 секунды. Клавиши и мышь -
собранными событиями, настоящий курсор не трогается."""
import os
import time

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from game import APP_NAME, GAME_INFO, create_widget
from game.ai.net import NetPolicy
from game.core import geom
from game.ui.i18n import EN, RU


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def home(tmp_path):
    return str(tmp_path / "home")


@pytest.fixture
def win(app, home):
    from aikit.host import make_window
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=home)
    w.resize(1280, 800)
    w.show()
    yield w
    w.game.shutdown()
    w.close()


def key(view, k, press=True):
    ev = QKeyEvent(QEvent.Type.KeyPress if press else QEvent.Type.KeyRelease, k, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view, ev)


def mouse(view, kind, x, y, button=Qt.MouseButton.NoButton):
    ev = QMouseEvent(kind, QPointF(x, y), QPointF(x, y), button, button, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view, ev)


def to_screen(view, wx, wy):
    ox, oy, s = view.layout_rect()
    return ox + wx * s, oy + wy * s


def play_to_end(g, limit=4000):
    for _ in range(limit // 100):
        if g.session.over:
            break
        g.advance(100)
    assert g.session.over


def test_translations_complete():
    assert set(RU) == set(EN)


def test_models_are_networks():
    from game.ai.agents import LEVEL_NAMES, make_policy
    for lv in LEVEL_NAMES:
        assert isinstance(make_policy(lv), NetPolicy)


def test_duel_to_the_end_records_stats(app, win):
    g = win.game
    g.change("mode", "duel")
    g.change("level", "novice")
    g.change("show_thoughts", False)
    g.start_game(seed=3, realtime=False)
    assert g.current_page() == "play"
    play_to_end(g)
    e = g.ctx.stats.entry("duel/novice")
    assert e["games"] == 1 and e["wins"] + e["losses"] + e["draws"] == 1
    assert g.play.status.text() in (RU["win"], RU["loss"], RU["draw"])


def test_thoughts_keep_battle_out_of_stats(app, win):
    g = win.game
    g.change("mode", "duel")
    g.change("show_thoughts", True)
    g.start_game(seed=4, realtime=False)
    g.advance(60)
    assert any(c.thoughts for c in g.session.controllers.values())
    th = next(c.thoughts for c in g.session.controllers.values() if c.thoughts)
    assert "rays" in th and "fire_line" in th
    win.grab()                                       # «Мысли ИИ» рисуются без ошибок
    play_to_end(g)
    assert g.ctx.stats.entry("duel/medium")["games"] == 0
    g.change("show_thoughts", False)


def test_keys_drive_both_hotseat_tanks(app, win):
    g = win.game
    g.change("mode", "hotseat")
    g.start_game(seed=1, realtime=False)
    view = g.play.arena
    a, b = g.session.world.tanks
    x0, y0, bx0, by0 = a.x, a.y, b.x, b.y
    key(view, Qt.Key.Key_W)
    key(view, Qt.Key.Key_Up)
    g.advance(10)
    key(view, Qt.Key.Key_W, False)
    key(view, Qt.Key.Key_Up, False)
    assert (a.x - x0) ** 2 + (a.y - y0) ** 2 > 0.3 and (b.x - bx0) ** 2 + (b.y - by0) ** 2 > 0.3
    h0 = b.hull
    key(view, Qt.Key.Key_Right)
    g.advance(5)
    key(view, Qt.Key.Key_Right, False)
    assert b.hull != h0
    key(view, Qt.Key.Key_Space)
    g.advance(1)
    key(view, Qt.Key.Key_Space, False)
    assert a.shots == 1 and b.shots == 0
    g.advance(3)
    assert view.keys == set()


def test_mouse_aims_turret_without_capture(app, win):
    g = win.game
    g.change("mode", "duel")
    g.start_game(seed=2, realtime=False)
    view = g.play.arena
    me = g.session.world.tanks[0]
    tx, ty = me.x + 3.0, me.y + 3.0
    px, py = to_screen(view, tx, ty)
    mouse(view, QEvent.Type.MouseMove, px, py)
    assert QWidget.mouseGrabber() is None
    g.advance(60)
    want = geom.angle_of(tx - me.x, ty - me.y)
    assert abs(geom.diff(want, me.aim)) <= 2
    mouse(view, QEvent.Type.MouseButtonPress, px, py, Qt.MouseButton.LeftButton)
    g.advance(1)
    mouse(view, QEvent.Type.MouseButtonRelease, px, py, Qt.MouseButton.LeftButton)
    assert me.shots == 1
    assert QWidget.mouseGrabber() is None and view.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_fog_hides_enemy_and_watch_shows_all(app, win):
    g = win.game
    g.change("mode", "duel")
    g.change("fog", True)
    g.start_game(seed=6, realtime=False)
    s = g.session
    enemy = s.world.tanks[1]
    assert s.fog and not s.visible(enemy)            # базы не видят друг друга
    win.grab()
    g.change("mode", "watch")
    g.start_game(seed=6, realtime=False)
    assert not g.session.fog and g.session.visible(g.session.world.tanks[1])


def test_team_mode_has_ai_ally(app, win):
    g = win.game
    g.change("mode", "team")
    g.start_game(seed=8, realtime=False)
    s = g.session
    assert len(s.world.tanks) == 4 and list(s.humans) == [0]
    ally = [t for t in s.world.tanks if t.team == 0 and t.id != 0][0]
    assert ally.id in s.controllers
    play_to_end(g)
    assert g.ctx.stats.entry("team/medium")["games"] == 1


def test_watch_plays_itself(app, win):
    g = win.game
    g.change("mode", "watch")
    g.start_game(seed=9, realtime=False)
    play_to_end(g)
    assert g.play.status.text()
    assert not g.ctx.stats.data


def test_realtime_timer_runs_world(app, win):
    g = win.game
    g.change("mode", "watch")
    g.start_game(seed=10)
    end = time.time() + 5
    while g.session.world.tick < 20 and time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    assert g.session.world.tick >= 20
    g.toggle_pause()
    t0 = g.session.world.tick
    for _ in range(20):
        app.processEvents()
        time.sleep(0.005)
    assert g.session.world.tick == t0
    g.toggle_pause()


def test_theme_and_language_on_the_fly(app, win):
    g = win.game
    assert g.menu.play_button.text() == RU["play"]
    g.ctx.set_lang("en")
    assert g.menu.play_button.text() == EN["play"]
    assert win.windowTitle().startswith("Tanks")
    g.ctx.set_theme("light")
    assert g.play.arena.theme == "light"
    g.change("mode", "duel")
    g.start_game(seed=11, realtime=False)
    g.advance(30)
    img = win.grab().toImage()
    assert not img.isNull()
    g.ctx.set_lang("ru")
    g.ctx.set_theme("dark")


def test_stats_page_and_menu_sync(app, win):
    g = win.game
    g.change("level", "strong")
    assert g.menu.level_buttons["strong"].isChecked()
    assert "100" in g.menu.note.text()               # реакция сильного 100 мс
    g.show_page("stats")
    assert g.current_page() == "stats"
    assert RU["passport"] in g.stats.body.text()
    g.show_page("menu")


def test_close_stops_in_two_seconds_and_saves_window(app, home):
    from aikit.host import make_window
    w, _ = make_window(GAME_INFO, create_widget, APP_NAME, root=home)
    w.resize(1100, 760)
    w.show()
    g = w.game
    g.change("mode", "watch")
    g.start_game(seed=12)
    for _ in range(10):
        app.processEvents()
    t0 = time.time()
    w.close()
    app.processEvents()
    assert time.time() - t0 < 2.0
    assert not g.timer.isActive()
    assert os.path.exists(os.path.join(home, "window.json"))
    assert os.path.exists(os.path.join(home, "tanks", "settings.json"))
