import json

from PIL import Image

from miro_sticky_art.artifacts import print_summary, save_artifacts
from miro_sticky_art.config import Settings
from miro_sticky_art.layout import build_notes
from miro_sticky_art.palette import COLORS_BY_NAME
from miro_sticky_art.state import make_plan


def mixed_plan(names=("gray", "red", "blue", "gray"), settings=None):
    image = Image.new("RGB", (2, 2))
    image.putdata([COLORS_BY_NAME[name].rgb for name in names])
    settings = settings or Settings(columns=2, note_size=20, gap=5, origin_x=-10, origin_y=7)
    return make_plan(
        {"sha256": "a" * 64, "bytes": 100, "original_size": [2, 2], "oriented_size": [2, 2]},
        settings,
        "board",
        build_notes(image, settings),
        2,
        2,
    )


def test_preview_uses_transparency_for_gray_and_nearest_neighbor(tmp_path):
    save_artifacts(tmp_path, mixed_plan())
    with Image.open(tmp_path / "preview.png") as preview:
        assert preview.mode == "RGBA"
        assert preview.size == (32, 32)
        assert preview.getpixel((0, 0)) == (*COLORS_BY_NAME["gray"].rgb, 0)
        assert preview.getpixel((31, 31)) == (*COLORS_BY_NAME["gray"].rgb, 0)
        for x, y in ((16, 0), (31, 15)):
            assert preview.getpixel((x, y)) == (*COLORS_BY_NAME["red"].rgb, 255)
        for x, y in ((0, 16), (15, 31)):
            assert preview.getpixel((x, y)) == (*COLORS_BY_NAME["blue"].rgb, 255)


def test_json_records_all_cells_and_separates_the_creation_plan(tmp_path):
    plan = mixed_plan()
    save_artifacts(tmp_path, plan)
    data = json.loads((tmp_path / "layout.json").read_text(encoding="utf-8"))
    assert data["notes"] == plan["notes"]
    assert data["cells"] == [
        {"row": 0, "col": 0, "color": "gray", "x": -10, "y": 7, "action": "skip"},
        {"row": 0, "col": 1, "color": "red", "x": 15, "y": 7, "action": "create"},
        {"row": 1, "col": 0, "color": "blue", "x": -10, "y": 32, "action": "create"},
        {"row": 1, "col": 1, "color": "gray", "x": 15, "y": 32, "action": "skip"},
    ]
    assert "cells" not in plan  # 全格子を1枚ごとにstateへ保存しない。


def test_all_gray_produces_a_fully_transparent_preview_and_skipped_cells(tmp_path):
    plan = mixed_plan(("gray",) * 4)
    save_artifacts(tmp_path, plan)
    with Image.open(tmp_path / "preview.png") as preview:
        assert preview.mode == "RGBA"
        assert preview.getchannel("A").getextrema() == (0, 0)
    data = json.loads((tmp_path / "layout.json").read_text(encoding="utf-8"))
    assert data["notes"] == []
    assert len(data["cells"]) == 4
    assert all(cell["action"] == "skip" for cell in data["cells"])


def test_summary_distinguishes_grid_skipped_and_created_counts(capsys):
    print_summary(mixed_plan())
    output = capsys.readouterr().out
    assert "総マス数: 4" in output
    assert "gray除外: 2" in output
    assert "作成予定: 2枚" in output
    assert "gray: 0" in output
    assert "red: 1" in output and "blue: 1" in output


def test_summary_of_all_gray_is_zero_notes(capsys):
    print_summary(mixed_plan(("gray",) * 4))
    output = capsys.readouterr().out
    assert "総マス数: 4" in output
    assert "gray除外: 4" in output
    assert "作成予定: 0枚" in output
