import pytest

from miro_sticky_art.colors import delta_e76, nearest_color, rgb_to_lab
from miro_sticky_art.palette import PALETTE, PaletteColor


def test_official_palette_names_and_reference_values():
    assert [(c.name, c.hex) for c in PALETTE] == [
        ("gray", "#f5f6f8"),
        ("light_yellow", "#fff9b1"),
        ("yellow", "#f5d128"),
        ("orange", "#ff9d48"),
        ("light_green", "#d5f692"),
        ("green", "#c9df56"),
        ("dark_green", "#93d275"),
        ("cyan", "#67c6c0"),
        ("light_pink", "#ffcee0"),
        ("pink", "#ea94bb"),
        ("violet", "#c6a2d2"),
        ("red", "#f0939d"),
        ("light_blue", "#a6ccf5"),
        ("blue", "#6cd8fa"),
        ("dark_blue", "#9ea9ff"),
        ("black", "#000000"),
    ]


@pytest.mark.parametrize("color", PALETTE, ids=lambda c: c.name)
def test_palette_color_maps_to_itself(color):
    assert nearest_color(color.rgb).name == color.name


@pytest.mark.parametrize(
    "rgb, expected",
    [
        ((0, 0, 0), (0, 0, 0)),
        ((255, 255, 255), (100, 0, 0)),
        ((255, 0, 0), (53.2408, 80.0925, 67.2032)),
    ],
)
def test_lab_reference_points(rgb, expected):
    assert rgb_to_lab(rgb) == pytest.approx(expected, abs=0.0002)


def test_delta_e76_and_deterministic_tie():
    assert delta_e76((0, 1, 2), (3, 5, 2)) == 5
    first = PaletteColor("first", "#000000")
    second = PaletteColor("second", "#000000")
    assert nearest_color((10, 10, 10), (first, second)) == first
