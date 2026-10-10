"""Иконка программы: синий танк на тёмном поле, нарисованный кодом."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPixmap


def render(size=256):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, size, size), size * 0.18, size * 0.18)
    p.setClipPath(clip)
    p.fillRect(QRectF(0, 0, size, size), QColor("#2a303a"))
    p.scale(size / 10, size / 10)
    p.translate(5, 5.3)
    p.rotate(-35)
    p.setPen(Qt.PenStyle.NoPen)
    body = QColor("#4f8fe6")
    p.setBrush(body.darker(150))
    p.drawRoundedRect(QRectF(-3.4, -3.1, 6.8, 1.4), 0.4, 0.4)
    p.drawRoundedRect(QRectF(-3.4, 1.7, 6.8, 1.4), 0.4, 0.4)
    p.setBrush(body)
    p.drawRoundedRect(QRectF(-2.9, -2.1, 5.8, 4.2), 0.6, 0.6)
    p.setBrush(body.darker(150))
    p.drawRoundedRect(QRectF(0.4, -0.45, 4.4, 0.9), 0.25, 0.25)
    p.setBrush(body.lighter(120))
    p.drawEllipse(QPointF(0, 0), 1.5, 1.5)
    p.end()
    return img


def app_icon():
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(render(s)))
    return icon
