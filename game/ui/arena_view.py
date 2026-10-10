"""Поле боя: клетки, танки, снаряды, вспышки, туман войны и «Мысли ИИ». Всё рисуется кодом.

Управление (без захвата курсора: ни grabMouse, ни скрытия, ни зажима мыши):
- игрок 1: W/S вперёд и назад, A/D поворот, Q/E башня, пробел - огонь; башня идёт за мышью,
  когда мышь двигали над полем, левая кнопка - огонь; в одиночных режимах стрелки - тоже езда;
- игрок 2 («вдвоём»): стрелки, башня «,» и «.», огонь Enter.
"""
import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from aikit import theme
from game.core import geom, vision
from game.core.arena import BRICK, BUSH, STEEL
from game.core.world import RELOAD, SHELL_R, TANK_R, TURRET_TURN, Action
from game.ui.session import aim_action

TEAM_COLORS = {"dark": ("#4f8fe6", "#e2584c"), "light": ("#2f6fd0", "#cf3f33")}
FIELD = {
    "dark": {"floor": "#2a303a", "grid": "#323946", "steel": "#7d8794", "steel_edge": "#a9b2be",
             "brick": "#9a5a3c", "brick_line": "#6e3d27", "bush": "#2f7d45", "bush_dark": "#1f5a31",
             "shell": "#ffd25a", "fog": (12, 14, 20, 150), "wreck": "#4a4f58"},
    "light": {"floor": "#e9edf3", "grid": "#d6dce6", "steel": "#8a95a6", "steel_edge": "#b7c0cd",
              "brick": "#c27548", "brick_line": "#97512d", "bush": "#5aa86a", "bush_dark": "#3f8a50",
              "shell": "#e0a400", "fog": (40, 48, 62, 120), "wreck": "#9aa1ab"},
}
P1_KEYS = {Qt.Key.Key_W: ("move", 1), Qt.Key.Key_S: ("move", -1), Qt.Key.Key_A: ("turn", -1),
           Qt.Key.Key_D: ("turn", 1), Qt.Key.Key_Q: ("turret", -1), Qt.Key.Key_E: ("turret", 1),
           Qt.Key.Key_Space: ("fire", 1)}
P2_KEYS = {Qt.Key.Key_Up: ("move", 1), Qt.Key.Key_Down: ("move", -1), Qt.Key.Key_Left: ("turn", -1),
           Qt.Key.Key_Right: ("turn", 1), Qt.Key.Key_Comma: ("turret", -1), Qt.Key.Key_Period: ("turret", 1),
           Qt.Key.Key_Return: ("fire", 1), Qt.Key.Key_Enter: ("fire", 1)}
FOG_RAYS = 240


class ArenaView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = None
        self.theme = "dark"
        self.lang = "ru"
        self.show_thoughts = False
        self.keys = set()
        self.mouse = None              # (x, y) в клетках
        self.mouse_time = 0.0
        self.mouse_fire = False
        self.effects = []              # [вид, x, y, возраст]
        self.labels = {}
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)    # мышь только читается; курсор не захватывается
        self.setMinimumSize(480, 320)

    # --- геометрия ---

    def layout_rect(self):
        if self.session is None:
            return 0.0, 0.0, 1.0
        a = self.session.world.arena
        s = min(self.width() / a.W, self.height() / a.H)
        return (self.width() - s * a.W) / 2, (self.height() - s * a.H) / 2, s

    def to_world(self, px, py):
        ox, oy, s = self.layout_rect()
        return (px - ox) / s, (py - oy) / s

    # --- ввод ---

    def keyPressEvent(self, e):
        if e.isAutoRepeat():
            return
        self.keys.add(e.key())
        if e.key() in (Qt.Key.Key_Q, Qt.Key.Key_E):
            self.mouse_time = 0.0       # клавиши башни главнее мыши
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.isAutoRepeat():
            return
        self.keys.discard(e.key())
        super().keyReleaseEvent(e)

    def focusOutEvent(self, e):
        self.keys.clear()               # отпущенная вне окна клавиша не залипает
        self.mouse_fire = False
        super().focusOutEvent(e)

    def mouseMoveEvent(self, e):
        self.mouse = self.to_world(e.position().x(), e.position().y())
        self.mouse_time = time.monotonic()

    def mousePressEvent(self, e):
        self.setFocus()
        if e.button() == Qt.MouseButton.LeftButton:
            self.mouse_fire = True
            self.mouse = self.to_world(e.position().x(), e.position().y())
            self.mouse_time = time.monotonic()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.mouse_fire = False

    def leaveEvent(self, e):
        self.mouse_fire = False
        super().leaveEvent(e)

    def human_actions(self):
        """Действия людей из нажатых клавиш и мыши: {номер игрока: Action}."""
        s = self.session
        if s is None or not s.humans:
            return {}
        solo = len(s.humans) == 1
        out = {}
        for player, table in ((0, P1_KEYS), (1, P2_KEYS)):
            tank = s.human_tank(player)
            if tank is None:
                continue
            v = {"move": 0, "turn": 0, "turret": 0, "fire": 0}
            tables = [table] + ([P2_KEYS] if solo and player == 0 else [])
            for tb in tables:
                for key, (what, d) in tb.items():
                    if key in self.keys:
                        if solo and tb is P2_KEYS and what in ("turret", "fire"):
                            continue
                        v[what] = max(-1, min(1, v[what] + d)) if what != "fire" else 1
            act = Action(v["move"], v["turn"], v["turret"] * TURRET_TURN, bool(v["fire"]))
            if player == 0:
                if v["turret"] == 0 and self.mouse is not None and time.monotonic() - self.mouse_time < 3.0:
                    want = geom.angle_of(self.mouse[0] - tank.x, self.mouse[1] - tank.y)
                    act = aim_action(tank, want, act.move, act.turn)
                    act.fire = bool(v["fire"]) or self.mouse_fire
                elif self.mouse_fire:
                    act.fire = True
            out[player] = act
        return out

    # --- вспышки ---

    def add_events(self, events):
        w = self.session.world
        shells = {s.id: s for s in w.shells}
        for e in events:
            if e[0] == "shot":
                t = w.tanks[e[1]]
                self.effects.append(["flash", t.x + geom.COS[t.aim] * 0.55, t.y + geom.SIN[t.aim] * 0.55, 0])
            elif e[0] == "hit":
                t = w.tanks[e[2]]
                self.effects.append(["boom", t.x, t.y, 0])
            elif e[0] == "brick":
                self.effects.append(["dust", e[1] + 0.5, e[2] + 0.5, 0])
            elif e[0] == "gone" and e[2] in ("wall", "shell"):
                s = shells.get(e[1])
                if s is not None:
                    self.effects.append(["spark", s.x, s.y, 0])

    def age_effects(self):
        for fx in self.effects:
            fx[3] += 1
        self.effects = [fx for fx in self.effects if fx[3] < 14]

    # --- рисование ---

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = theme.palette(self.theme)
        p.fillRect(self.rect(), QColor(pal["bg"]))
        s = self.session
        if s is None:
            p.end()
            return
        ox, oy, sc = self.layout_rect()
        p.translate(ox, oy)
        p.scale(sc, sc)
        f = FIELD.get(self.theme, FIELD["dark"])
        self.draw_tiles(p, s.world.arena, f, ground=True)
        for t in s.world.tanks:
            if not t.alive:
                self.draw_wreck(p, t, f)
        for t in s.world.tanks:
            if t.alive and s.visible(t):
                self.draw_tank(p, t)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(f["shell"]))
        for sh in s.world.shells:
            if s.shell_visible(sh):
                p.drawEllipse(QPointF(sh.x, sh.y), SHELL_R * 1.4, SHELL_R * 1.4)
        self.draw_tiles(p, s.world.arena, f, ground=False)    # кусты поверх танков
        self.draw_effects(p, f)
        if s.fog:
            self.draw_fog(p, s, f, sc)
        if self.show_thoughts:
            self.draw_thoughts(p, s)
        p.end()

    def draw_tiles(self, p, a, f, ground):
        p.setPen(Qt.PenStyle.NoPen)
        if ground:
            p.fillRect(QRectF(0, 0, a.W, a.H), QColor(f["floor"]))
            pen = QPen(QColor(f["grid"]))
            pen.setWidthF(0.03)
            p.setPen(pen)
            for c in range(a.W + 1):
                p.drawLine(QPointF(c, 0), QPointF(c, a.H))
            for r in range(a.H + 1):
                p.drawLine(QPointF(0, r), QPointF(a.W, r))
            p.setPen(Qt.PenStyle.NoPen)
        for r in range(a.H):
            for c in range(a.W):
                k = a.tiles[r * a.W + c]
                if ground and k == STEEL:
                    p.setBrush(QColor(f["steel"]))
                    p.drawRect(QRectF(c, r, 1, 1))
                    p.setBrush(QColor(f["steel_edge"]))
                    p.drawRect(QRectF(c + 0.12, r + 0.12, 0.76, 0.18))
                elif ground and k == BRICK:
                    p.setBrush(QColor(f["brick"]))
                    p.drawRect(QRectF(c, r, 1, 1))
                    pen = QPen(QColor(f["brick_line"]))
                    pen.setWidthF(0.06)
                    p.setPen(pen)
                    for y in (0.33, 0.66):
                        p.drawLine(QPointF(c, r + y), QPointF(c + 1, r + y))
                    for x, y0, y1 in ((0.5, 0, 0.33), (0.25, 0.33, 0.66), (0.75, 0.33, 0.66), (0.5, 0.66, 1)):
                        p.drawLine(QPointF(c + x, r + y0), QPointF(c + x, r + y1))
                    p.setPen(Qt.PenStyle.NoPen)
                elif not ground and k == BUSH:
                    for i, (dx, dy, rr) in enumerate(((0.3, 0.3, 0.32), (0.72, 0.32, 0.3), (0.28, 0.72, 0.3),
                                                      (0.7, 0.7, 0.33), (0.5, 0.5, 0.3))):
                        p.setBrush(QColor(f["bush_dark"] if i % 2 else f["bush"]))
                        p.drawEllipse(QPointF(c + dx, r + dy), rr, rr)

    def draw_tank(self, p, t):
        colors = TEAM_COLORS.get(self.theme, TEAM_COLORS["dark"])
        body = QColor(colors[t.team])
        dark = body.darker(150)
        p.save()
        p.translate(t.x, t.y)
        p.rotate(geom.degrees(t.hull))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(dark)
        p.drawRoundedRect(QRectF(-0.42, -0.4, 0.84, 0.18), 0.05, 0.05)       # гусеницы
        p.drawRoundedRect(QRectF(-0.42, 0.22, 0.84, 0.18), 0.05, 0.05)
        p.setBrush(body)
        p.drawRoundedRect(QRectF(-0.36, -0.27, 0.72, 0.54), 0.08, 0.08)
        p.restore()
        p.save()
        p.translate(t.x, t.y)
        p.rotate(geom.degrees(t.aim))
        p.setBrush(dark)
        p.drawRoundedRect(QRectF(0.05, -0.055, 0.5, 0.11), 0.03, 0.03)       # ствол
        p.setBrush(body.lighter(115))
        p.drawEllipse(QPointF(0, 0), 0.19, 0.19)
        p.restore()
        # жизни и перезарядка над танком
        for i in range(3):
            p.setBrush(QColor("#ff6b6b") if i < t.lives else QColor(0, 0, 0, 70))
            p.drawEllipse(QPointF(t.x - 0.2 + i * 0.2, t.y - 0.62), 0.07, 0.07)
        if t.reload > 0:
            p.setBrush(QColor(0, 0, 0, 80))
            p.drawRect(QRectF(t.x - 0.3, t.y + 0.52, 0.6, 0.07))
            p.setBrush(QColor("#ffd25a"))
            p.drawRect(QRectF(t.x - 0.3, t.y + 0.52, 0.6 * (1 - t.reload / RELOAD), 0.07))

    def draw_wreck(self, p, t, f):
        p.save()
        p.translate(t.x, t.y)
        p.rotate(geom.degrees(t.hull))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(f["wreck"]))
        p.drawRoundedRect(QRectF(-0.4, -0.36, 0.8, 0.72), 0.1, 0.1)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawEllipse(QPointF(0, 0), 0.2, 0.2)
        p.restore()

    def draw_effects(self, p, f):
        p.setPen(Qt.PenStyle.NoPen)
        for kind, x, y, age in self.effects:
            k = age / 14
            if kind == "flash":
                p.setBrush(QColor(255, 220, 120, int(220 * (1 - k))))
                p.drawEllipse(QPointF(x, y), 0.18 + 0.1 * k, 0.18 + 0.1 * k)
            elif kind == "boom":
                p.setBrush(QColor(255, 140, 60, int(200 * (1 - k))))
                p.drawEllipse(QPointF(x, y), 0.3 + 0.6 * k, 0.3 + 0.6 * k)
            elif kind == "dust":
                p.setBrush(QColor(170, 110, 80, int(180 * (1 - k))))
                p.drawEllipse(QPointF(x, y), 0.3 + 0.4 * k, 0.3 + 0.4 * k)
            else:
                p.setBrush(QColor(255, 230, 150, int(200 * (1 - k))))
                p.drawEllipse(QPointF(x, y), 0.1 + 0.15 * k, 0.1 + 0.15 * k)

    def visibility_polygons(self, s):
        """Многоугольники того, что видит команда человека: лучи до непрозрачных клеток."""
        out = []
        a = s.world.arena
        for t in s.world.tanks:
            if t.team != s.human_team or not t.alive:
                continue
            pts = []
            for i in range(FOG_RAYS):
                ang = 2 * math.pi * i / FOG_RAYS
                ca, sa = math.cos(ang), math.sin(ang)
                d, k = vision.cast_ray(a, t.x, t.y, ca, sa, 40.0)
                if k == BUSH:
                    d = min(d + vision.BUSH_SEE * 0.5, d + 1.0)
                elif k:
                    d += 0.05
                pts.append(QPointF(t.x + ca * d, t.y + sa * d))
            out.append(QPolygonF(pts))
        return out

    def draw_fog(self, p, s, f, sc):
        a = s.world.arena
        k = 16                          # точек тумана на клетку: край тени без ступенек
        w, h = a.W * k, a.H * k
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor(*f["fog"]))
        q = QPainter(img)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.scale(k, k)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QBrush(Qt.GlobalColor.black))
        for poly in self.visibility_polygons(s):
            q.drawPolygon(poly)
        q.end()
        p.drawImage(QRectF(0, 0, a.W, a.H), img)

    def draw_thoughts(self, p, s):
        for tid, c in s.controllers.items():
            th = c.thoughts
            t = s.world.tanks[tid]
            if not th or not t.alive:
                continue
            col = QColor(TEAM_COLORS.get(self.theme, TEAM_COLORS["dark"])[t.team])
            pen = QPen(col)
            pen.setWidthF(0.03)
            for ang, d, kind, enemy in th.get("rays", ()):
                pen.setColor(QColor(255, 80, 80, 220) if enemy is not None else QColor(col.red(), col.green(), col.blue(), 90))
                p.setPen(pen)
                dd = enemy if enemy is not None else d
                p.drawLine(QPointF(t.x, t.y), QPointF(t.x + geom.COS[ang] * dd, t.y + geom.SIN[ang] * dd))
            dash = QPen(QColor("#ffd25a"))
            dash.setWidthF(0.05)
            dash.setStyle(Qt.PenStyle.DashLine)
            p.setPen(dash)
            for x0, y0, x1, y1 in th.get("fire_line", ()):
                p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
            tgt = th.get("target")
            if tgt is not None:
                ring = QPen(QColor(255, 80, 80) if th.get("target_visible") else QColor(255, 170, 60))
                ring.setWidthF(0.07)
                if not th.get("target_visible"):
                    ring.setStyle(Qt.PenStyle.DotLine)
                p.setPen(ring)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(*tgt), 0.5, 0.5)
                if not th.get("target_visible"):
                    font = p.font()
                    font.setPointSizeF(0.5)
                    p.setFont(font)
                    p.drawText(QRectF(tgt[0] - 0.5, tgt[1] - 0.5, 1, 1), Qt.AlignmentFlag.AlignCenter, "?")
            lead = th.get("lead")
            if lead is not None:
                cross = QPen(QColor(255, 80, 80))
                cross.setWidthF(0.05)
                p.setPen(cross)
                p.drawLine(QPointF(lead[0] - 0.2, lead[1]), QPointF(lead[0] + 0.2, lead[1]))
                p.drawLine(QPointF(lead[0], lead[1] - 0.2), QPointF(lead[0], lead[1] + 0.2))
            cover = th.get("cover")
            if cover is not None:
                cp = QPen(QColor(90, 200, 120))
                cp.setWidthF(0.05)
                p.setPen(cp)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(QRectF(cover[0] - 0.45, cover[1] - 0.45, 0.9, 0.9))
            path = th.get("path")
            if path is not None:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(col.red(), col.green(), col.blue(), 160))
                p.drawEllipse(QPointF(*path), 0.1, 0.1)


