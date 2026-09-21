"""grayを空白にし、元の行・列を維持した付箋の配置データを生成する。"""

from dataclasses import dataclass
from math import isfinite

from PIL import Image

from .colors import nearest_color
from .config import Settings

SKIP_COLORS = ("gray",)


@dataclass(frozen=True)
class Note:
    row: int
    col: int
    color: str
    x: float
    y: float

    @property
    def key(self) -> str:
        return f"{self.row},{self.col}"


def cell_position(row: int, col: int, settings: Settings) -> tuple[float, float]:
    """付箋と空白マスで共通の、格子上の中心座標。"""
    step = settings.note_size + settings.gap
    x = settings.origin_x + col * step
    y = settings.origin_y + row * step
    if not all(map(isfinite, (x, y))):
        raise ValueError("配置座標が大きすぎます。サイズ・間隔・開始座標を小さくしてください。")
    return x, y


def build_notes(mosaic: Image.Image, settings: Settings) -> list[Note]:
    settings.validate()
    notes = []
    for row in range(mosaic.height):
        for col in range(mosaic.width):
            x, y = cell_position(row, col, settings)
            color = nearest_color(mosaic.getpixel((col, row))).name
            if color not in SKIP_COLORS:
                notes.append(Note(row, col, color, x, y))
    if len(notes) > settings.max_notes:
        raise ValueError(
            f"gray除外後の付箋{len(notes):,}枚は上限{settings.max_notes:,}枚を超えます。"
            "--columns を小さくしてください（例: --columns 20）。"
            "必要なら --max-notes で上限を変更できます。"
        )
    return notes
