"""縮小後の1画素につき1枚、左上から行単位の配置データを生成する。"""

from dataclasses import dataclass
from math import isfinite

from PIL import Image

from .colors import nearest_color
from .config import Settings


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


def build_notes(mosaic: Image.Image, settings: Settings) -> list[Note]:
    settings.validate()
    step = settings.note_size + settings.gap
    notes = []
    for row in range(mosaic.height):
        for col in range(mosaic.width):
            x = settings.origin_x + col * step
            y = settings.origin_y + row * step
            if not all(map(isfinite, (x, y))):
                raise ValueError(
                    "配置座標が大きすぎます。サイズ・間隔・開始座標を小さくしてください。"
                )
            color = nearest_color(mosaic.getpixel((col, row))).name
            notes.append(Note(row, col, color, x, y))
    return notes
