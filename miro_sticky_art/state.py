"""送信計画と状態を保存し、安全に再開する。トークンは受け取らない。"""

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .layout import Note
from .palette import PALETTE


class StateError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value: dict) -> str:
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_json_atomic(path: Path, value: dict) -> None:
    """同じディレクトリの一時ファイルをfsyncした後に置換する。"""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def make_plan(
    image: dict,
    settings: Settings,
    board_id: str | None,
    notes: list[Note],
    columns: int,
    rows: int,
) -> dict:
    return {
        "conversion": "srgb-d65-box-de76-v1",
        "image": {key: image[key] for key in ("sha256", "bytes", "original_size", "oriented_size")},
        "settings": asdict(settings),
        "board_id": board_id,
        "columns": columns,
        "rows": rows,
        "palette": [asdict(color) for color in PALETTE],
        "notes": [asdict(note) for note in notes],
    }


class StateStore:
    def __init__(self, path: Path, data: dict):
        self.path = Path(path)
        self.data = data

    @classmethod
    def create(cls, path: Path, plan: dict):
        if path.exists():
            raise StateError("状態ファイルが既にあります。--resume で再開してください。")
        data = {
            "schema_version": 1,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "plan": plan,
            "plan_sha256": fingerprint(plan),
            "resolutions": [],
            "notes": [
                {
                    "row": note["row"],
                    "col": note["col"],
                    "status": "pending",
                    "id": None,
                    "error": None,
                }
                for note in plan["notes"]
            ],
        }
        store = cls(path, data)
        store.save()
        return store

    @classmethod
    def load(cls, path: Path, expected_plan: dict):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if data["schema_version"] != 1 or data["plan_sha256"] != fingerprint(data["plan"]):
                raise StateError("状態ファイルのバージョンまたは整合性が不正です。")
            if data["plan_sha256"] != fingerprint(expected_plan):
                raise StateError(
                    "画像・設定・ボードID・変換結果が前回と一致しません。元の条件で再開してください。"
                )
            if len(data["notes"]) != len(expected_plan["notes"]):
                raise StateError("状態ファイルの付箋数が不正です。")
            if not isinstance(data["resolutions"], list):
                raise StateError("状態ファイルの確認履歴が不正です。")
            ids = set()
            for record, note in zip(data["notes"], expected_plan["notes"], strict=True):
                if (record["row"], record["col"]) != (note["row"], note["col"]):
                    raise StateError("状態ファイルの行・列が不正です。")
                if record["status"] not in ("pending", "in_flight", "created", "unknown"):
                    raise StateError("状態ファイルのステータスが不正です。")
                item_id = record["id"]
                if record["status"] == "created":
                    if not isinstance(item_id, str) or not item_id.strip() or item_id in ids:
                        raise StateError("作成済みIDが欠落または重複しています。")
                    ids.add(item_id)
                elif item_id is not None:
                    raise StateError("未確定の付箋にIDが記録されています。")
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise StateError(
                "状態ファイルを読み込めません。正しいstate.jsonを指定してください。"
            ) from error
        store = cls(path, data)
        changed = False
        for record in data["notes"]:
            if record["status"] == "in_flight":
                record.update(status="unknown", error="送信中の中断を検出しました。結果不明です。")
                changed = True
        if changed:
            store.save()
        return store

    def save(self) -> None:
        self.data["updated_at"] = utc_now()
        try:
            write_json_atomic(self.path, self.data)
        except OSError:
            raise StateError(
                "状態を保存できないため停止しました。容量と書き込み権限を確認してください。"
                "送信中の場合は結果不明としてボードを確認してから再開してください。"
            ) from None

    def unknown_records(self) -> list[dict]:
        return [record for record in self.data["notes"] if record["status"] == "unknown"]

    def resolve(self, row: int, col: int, item_id: str | None) -> None:
        record = next((n for n in self.data["notes"] if (n["row"], n["col"]) == (row, col)), None)
        if record is None or record["status"] != "unknown":
            raise StateError("指定された行・列は結果不明の付箋ではありません。")
        if item_id is not None:
            if not item_id.strip() or any(n["id"] == item_id for n in self.data["notes"]):
                raise StateError("確認した付箋IDが空、または既に記録済みです。")
        record.update(
            status="created" if item_id is not None else "pending", id=item_id, error=None
        )
        self.data["resolutions"].append(
            {
                "row": row,
                "col": col,
                "action": "created" if item_id is not None else "absent",
                "id": item_id,
                "confirmed_at": utc_now(),
            }
        )
        self.save()
