import json
from email.utils import formatdate
from unittest.mock import Mock

import pytest
import requests

from miro_sticky_art.api import APIError, MiroClient, UnknownResult, retry_delay
from miro_sticky_art.layout import Note


def response(status=201, body=None, headers=None):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps({"id": "item-1"} if body is None else body).encode()
    result.headers.update(headers or {})
    return result


def client_for(*responses, **options):
    session = Mock()
    session.post.side_effect = responses
    sleep = Mock()
    client = MiroClient(
        "test-only-not-a-token",
        session=session,
        sleep=sleep,
        clock=lambda: 1000.0,
        interval=0,
        **options,
    )
    return client, session, sleep


NOTE = Note(0, 0, "yellow", -100, 200)


def test_request_uses_official_payload_and_only_width():
    client, session, _ = client_for(response())
    assert client.create_note("board/=", NOTE, 200) == "item-1"
    args, kwargs = session.post.call_args
    assert args == ("https://api.miro.com/v2/boards/board%2F%3D/sticky_notes",)
    assert kwargs["json"] == {
        "data": {"content": "", "shape": "square"},
        "style": {"fillColor": "yellow"},
        "position": {"x": -100, "y": 200, "origin": "center"},
        "geometry": {"width": 200},
    }
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] == (10, 30)


@pytest.mark.parametrize(
    "headers, expected",
    [
        ({"Retry-After": "5"}, 5),
        ({"Retry-After": formatdate(1007, usegmt=True)}, 7),
        ({"X-RateLimit-Reset": "1009"}, 9),
        ({"Retry-After": "2", "X-RateLimit-Reset": "1008"}, 8),
        ({"Retry-After": "bad", "X-RateLimit-Reset": "NaN"}, 4),
        ({"Retry-After": "-1"}, 4),
    ],
)
def test_retry_wait_information(headers, expected):
    assert retry_delay(response(429, headers=headers).headers, 2, 1000) == expected


def test_429_retries_and_stops_at_limit():
    client, session, sleep = client_for(
        response(429, headers={"Retry-After": "3"}), response(), max_retries=2
    )
    assert client.create_note("board", NOTE, 200) == "item-1"
    sleep.assert_called_once_with(3)
    assert session.post.call_count == 2
    client, session, _ = client_for(*[response(429)] * 3, max_retries=2)
    with pytest.raises(APIError, match="429"):
        client.create_note("board", NOTE, 200)
    assert session.post.call_count == 3


@pytest.mark.parametrize(
    "status, cause",
    [
        (400, "入力"),
        (401, "認証"),
        (403, "権限"),
        (404, "ボード"),
        (422, "入力"),
    ],
)
def test_known_rejections_do_not_retry_or_echo_body(status, cause):
    client, session, _ = client_for(response(status, {"message": "sensitive-response"}))
    with pytest.raises(APIError, match=cause) as error:
        client.create_note("board", NOTE, 200)
    assert "sensitive-response" not in str(error.value)
    assert session.post.call_count == 1


@pytest.mark.parametrize(
    "outcome",
    [
        requests.ReadTimeout("sensitive-transport-detail"),
        requests.ConnectionError("sensitive-transport-detail"),
        response(500),
        response(502),
        response(408),
        response(302),
        response(201, {}),
        response(201, {"id": None}),
    ],
)
def test_uncertain_result_is_never_automatically_retried(outcome):
    client, session, _ = client_for(outcome)
    with pytest.raises(UnknownResult) as error:
        client.create_note("board", NOTE, 200)
    assert "sensitive" not in str(error.value)
    assert session.post.call_count == 1


def test_success_with_non_json_is_unknown():
    result = response()
    result._content = b"not json"
    client, _, _ = client_for(result)
    with pytest.raises(UnknownResult):
        client.create_note("board", NOTE, 200)


def test_remaining_credits_delay_the_next_request():
    client, _, sleep = client_for(
        response(
            headers={
                "X-RateLimit-Remaining": "50",
                "X-RateLimit-Reset": "1010",
            }
        ),
        response(),
    )
    client.create_note("board", NOTE, 200)
    client.create_note("board", NOTE, 200)
    sleep.assert_called_once_with(10)
