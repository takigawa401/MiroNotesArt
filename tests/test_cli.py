import json
from unittest.mock import Mock

import pytest
from PIL import Image

from miro_sticky_art import cli
from miro_sticky_art.palette import COLORS_BY_NAME


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MIRO_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("MIRO_BOARD_ID", raising=False)
    image = tmp_path / "sample.jpg"
    Image.new("RGB", (20, 10), COLORS_BY_NAME["red"].rgb).save(image)
    return image


def test_dry_run_without_credentials_never_constructs_api_client(environment, monkeypatch, capsys):
    factory = Mock(side_effect=AssertionError("dry-runでAPIクライアントを作成しない"))
    monkeypatch.setattr(cli, "MiroClient", factory)
    assert cli.main(["--image", str(environment), "--columns", "4", "--dry-run"]) == 0
    factory.assert_not_called()
    output = next(environment.parent.glob("output/*/layout.json"))
    plan = json.loads(output.read_text(encoding="utf-8"))
    assert (plan["columns"], plan["rows"], len(plan["notes"])) == (4, 2, 8)
    assert plan["board_id"] is None
    assert not (output.parent / "state.json").exists()
    preview = Image.open(output.parent / "preview.png")
    assert preview.size == (64, 32)
    for note in plan["notes"]:
        assert preview.getpixel((note["col"] * 16, note["row"] * 16)) == (
            *COLORS_BY_NAME[note["color"]].rgb,
            255,
        )
    displayed = capsys.readouterr().out
    assert "4列 × 2行" in displayed and "8枚" in displayed
    assert "red: 8" in displayed


def test_each_run_gets_its_own_directory(environment):
    args = ["--image", str(environment), "--columns", "1", "--dry-run", "--output-dir", "art"]
    assert cli.main(args) == cli.main(args) == 0
    assert len(list(environment.parent.glob("art/*/layout.json"))) == 2


@pytest.mark.parametrize(
    "extra",
    [
        ["--columns", "0"],
        ["--columns", "bad"],
        ["--gap", "-1"],
        ["--origin-x", "nan"],
        ["--note-size", "0"],
        ["--max-notes", "1"],
        ["--interval", "-1"],
        ["--timeout", "0"],
    ],
)
def test_invalid_configuration_does_not_call_api(environment, extra, monkeypatch, capsys):
    client = Mock()
    monkeypatch.setattr(cli, "MiroClient", client)
    assert cli.main(["--image", str(environment), *extra]) == 2
    assert "エラー" in capsys.readouterr().err
    client.assert_not_called()


def test_real_run_requires_credentials(environment, capsys):
    assert cli.main(["--image", str(environment), "--columns", "1"]) == 2
    assert "MIRO_" in capsys.readouterr().err


def test_env_file_environment_priority_and_board_argument(environment, monkeypatch, capsys):
    (environment.parent / ".env").write_text(
        "MIRO_ACCESS_TOKEN=dotenv-placeholder\nMIRO_BOARD_ID=dotenv-board\n", encoding="utf-8"
    )
    monkeypatch.setenv("MIRO_ACCESS_TOKEN", "environment-placeholder")
    monkeypatch.setenv("MIRO_BOARD_ID", "environment-board")
    client = Mock()
    client.create_note.return_value = "item-1"
    factory = Mock(return_value=client)
    monkeypatch.setattr(cli, "MiroClient", factory)
    assert (
        cli.main(["--image", str(environment), "--columns", "1", "--board-id", "argument-board"])
        == 0
    )
    assert factory.call_args.args[0] == "environment-placeholder"
    assert client.create_note.call_args.args[0] == "argument-board"
    state_path = next(environment.parent.glob("output/*/state.json"))
    state_text = state_path.read_text(encoding="utf-8")
    assert "placeholder" not in state_text
    assert "placeholder" not in capsys.readouterr().out
    client.reset_mock()
    assert (
        cli.main(
            [
                "--image",
                str(environment),
                "--columns",
                "1",
                "--board-id",
                "argument-board",
                "--resume",
                str(state_path),
            ]
        )
        == 0
    )
    client.create_note.assert_not_called()


def test_dotenv_used_when_environment_absent(environment, monkeypatch):
    (environment.parent / ".env").write_text(
        "MIRO_ACCESS_TOKEN=local-placeholder\nMIRO_BOARD_ID=local-board\n", encoding="utf-8"
    )
    client = Mock()
    client.create_note.return_value = "item-1"
    factory = Mock(return_value=client)
    monkeypatch.setattr(cli, "MiroClient", factory)
    assert cli.main(["--image", str(environment), "--columns", "1"]) == 0
    assert factory.call_args.args[0] == "local-placeholder"
    assert client.create_note.call_args.args[0] == "local-board"


def test_unknown_result_saved_and_described(environment, monkeypatch, capsys):
    from miro_sticky_art.api import UnknownResult

    monkeypatch.setenv("MIRO_ACCESS_TOKEN", "test-placeholder")
    monkeypatch.setenv("MIRO_BOARD_ID", "board")
    client = Mock()
    client.create_note.side_effect = UnknownResult("結果不明")
    monkeypatch.setattr(cli, "MiroClient", Mock(return_value=client))
    assert cli.main(["--image", str(environment), "--columns", "1"]) == 3
    state_path = next(environment.parent.glob("output/*/state.json"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["notes"][0]["status"] == "unknown"
    assert "結果不明" in capsys.readouterr().err


@pytest.mark.parametrize("invalid", ["日本語の仮の値", "invalid\x00value", "invalid\x7fvalue"])
def test_invalid_token_stops_before_client_creation(environment, monkeypatch, capsys, invalid):
    monkeypatch.setattr(cli, "credentials", lambda board: ("board", invalid))
    factory = Mock()
    monkeypatch.setattr(cli, "MiroClient", factory)
    assert cli.main(["--image", str(environment), "--columns", "1"]) == 2
    factory.assert_not_called()
    assert invalid not in capsys.readouterr().err


def test_resume_accepts_explicit_defaults_as_same_numeric_settings(environment, monkeypatch):
    monkeypatch.setenv("MIRO_ACCESS_TOKEN", "test-placeholder")
    monkeypatch.setenv("MIRO_BOARD_ID", "board")
    client = Mock()
    client.create_note.return_value = "item-1"
    monkeypatch.setattr(cli, "MiroClient", Mock(return_value=client))
    args = ["--image", str(environment), "--columns", "1"]
    assert cli.main(args) == 0
    state = next(environment.parent.glob("output/*/state.json"))
    client.reset_mock()
    assert (
        cli.main(
            [
                *args,
                "--resume",
                str(state),
                "--note-size",
                "200",
                "--gap",
                "0",
                "--origin-x",
                "0",
                "--origin-y",
                "0",
                "--timeout",
                "30",
            ]
        )
        == 0
    )
    client.create_note.assert_not_called()


@pytest.mark.parametrize("dry_run", [False, True])
def test_note_limit_stops_before_output_and_network(environment, monkeypatch, dry_run):
    factory = Mock()
    monkeypatch.setattr(cli, "MiroClient", factory)
    args = ["--image", str(environment), "--columns", "4", "--max-notes", "7"]
    assert cli.main(args + (["--dry-run"] if dry_run else [])) == 2
    assert not (environment.parent / "output").exists()
    factory.assert_not_called()


def test_resume_note_limit_counts_successes_as_well_as_pending(environment, monkeypatch, capsys):
    from miro_sticky_art.api import APIError

    monkeypatch.setenv("MIRO_ACCESS_TOKEN", "test-placeholder")
    monkeypatch.setenv("MIRO_BOARD_ID", "board")
    client = Mock()
    client.create_note.side_effect = ["first-id", APIError("HTTP 401")]
    factory = Mock(return_value=client)
    monkeypatch.setattr(cli, "MiroClient", factory)
    args = ["--image", str(environment), "--columns", "2"]
    assert cli.main(args) == 2
    state = next(environment.parent.glob("output/*/state.json"))
    before = state.read_bytes()
    capsys.readouterr()
    factory.reset_mock()
    assert cli.main([*args, "--resume", str(state), "--max-notes", "1"]) == 2
    assert "gray除外後の付箋2枚" in capsys.readouterr().err
    assert state.read_bytes() == before
    factory.assert_not_called()


@pytest.mark.parametrize("dry_run", [False, True])
def test_all_gray_succeeds_without_credentials_or_state(environment, monkeypatch, capsys, dry_run):
    Image.new("RGB", (20, 10), COLORS_BY_NAME["gray"].rgb).save(environment)
    factory = Mock(side_effect=AssertionError("全grayでAPIクライアントを作成しない"))
    monkeypatch.setattr(cli, "MiroClient", factory)
    args = ["--image", str(environment), "--columns", "4", "--max-notes", "1"]
    assert cli.main(args + (["--dry-run"] if dry_run else [])) == 0
    factory.assert_not_called()
    layout = next(environment.parent.glob("output/*/layout.json"))
    assert (layout.parent / "preview.png").is_file()
    assert not (layout.parent / "state.json").exists()
    assert not (layout.parent / ".run.lock").exists()
    data = json.loads(layout.read_text(encoding="utf-8"))
    assert data["notes"] == [] and len(data["cells"]) == 8
    assert "作成予定: 0枚" in capsys.readouterr().out


@pytest.mark.parametrize("all_gray", [False, True])
def test_legacy_resume_stops_before_api_or_state_change(
    environment, monkeypatch, capsys, legacy_state, all_gray
):
    if all_gray:
        Image.new("RGB", (20, 10), "white").save(environment)
    path = environment.parent / "state.json"
    path.write_text(json.dumps(legacy_state), encoding="utf-8")
    before = path.read_bytes()
    factory = Mock()
    monkeypatch.setattr(cli, "MiroClient", factory)
    assert cli.main(["--image", str(environment), "--columns", "1", "--resume", str(path)]) == 2
    assert "旧形式" in capsys.readouterr().err
    assert path.read_bytes() == before
    assert not (path.parent / ".run.lock").exists()
    factory.assert_not_called()
