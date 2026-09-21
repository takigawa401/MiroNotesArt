from dataclasses import replace

import pytest
from PIL import Image

from miro_sticky_art.config import Settings
from miro_sticky_art.imaging import grid_size, load_mosaic
from miro_sticky_art.layout import build_notes
from miro_sticky_art.palette import COLORS_BY_NAME


@pytest.mark.parametrize(
    "size, columns, expected",
    [
        ((600, 400), 40, (40, 27)),
        ((400, 600), 40, (40, 60)),
        ((1000, 1), 40, (40, 1)),
        ((4, 1), 2, (2, 1)),
        ((4, 5), 2, (2, 3)),
    ],
)
def test_aspect_ratio_and_half_up_rounding(size, columns, expected):
    assert grid_size(*size, columns) == expected


def test_exif_rotation_rgb_and_jpeg_extension(tmp_path):
    path = tmp_path / "rotated.JPEG"
    image = Image.new("RGB", (6, 4), "red")
    for y in range(4):
        for x in range(3, 6):
            image.putpixel((x, y), (0, 0, 255))
    exif = Image.Exif()
    exif[274] = 6  # 時計回り90度: 左の赤は上になる。
    image.save(path, quality=100, subsampling=0, exif=exif)
    mosaic, info = load_mosaic(path, Settings(columns=2))
    assert mosaic.mode == "RGB"
    assert mosaic.size == (2, 3)
    assert info["oriented_size"] == [4, 6]
    assert mosaic.getpixel((0, 0))[0] > 240
    assert mosaic.getpixel((0, 2))[2] > 240
    assert len(info["sha256"]) == 64


def test_box_is_average_and_grayscale_becomes_rgb(tmp_path):
    path = tmp_path / "average.jpg"
    image = Image.new("L", (2, 2))
    image.putdata([0, 255, 255, 0])
    image.save(path, quality=100)
    mosaic, _ = load_mosaic(path, Settings(columns=1))
    assert mosaic.mode == "RGB"
    assert mosaic.getpixel((0, 0)) == pytest.approx((128, 128, 128), abs=1)


def test_four_notes_in_row_major_order_with_correct_colors_and_positions():
    image = Image.new("RGB", (2, 2))
    names = ["red", "blue", "yellow", "black"]
    image.putdata([COLORS_BY_NAME[name].rgb for name in names])
    notes = build_notes(image, Settings(columns=2, note_size=20, gap=5, origin_x=-10, origin_y=7))
    assert [(n.row, n.col, n.color, n.x, n.y) for n in notes] == [
        (0, 0, "red", -10, 7),
        (0, 1, "blue", 15, 7),
        (1, 0, "yellow", -10, 32),
        (1, 1, "black", 15, 32),
    ]


@pytest.mark.parametrize(
    "changes",
    [
        {"columns": 0},
        {"columns": -1},
        {"columns": 2.5},
        {"note_size": 0},
        {"note_size": float("nan")},
        {"gap": -1},
        {"origin_x": float("inf")},
        {"max_notes": 0},
        {"interval": -1},
        {"timeout": 0},
        {"max_retries": -1},
    ],
)
def test_invalid_settings(changes):
    with pytest.raises(ValueError):
        replace(Settings(), **changes).validate()


def test_note_limit_checked_before_resize(tmp_path, monkeypatch):
    path = tmp_path / "tall.jpg"
    Image.new("RGB", (10, 100)).save(path)

    def forbidden(*args, **kwargs):
        pytest.fail("枚数上限の超過は縮小処理の前に検出する")

    monkeypatch.setattr(Image.Image, "resize", forbidden)
    with pytest.raises(ValueError, match="--columns"):
        load_mosaic(path, Settings(columns=40))


@pytest.mark.parametrize(
    "name, content",
    [
        ("bad.jpg", b"not a jpeg"),
        ("bad.png", b"not a jpeg"),
    ],
)
def test_invalid_image(tmp_path, name, content):
    path = tmp_path / name
    path.write_bytes(content)
    with pytest.raises(ValueError, match="画像|JPEG"):
        load_mosaic(path, Settings())


def test_disguised_png_and_missing_file(tmp_path):
    path = tmp_path / "fake.jpg"
    Image.new("RGB", (2, 2)).save(path, format="PNG")
    with pytest.raises(ValueError, match="JPEG"):
        load_mosaic(path, Settings())
    with pytest.raises(ValueError, match="見つかりません"):
        load_mosaic(tmp_path / "missing.jpg", Settings())
