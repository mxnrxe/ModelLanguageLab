"""Преобразование B внутри put(TN), ПОСЛЕ распознавания автоматом.

Никаких regex, float или готовых конвертеров систем счисления.
Fraction хранит точное значение, чтобы 1B, 01 и 1.0 имели один индекс.
"""
from fractions import Fraction

DIGITS = "0123456789abcdef"
MAX_DECIMAL_POWER = 10000


class NumericLimitError(ValueError):
    """Ограничение ресурсов реализации, не ошибка грамматики числа."""


def accumulate(text: str, base: int) -> int:
    value = 0
    for ch in text.lower():
        digit = DIGITS.index(ch)
        if digit >= base:
            raise ValueError("Цифра не принадлежит системе счисления")
        value = base * value + digit
    return value


def convert_number(buffer: str, kind: str) -> Fraction:
    if kind != "REAL":
        base = {"BIN": 2, "OCT": 8, "DEC": 10, "DEC_D": 10, "HEX": 16}[kind]
        digits = buffer if kind == "DEC" else buffer[:-1]
        return Fraction(accumulate(digits, base))
    text = buffer.lower()
    mantissa, separator, exponent = text.partition("e")
    power = 0
    if separator:
        sign = -1 if exponent.startswith("-") else 1
        exponent = exponent.lstrip("+-")
        # Ограничение проверяется до построения огромного целого порядка.
        significant = exponent.lstrip("0") or "0"
        if len(significant) > 5:
            raise NumericLimitError("Порядок превышает предел реализации 10000")
        power = sign * accumulate(significant, 10)
    integer, dot, fractional = mantissa.partition(".")
    power -= len(fractional) if dot else 0
    if abs(power) > MAX_DECIMAL_POWER:
        raise NumericLimitError("Десятичный масштаб превышает предел реализации 10000")
    value = accumulate(integer + fractional, 10)
    return Fraction(value * 10 ** power) if power >= 0 else Fraction(value, 10 ** (-power))


def display_value(value: Fraction) -> str:
    """Читаемое точное значение; у нашего языка дроби всегда конечные."""
    if value.denominator == 1:
        return str(value.numerator)
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return str(value)
    scale = max(twos, fives)
    if scale > 60:
        return str(value)
    digits = str(value.numerator * 2 ** (scale - twos) * 5 ** (scale - fives)).zfill(scale + 1)
    return digits[:-scale] + "." + digits[-scale:]
