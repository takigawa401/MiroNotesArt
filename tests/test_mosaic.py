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


def test_gray_cells_leave_holes_without_changing_coordinates():
    image = Image.new("RGB", (2, 2))
    image.putdata([COLORS_BY_NAME[name].rgb for name in ("gray", "red", "blue", "gray")])
    notes = build_notes(image, Settings(columns=2, note_size=20, gap=5, origin_x=-10, origin_y=7))
    assert [(n.row, n.col, n.color, n.x, n.y) for n in notes] == [
        (0, 1, "red", 15, 7),
        (1, 0, "blue", -10, 32),
    ]


@pytest.mark.parametrize(
    "names, expected_columns",
    [
        (("gray", "gray", "gray"), []),
        (("red", "gray", "blue"), [0, 2]),
        (("red", "blue", "yellow"), [0, 1, 2]),
    ],
)
def test_gray_filter_preserves_original_column_numbers(names, expected_columns):
    image = Image.new("RGB", (3, 1))
    image.putdata([COLORS_BY_NAME[name].rgb for name in names])
    notes = build_notes(image, Settings(columns=3))
    assert [note.col for note in notes] == expected_columns
    assert all(note.color != "gray" for note in notes)


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


def test_total_cells_may_exceed_note_limit_when_gray_is_skipped(tmp_path):
    path = tmp_path / "gray.jpg"
    Image.new("RGB", (2, 2), COLORS_BY_NAME["gray"].rgb).save(path)
    settings = Settings(columns=2, max_notes=1)
    mosaic, _ = load_mosaic(path, settings)
    assert mosaic.size == (2, 2)
    assert build_notes(mosaic, settings) == []


@pytest.mark.parametrize(
    "names, allowed",
    [
        (("gray", "red", "blue", "gray"), True),
        (("red", "red", "blue", "gray"), False),
    ],
)
def test_note_limit_counts_only_non_gray_cells(names, allowed):
    image = Image.new("RGB", (2, 2))
    image.putdata([COLORS_BY_NAME[name].rgb for name in names])
    settings = Settings(columns=2, max_notes=2)
    if allowed:
        assert len(build_notes(image, settings)) == 2
    else:
        with pytest.raises(ValueError, match="gray除外後.*3.*2.*--columns"):
            build_notes(image, settings)


def test_processing_cell_limit_checked_before_image_decode(tmp_path, monkeypatch):
    path = tmp_path / "gray.jpg"
    Image.new("RGB", (2, 2), "white").save(path)

    def forbidden(*args, **kwargs):
        pytest.fail("処理用セル数上限は画像展開より前に検査する")

    monkeypatch.setattr("miro_sticky_art.imaging.ImageOps.exif_transpose", forbidden)
    with pytest.raises(ValueError, match="処理用セル数.*1,000,000.*--columns"):
        load_mosaic(path, Settings(columns=1001, max_notes=2_000_000))


def test_processing_cell_limit_allows_exact_boundary(tmp_path):
    path = tmp_path / "gray.jpg"
    Image.new("RGB", (2, 2), "white").save(path)
    mosaic, _ = load_mosaic(path, Settings(columns=1000, max_notes=1))
    assert mosaic.size == (1000, 1000)


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
