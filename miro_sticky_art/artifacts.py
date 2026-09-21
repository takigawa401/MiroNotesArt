"""送信に使う配置データから、PNGとJSONを生成する。"""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from PIL import Image

from .palette import COLORS_BY_NAME, PALETTE
from .state import write_json_atomic


def create_run_dir(output_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = Path(output_dir) / f"{stamp}-{uuid4().hex[:8]}"
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def save_artifacts(directory: Path, plan: dict) -> None:
    write_json_atomic(directory / "layout.json", plan)
    image = Image.new("RGB", (plan["columns"], plan["rows"]))
    for note in plan["notes"]:
        image.putpixel((note["col"], note["row"]), COLORS_BY_NAME[note["color"]].rgb)
    scale = max(1, min(16, 2048 // max(image.size)))
    image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST).save(
        directory / "preview.png"
    )


def print_summary(plan: dict) -> None:
    counts = Counter(note["color"] for note in plan["notes"])
    print(f"{plan['columns']}列 × {plan['rows']}行、付箋の総数: {len(plan['notes'])}枚")
    print("色別の枚数: " + ", ".join(f"{c.name}: {counts[c.name]}" for c in PALETTE))
