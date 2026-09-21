"""画像の検証、識別、EXIF補正、平均色による縮小。"""

import hashlib
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import MAX_GRID_CELLS, Settings


def grid_size(width: int, height: int, columns: int) -> tuple[int, int]:
    if min(width, height, columns) <= 0:
        raise ValueError("画像寸法と列数は1以上が必要です。")
    # 整数演算で四捨五入。banker's roundingを避け、最低1行を確保する。
    return columns, max(1, (2 * height * columns + width) // (2 * width))


def load_mosaic(path: Path, settings: Settings) -> tuple[Image.Image, dict]:
    settings.validate()
    path = Path(path)
    if not path.is_file():
        raise ValueError("入力画像が見つかりません。--image のファイルを確認してください。")
    if path.suffix.lower() not in (".jpg", ".jpeg"):
        raise ValueError("画像には .jpg または .jpeg を指定してください。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            # 同じファイルハンドルからハッシュと画像を読み、取り違えを抑える。
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
                byte_size = source.tell()
                source.seek(0)
                with Image.open(source) as image:
                    if image.format != "JPEG":
                        raise ValueError("入力の実体がJPEG画像ではありません。")
                    original_size = image.size
                    orientation = image.getexif().get(274, 1)
                    oriented_size = (
                        original_size[::-1] if orientation in (5, 6, 7, 8) else original_size
                    )
                    size = grid_size(*oriented_size, settings.columns)
                    count = size[0] * size[1]
                    if count > MAX_GRID_CELLS:
                        raise ValueError(
                            f"処理用セル数{count:,}マスは上限{MAX_GRID_CELLS:,}マスを超えます。"
                            "--columns を小さくしてください。付箋枚数上限とは別の制限です。"
                        )
                    rgb = ImageOps.exif_transpose(image).convert("RGB")
                    mosaic = rgb.resize(size, Image.Resampling.BOX)
        return mosaic, {
            "filename": path.name,
            "sha256": digest,
            "bytes": byte_size,
            "original_size": list(original_size),
            "oriented_size": list(oriented_size),
        }
    except (
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError(
            "JPEG画像を読み込めません。破損・権限・画像サイズを確認してください。"
        ) from error
