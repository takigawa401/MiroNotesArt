"""永続化とAPI送信を調停する。APIを呼ぶ前に必ず送信中状態を保存する。"""

from .api import APIError, UnknownResult
from .layout import Note
from .state import StateError, StateStore


def upload(store: StateStore, client, report=lambda message: None) -> None:
    unknown = store.unknown_records()
    if unknown:
        positions = ", ".join(f"({n['row']},{n['col']})" for n in unknown)
        raise StateError(
            f"結果不明の付箋があります: 行,列={positions}。"
            "READMEの確認手順と --resolve-created / --resolve-absent で解決してください。"
        )
    plan = store.data["plan"]
    total = len(store.data["notes"])
    created = sum(record["status"] == "created" for record in store.data["notes"])
    report(f"作成済み {created}/{total} 枚")
    for record, data in zip(store.data["notes"], plan["notes"], strict=True):
        if record["status"] == "created":
            continue
        record.update(status="in_flight", error=None)
        store.save()
        try:
            item_id = client.create_note(
                plan["board_id"], Note(**data), plan["settings"]["note_size"]
            )
        except APIError as error:
            record.update(status="pending", error=str(error))
            store.save()
            raise
        except UnknownResult as error:
            record.update(status="unknown", error=str(error))
            store.save()
            raise
        except BaseException:
            # Ctrl+Cや予期しない例外も、POST開始後なら成功を否定できない。
            record.update(status="unknown", error="送信処理が中断されました。結果不明です。")
            store.save()
            raise
        record.update(status="created", id=item_id, error=None)
        store.save()
        created += 1
        report(f"作成済み {created}/{total} 枚")
