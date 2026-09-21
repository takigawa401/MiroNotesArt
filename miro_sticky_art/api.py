"""Miro REST v2の逐次送信。POSTの結果不明時には自動再送しない。"""

import math
import time
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

from .layout import Note


class APIError(RuntimeError):
    """作成拒否が確定したエラー（次回の明示的再開は可能）。"""


class UnknownResult(RuntimeError):
    """Miro側で作成されたか判断できないエラー。"""


def _number(value) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def retry_delay(headers, attempt: int, now: float) -> float:
    """指数バックオフ、Retry-After、UNIX秒のResetの最大値を使う。"""
    waits = [float(2 ** min(attempt, 6))]
    retry_after = headers.get("Retry-After")
    seconds = _number(retry_after)
    if seconds is None and retry_after:
        try:
            seconds = parsedate_to_datetime(retry_after).timestamp() - now
        except (ValueError, TypeError, OverflowError):
            pass
    if seconds is not None and seconds >= 0:
        waits.append(seconds)
    reset = _number(headers.get("X-RateLimit-Reset"))
    if reset is not None:
        waits.append(max(0, reset - now))
    return max(waits)


class MiroClient:
    # Create sticky note = Level 2 = 100 credits（2026-09-21確認）。
    # https://developers.miro.com/reference/rate-limiting
    def __init__(
        self,
        token: str,
        *,
        session=None,
        interval=0.1,
        max_retries=5,
        timeout=30,
        sleep=time.sleep,
        clock=time.time,
        report=lambda message: None,
    ):
        self._session = session if session is not None else requests.Session()
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self.interval = interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._sleep = sleep
        self._clock = clock
        self._report = report
        self._next_request_at = 0.0

    def close(self):
        self._session.close()

    def _wait(self, seconds):
        if seconds > 0:
            if seconds >= 1:
                self._report(f"レート制限等により{seconds:.1f}秒待機します（Ctrl+Cで中断可）。")
            self._sleep(seconds)

    def create_note(self, board_id: str, note: Note, note_size: float) -> str:
        url = f"https://api.miro.com/v2/boards/{quote(board_id, safe='')}/sticky_notes"
        payload = {
            "data": {"content": "", "shape": "square"},
            "style": {"fillColor": note.color},
            "position": {"x": note.x, "y": note.y, "origin": "center"},
            "geometry": {"width": note_size},
        }
        for attempt in range(self.max_retries + 1):
            self._wait(max(0, self._next_request_at - self._clock()))
            try:
                result = self._session.post(
                    url,
                    json=payload,
                    headers=self._headers,
                    timeout=(min(10, self.timeout), self.timeout),
                    allow_redirects=False,
                )
            except requests.RequestException:
                # 例外本文にはURL/認証情報等が入り得るため、表示・保存しない。
                raise UnknownResult(
                    "通信失敗: 作成されたか判断できないため結果不明です。"
                ) from None

            now = self._clock()
            self._next_request_at = now + self.interval
            remaining = _number(result.headers.get("X-RateLimit-Remaining"))
            reset = _number(result.headers.get("X-RateLimit-Reset"))
            if remaining is not None and remaining < 100 and reset is not None:
                self._next_request_at = max(self._next_request_at, reset)

            status = result.status_code
            if status == 429:
                if attempt == self.max_retries:
                    raise APIError(
                        "HTTP 429: レート制限の再試行上限に達しました。"
                        "時間を置いて再開してください。"
                    )
                delay = retry_delay(result.headers, attempt, now)
                self._next_request_at = max(self._next_request_at, now + delay)
                self._report(f"HTTP 429: 再試行 {attempt + 1}/{self.max_retries}")
                continue
            if status == 201:
                try:
                    item_id = result.json().get("id")
                except (ValueError, AttributeError):
                    item_id = None
                if not isinstance(item_id, str) or not item_id.strip():
                    raise UnknownResult("作成応答に有効なIDがないため結果不明です。")
                return item_id
            if 400 <= status < 500 and status != 408:
                causes = {
                    400: "入力値が拒否されました。付箋の幅・座標・配置データを確認してください。",
                    401: "認証に失敗しました。アクセストークンと有効期限を確認してください。",
                    403: (
                        "権限がありません。boards:write と"
                        "チームへのインストールを確認してください。"
                    ),
                    404: (
                        "ボードが見つからないかアクセスできません。"
                        "ボードIDと対象チームを確認してください。"
                    ),
                    422: "入力値を処理できません。付箋の幅・座標を確認してください。",
                }
                raise APIError(
                    f"HTTP {status}: "
                    + causes.get(status, "要求が拒否されました。設定を確認してください。")
                )
            # 5xx/408/3xx/想定外の2xxも、作成後の障害の可能性がある。
            raise UnknownResult(
                f"HTTP {status}: 作成を確定できないため結果不明です。自動再送しません。"
            )
        raise AssertionError("到達しない分岐")
