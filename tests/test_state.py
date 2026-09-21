import copy
import json
from dataclasses import replace
from unittest.mock import Mock

import pytest
from PIL import Image

from miro_sticky_art.api import APIError, UnknownResult
from miro_sticky_art.config import Settings
from miro_sticky_art.layout import build_notes
from miro_sticky_art.runner import upload
from miro_sticky_art.state import StateError, StateStore, make_plan


def plan_for(settings=None, board="board"):
    settings = settings or Settings(columns=2)
    notes = build_notes(Image.new("RGB", (2, 2)), settings)
    return make_plan(
        {"sha256": "a" * 64, "bytes": 100, "original_size": [2, 2], "oriented_size": [2, 2]},
        settings,
        board,
        notes,
        2,
        2,
    )


def test_success_is_persisted_and_resume_skips_created_notes(tmp_path):
    path = tmp_path / "state.json"
    plan = plan_for()
    store = StateStore.create(path, plan)
    client = Mock()
    client.create_note.side_effect = ["id-0", APIError("HTTP 401: 認証")]
    with pytest.raises(APIError):
        upload(store, client)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["notes"][0] == {
        "row": 0,
        "col": 0,
        "status": "created",
        "id": "id-0",
        "error": None,
    }
    assert saved["notes"][1]["status"] == "pending"
    resumed = StateStore.load(path, plan)
    client = Mock()
    client.create_note.side_effect = ["id-1", "id-2", "id-3"]
    upload(resumed, client)
    assert [(call.args[1].row, call.args[1].col) for call in client.create_note.call_args_list] == [
        (0, 1),
        (1, 0),
        (1, 1),
    ]
    assert len({note["id"] for note in resumed.data["notes"]}) == 4
    upload(StateStore.load(path, plan), client)
    assert client.create_note.call_count == 3


def test_in_flight_is_written_before_post_and_unknown_blocks_resume(tmp_path):
    path = tmp_path / "state.json"
    plan = plan_for()
    store = StateStore.create(path, plan)

    def fail(*args):
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["notes"][0]["status"] == "in_flight"
        raise UnknownResult("結果不明")

    client = Mock()
    client.create_note.side_effect = fail
    with pytest.raises(UnknownResult):
        upload(store, client)
    assert StateStore.load(path, plan).data["notes"][0]["status"] == "unknown"
    client.reset_mock()
    with pytest.raises(StateError, match="結果不明"):
        upload(StateStore.load(path, plan), client)
    client.create_note.assert_not_called()


def test_process_crash_in_flight_becomes_unknown(tmp_path):
    store = StateStore.create(tmp_path / "state.json", plan_for())
    store.data["notes"][0]["status"] = "in_flight"
    store.save()
    loaded = StateStore.load(store.path, plan_for())
    assert loaded.data["notes"][0]["status"] == "unknown"
    assert json.loads(store.path.read_text(encoding="utf-8"))["notes"][0]["status"] == "unknown"


@pytest.mark.parametrize("change", ["image", "board", "settings", "notes"])
def test_resume_requires_matching_image_settings_board_and_plan(tmp_path, change):
    plan = plan_for()
    store = StateStore.create(tmp_path / "state.json", plan)
    changed = copy.deepcopy(plan)
    if change == "image":
        changed["image"]["sha256"] = "b" * 64
    elif change == "board":
        changed["board_id"] = "another"
    elif change == "settings":
        changed = plan_for(replace(Settings(columns=2), gap=5))
    else:
        changed["notes"][0]["color"] = "red"
    with pytest.raises(StateError, match="一致"):
        StateStore.load(store.path, changed)


@pytest.mark.parametrize("damage", ["id", "count", "position", "hash", "status", "duplicate"])
def test_corrupt_state_is_rejected(tmp_path, damage):
    store = StateStore.create(tmp_path / "state.json", plan_for())
    data = store.data
    if damage == "id":
        data["notes"][0]["status"] = "created"
    elif damage == "count":
        data["notes"].pop()
    elif damage == "position":
        data["notes"][0]["row"] = 99
    elif damage == "hash":
        data["plan"]["board_id"] = "tampered"
    elif damage == "status":
        data["notes"][0]["status"] = "typo"
    else:
        for note in data["notes"][:2]:
            note.update(status="created", id="duplicate")
    store.save()
    with pytest.raises(StateError):
        StateStore.load(store.path, plan_for())
