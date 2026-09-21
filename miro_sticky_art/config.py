"""画像・配置・通信設定と入力検証。"""

from dataclasses import dataclass
from math import isfinite

FLOAT_FIELDS = ("note_size", "gap", "origin_x", "origin_y", "interval", "timeout")


@dataclass(frozen=True)
class Settings:
    columns: int = 40
    note_size: float = 200
    gap: float = 0
    origin_x: float = 0
    origin_y: float = 0
    max_notes: int = 2500
    interval: float = 0.1
    max_retries: int = 5
    timeout: float = 30

    def __post_init__(self):
        # 200と200.0など、同じ数値はJSON上でも同じ表現にして再開比較を安定させる。
        for name in FLOAT_FIELDS:
            object.__setattr__(self, name, float(getattr(self, name)))

    def validate(self) -> None:
        for name in ("columns", "max_notes", "max_retries"):
            value = getattr(self, name)
            minimum = 0 if name == "max_retries" else 1
            if type(value) is not int or value < minimum:
                raise ValueError(f"--{name.replace('_', '-')} は{minimum}以上の整数が必要です。")
        for name in FLOAT_FIELDS:
            value = getattr(self, name)
            if not isfinite(value):
                raise ValueError(f"--{name.replace('_', '-')} は有限の数値が必要です。")
            if name in ("note_size", "timeout") and value <= 0:
                raise ValueError(f"--{name.replace('_', '-')} は0より大きい値が必要です。")
            if name in ("gap", "interval") and value < 0:
                raise ValueError(f"--{name.replace('_', '-')} は0以上の値が必要です。")
