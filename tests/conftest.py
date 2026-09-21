import pytest
import requests


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    """すべてのテストで、誤って実ボードへ接続しないようにする。"""

    def blocked(*args, **kwargs):
        raise AssertionError("テストからの外部通信は禁止です")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)


@pytest.fixture
def legacy_state():
    """初回版の形式を再現した匿名の1マス分の状態。認証情報は含めない。"""
    from dataclasses import asdict

    from miro_sticky_art.config import Settings
    from miro_sticky_art.palette import PALETTE
    from miro_sticky_art.state import fingerprint

    plan = {
        "conversion": "srgb-d65-box-de76-v1",
        "image": {
            "sha256": "0" * 64,
            "bytes": 100,
            "original_size": [1, 1],
            "oriented_size": [1, 1],
        },
        "settings": asdict(Settings(columns=1)),
        "board_id": "board",
        "columns": 1,
        "rows": 1,
        "palette": [asdict(color) for color in PALETTE],
        "notes": [{"row": 0, "col": 0, "color": "gray", "x": 0.0, "y": 0.0}],
    }
    return {
        "schema_version": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "plan": plan,
        "plan_sha256": fingerprint(plan),
        "resolutions": [],
        "notes": [{"row": 0, "col": 0, "status": "in_flight", "id": None, "error": None}],
    }
