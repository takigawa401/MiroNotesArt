"""sRGB → XYZ(D65) → CIELAB、ΔE76。ディザリングは行わない。"""

from functools import lru_cache
from math import sqrt

from .palette import PALETTE, PaletteColor


@lru_cache(maxsize=8192)
def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    def linear(channel: int) -> float:
        value = channel / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = map(linear, rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883
    delta = 6 / 29

    def f(value: float) -> float:
        return value ** (1 / 3) if value > delta**3 else value / (3 * delta**2) + 4 / 29

    fx, fy, fz = map(f, (x, y, z))
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e76(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


def nearest_color(
    rgb: tuple[int, int, int],
    palette: tuple[PaletteColor, ...] = PALETTE,
) -> PaletteColor:
    lab = rgb_to_lab(rgb)
    # minは最初の最小値を返すので、同点でも常にパレット順になる。
    return min(palette, key=lambda color: delta_e76(lab, rgb_to_lab(color.rgb)))
