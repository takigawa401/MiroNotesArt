"""同じ実行記録への多重送信を防ぐロック。残留ロックは自動削除しない。"""

import json
import os
from contextlib import contextmanager
from pathlib import Path

from .state import StateError, utc_now


@contextmanager
def run_lock(directory: Path):
    path = Path(directory) / ".run.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise StateError(
            "実行記録がロックされています。同時実行を終了してください。"
            "強制終了後はREADMEに従いプロセス停止を確認して .run.lock を削除してください。"
        ) from None
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"pid": os.getpid(), "created_at": utc_now()}, output)
        yield
    finally:
        path.unlink(missing_ok=True)
