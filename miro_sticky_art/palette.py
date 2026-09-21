"""APIの色名と比較用sRGBを分離して管理する。

2026-09-21確認。RGBはRESTで保証された測色値ではなく、公式Web SDK資料の
fillColorからリンクされた色見本のHEX値。
https://developers.miro.com/docs/websdk-reference-sticky-note
各色の参照先: https://www.color-hex.com/color/{HEX（#なし）}
RESTのenumも確認済み:
https://developers.miro.com/reference/create-sticky-note-item-1
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PaletteColor:
    name: str
    hex: str

    @property
    def rgb(self) -> tuple[int, int, int]:
        return tuple(int(self.hex[i : i + 2], 16) for i in (1, 3, 5))


# この順序が同点時の優先順位。変更時には再開用の変換バージョンも更新する。
PALETTE = tuple(
    PaletteColor(name, value)
    for name, value in (
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
    )
)
COLORS_BY_NAME = {color.name: color for color in PALETTE}
