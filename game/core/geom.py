"""Углы и направления.

Угол - целое число от 0 до ANG-1 (полоборота = ANG/2), а не число с плавающей точкой:
синусы и косинусы берутся из таблицы, округлённой до 12 знаков. Тогда шаг мира - только
сложение и умножение, одинаковые на любом процессоре, и повтор боя по записи сходится до
бита. Ось x - вправо, y - вниз (как на экране), угол растёт по часовой стрелке.
"""
import math

ANG = 720                      # единиц на полный оборот: одна единица - полградуса
HALF = ANG // 2
COS = tuple(round(math.cos(2 * math.pi * i / ANG), 12) for i in range(ANG))
SIN = tuple(round(math.sin(2 * math.pi * i / ANG), 12) for i in range(ANG))


def norm(a):
    return a % ANG


def diff(a, b):
    """Кратчайший поворот от b к a: от -HALF до HALF-1."""
    return (a - b + HALF) % ANG - HALF


def angle_of(dx, dy):
    """Угол направления (dx, dy) в единицах ANG. Только для решений (ИИ, мышь): в сам
    шаг мира попадает целое число из действия."""
    if dx == 0 and dy == 0:
        return 0
    return round(math.atan2(dy, dx) * ANG / (2 * math.pi)) % ANG


def to_radians(a):
    return 2 * math.pi * a / ANG


def degrees(a):
    return a * 360 / ANG
