"""送信に使う配置データから、PNGとJSONを生成する。"""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from PIL import Image

from .config import Settings
from .layout import cell_position
from .palette import COLORS_BY_NAME, PALETTE
from .state import write_json_atomic


def create_run_dir(output_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = Path(output_dir) / f"{stamp}-{uuid4().hex[:8]}"
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def iter_cells(plan: dict):
    """送信計画にないマスはgrayの空白。色変換は繰り返さない。"""
    notes = {(note["row"], note["col"]): note for note in plan["notes"]}
    settings = Settings(**plan["settings"])
    for row in range(plan["rows"]):
        for col in range(plan["columns"]):
            if (row, col) in notes:
                yield {**notes[row, col], "action": "create"}
            else:
                x, y = cell_position(row, col, settings)
                yield {"row": row, "col": col, "color": "gray", "x": x, "y": y, "action": "skip"}


def save_artifacts(directory: Path, plan: dict) -> None:
    write_json_atomic(directory / "layout.json", {**plan, "cells": list(iter_cells(plan))})
    image = Image.new("RGBA", (plan["columns"], plan["rows"]), (*COLORS_BY_NAME["gray"].rgb, 0))
    for note in plan["notes"]:
        image.putpixel((note["col"], note["row"]), (*COLORS_BY_NAME[note["color"]].rgb, 255))
    scale = max(1, min(16, 2048 // max(image.size)))
    image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST).save(
        directory / "preview.png"
    )


def print_summary(plan: dict) -> None:
    counts = Counter(note["color"] for note in plan["notes"])
    total = plan["columns"] * plan["rows"]
    create_count = len(plan["notes"])
    print(f"{plan['columns']}列 × {plan['rows']}行、総マス数: {total:,}")
    print(f"gray除外: {total - create_count:,}マス、作成予定: {create_count:,}枚")
    print("作成する付箋の色別枚数: " + ", ".join(f"{c.name}: {counts[c.name]}" for c in PALETTE))
