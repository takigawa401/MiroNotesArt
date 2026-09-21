import json
from unittest.mock import Mock

import pytest
from test_state import plan_for

from miro_sticky_art.api import UnknownResult
from miro_sticky_art.locking import run_lock
from miro_sticky_art.runner import upload
from miro_sticky_art.state import StateError, StateStore


def test_record_existing_id_and_confirm_absence_are_audited(tmp_path):
    store = StateStore.create(tmp_path / "state.json", plan_for())
    store.data["notes"][0]["status"] = "unknown"
    store.data["notes"][1]["status"] = "unknown"
    store.save()
    store.resolve(0, 0, "found-id")
    store.resolve(0, 1, None)
    assert store.data["notes"][0]["status"] == "created"
    assert store.data["notes"][1]["status"] == "pending"
    assert [a["action"] for a in store.data["resolutions"]] == ["created", "absent"]
    client = Mock()
    client.create_note.side_effect = ["id-1", "id-2", "id-3"]
    upload(StateStore.load(store.path, plan_for()), client)
    assert client.create_note.call_count == 3


def test_resolution_only_applies_to_unknown_and_rejects_duplicate_id(tmp_path):
    store = StateStore.create(tmp_path / "state.json", plan_for())
    with pytest.raises(StateError):
        store.resolve(0, 0, "id-0")
    with pytest.raises(StateError):
        store.resolve(99, 99, "id-0")
    store.data["notes"][0].update(status="created", id="already")
    store.data["notes"][1]["status"] = "unknown"
    with pytest.raises(StateError):
        store.resolve(0, 1, "already")
    with pytest.raises(StateError):
        store.resolve(0, 1, "")


def test_exclusive_lock_and_release_even_on_exception(tmp_path):
    with run_lock(tmp_path):
        assert (tmp_path / ".run.lock").is_file()
        with pytest.raises(StateError, match="ロック"):
            with run_lock(tmp_path):
                pytest.fail("同時取得を許可してはいけない")
    assert not (tmp_path / ".run.lock").exists()
    with pytest.raises(RuntimeError):
        with run_lock(tmp_path):
            raise RuntimeError()
    assert not (tmp_path / ".run.lock").exists()


def test_failure_to_save_before_post_prevents_network_call(tmp_path, monkeypatch):
    store = StateStore.create(tmp_path / "state.json", plan_for())
    client = Mock()
    monkeypatch.setattr(store, "save", Mock(side_effect=StateError("保存できません")))
    with pytest.raises(StateError):
        upload(store, client)
    client.create_note.assert_not_called()


def test_failure_to_save_success_leaves_recoverable_unknown(tmp_path, monkeypatch):
    store = StateStore.create(tmp_path / "state.json", plan_for())
    save = store.save

    def fail_after_success():
        if store.data["notes"][0]["status"] == "created":
            raise StateError("disk full")
        save()

    monkeypatch.setattr(store, "save", fail_after_success)
    client = Mock()
    client.create_note.return_value = "created-remotely"
    with pytest.raises(StateError):
        upload(store, client)
    resumed = StateStore.load(store.path, plan_for())
    assert resumed.data["notes"][0]["status"] == "unknown"
    assert client.create_note.call_count == 1


def test_keyboard_interrupt_is_recorded_as_unknown(tmp_path):
    store = StateStore.create(tmp_path / "state.json", plan_for())
    client = Mock()
    client.create_note.side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        upload(store, client)
    assert StateStore.load(store.path, plan_for()).data["notes"][0]["status"] == "unknown"


def test_failed_atomic_replace_preserves_previous_file(tmp_path, monkeypatch):
    store = StateStore.create(tmp_path / "state.json", plan_for())
    original = store.path.read_bytes()
    monkeypatch.setattr("miro_sticky_art.state.os.replace", Mock(side_effect=OSError("disk full")))
    store.data["notes"][0]["status"] = "unknown"
    with pytest.raises(StateError):
        store.save()
    assert store.path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_cli_resolution_does_not_call_api_or_require_token(tmp_path, monkeypatch):
    from PIL import Image

    from miro_sticky_art import cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MIRO_ACCESS_TOKEN", "test-placeholder")
    monkeypatch.setenv("MIRO_BOARD_ID", "board")
    image = tmp_path / "sample.jpg"
    Image.new("RGB", (2, 2)).save(image)
    client = Mock()
    client.create_note.side_effect = UnknownResult("結果不明")
    factory = Mock(return_value=client)
    monkeypatch.setattr(cli, "MiroClient", factory)
    args = ["--image", str(image), "--columns", "1"]
    assert cli.main(args) == 3
    state = next(tmp_path.glob("output/*/state.json"))
    factory.reset_mock()
    monkeypatch.delenv("MIRO_ACCESS_TOKEN")
    assert cli.main([*args, "--resume", str(state), "--resolve-created", "0,0=found-id"]) == 0
    factory.assert_not_called()
    assert json.loads(state.read_text(encoding="utf-8"))["notes"][0]["id"] == "found-id"


@pytest.mark.parametrize("resolution", ["-1,0", "0", "a,b", "0,0=", "0,0=x=y"])
def test_invalid_resolution_syntax(resolution):
    from miro_sticky_art.cli import parse_resolution

    with pytest.raises(ValueError):
        parse_resolution(resolution, created=True)
