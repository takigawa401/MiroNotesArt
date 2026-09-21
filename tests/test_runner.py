from unittest.mock import Mock

import pytest
from test_artifacts import mixed_plan

from miro_sticky_art.api import APIError, UnknownResult
from miro_sticky_art.runner import upload
from miro_sticky_art.state import StateError, StateStore


def test_upload_skips_gray_preserves_order_and_reports_actual_total(tmp_path):
    store = StateStore.create(tmp_path / "state.json", mixed_plan())
    client = Mock()
    client.create_note.side_effect = ["red-id", "blue-id"]
    progress = []
    upload(store, client, progress.append)
    assert [
        (c.args[1].row, c.args[1].col, c.args[1].color) for c in client.create_note.call_args_list
    ] == [
        (0, 1, "red"),
        (1, 0, "blue"),
    ]
    assert progress == ["作成済み 0/2 枚", "作成済み 1/2 枚", "作成済み 2/2 枚"]


def test_sparse_resume_does_not_recreate_successful_notes(tmp_path):
    plan = mixed_plan()
    store = StateStore.create(tmp_path / "state.json", plan)
    client = Mock()
    client.create_note.side_effect = ["red-id", APIError("HTTP 401")]
    with pytest.raises(APIError):
        upload(store, client)
    client = Mock()
    client.create_note.return_value = "blue-id"
    upload(StateStore.load(store.path, plan), client)
    client.create_note.assert_called_once()
    note = client.create_note.call_args.args[1]
    assert (note.row, note.col, note.color) == (1, 0, "blue")


def test_unknown_resolves_by_original_coordinates_not_list_index(tmp_path):
    plan = mixed_plan()
    store = StateStore.create(tmp_path / "state.json", plan)
    client = Mock()
    client.create_note.side_effect = ["red-id", UnknownResult("結果不明")]
    with pytest.raises(UnknownResult):
        upload(store, client)
    loaded = StateStore.load(store.path, plan)
    client.reset_mock()
    with pytest.raises(StateError, match="結果不明"):
        upload(loaded, client)
    client.create_note.assert_not_called()
    with pytest.raises(StateError):
        loaded.resolve(0, 0, "gray-id")
    loaded.resolve(1, 0, "found-blue-id")
    upload(StateStore.load(store.path, plan), client)
    client.create_note.assert_not_called()


def test_upload_rejects_a_plan_containing_gray_before_any_api_call(tmp_path):
    plan = mixed_plan()
    plan["notes"].insert(0, {"row": 0, "col": 0, "color": "gray", "x": -10, "y": 7})
    store = StateStore.create(tmp_path / "state.json", plan)
    client = Mock()
    client.create_note.side_effect = ["gray-id", "red-id", "blue-id"]
    with pytest.raises(StateError, match="gray"):
        upload(store, client)
    client.create_note.assert_not_called()
