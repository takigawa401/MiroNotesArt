import pytest
import requests


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    """すべてのテストで、誤って実ボードへ接続しないようにする。"""

    def blocked(*args, **kwargs):
        raise AssertionError("テストからの外部通信は禁止です")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
