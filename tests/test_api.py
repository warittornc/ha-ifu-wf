"""Protocol tests using actual firmware fixtures and an in-memory HTTP transport."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.ifu_wf.api import (
    PAGE,
    STATUS,
    IfuWfAuthError,
    IfuWfClient,
    IfuWfError,
    normalize_host,
    parse_device,
    parse_status,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" 192.168.1.60 ", "192.168.1.60"),
        ("AC.Local.", "ac.local"),
        ("2001:db8::1", "2001:db8::1"),
    ],
)
def test_normalize_host(value, expected):
    assert normalize_host(value) == expected


@pytest.mark.parametrize(
    "value", ["", "http://192.168.1.60/", "user@host", "host/path", "host:80", "-host"]
)
def test_reject_non_host_input(value):
    with pytest.raises(ValueError):
        normalize_host(value)


def test_capture(state):
    assert state.device_id == "IFU-WF00112233"
    assert not state.power
    assert state.target_temperature == 25
    assert state.mode == "COOL"  # last mode is reported while OFF
    assert state.capabilities.modes == ("DRY", "COOL", "FAN", "AUTO")
    assert state.capabilities.temperatures == tuple(range(16, 32))
    assert state.capabilities.fans == ("AUTO", "LOW", "MID1", "MID2", "HI")
    assert state.capabilities.vanes[-1] == "Swing"


@pytest.mark.parametrize(
    "replacement",
    [
        "<html>Login</html>",
        "<response><m0>ON</m0></response>",
        "<!DOCTYPE response><response/>",
    ],
)
def test_invalid_status(device, replacement):
    with pytest.raises(IfuWfError):
        parse_status(replacement, device)


@pytest.mark.parametrize(
    ("before", "after"),
    [("<am3>1", "<am3>0"), ("<m4>COOL", "<m4>HEAT"), ("25.0", "25.5")],
)
def test_unavailable_or_unsupported(device, status, before, after):
    with pytest.raises(IfuWfError):
        parse_status(status.replace(before, after), device)


@pytest.mark.parametrize("flag", ["Getfspeed(", "Gettemp(", "Getmode("])
def test_truncated_page_rejected(page, flag):
    # Cut before the flag's call, which follows its function definition.
    with pytest.raises(IfuWfError):
        parse_device(page[: page.rindex(flag)])


def test_invalid_page():
    with pytest.raises(IfuWfError):
        parse_device("<html>Sign in</html>")


class Firmware:
    def __init__(self, page, status):
        self.page, self.xml = page, status
        self.pages = []
        self.calls = []
        self.http_status = 200

    @asynccontextmanager
    async def request(self, method, url, **kwargs):
        await asyncio.sleep(0)
        self.calls.append((method, url.path, kwargs))
        if method == "POST":
            data = kwargs["data"]
            labels = [
                ("ON" if data["ifu1"] == "1" else "OFF"),
                {"0": "AUTO", "1": "P1", "7": "Swing"}[data["ifu2"]],
                {"0": "AUTO", "2": "LOW", "6": "HI"}[data["ifu3"]],
                str(int(data["ifu4"]) / 10),
                {"2": "DRY", "3": "COOL", "7": "FAN", "8": "AUTO"}[data["ifu5"]],
            ]
            self.xml = (
                "<response><am3>1</am3>"
                + "".join(f"<m{i}>{v}</m{i}>" for i, v in enumerate(labels))
                + "</response>"
            )
        if url.path == PAGE:
            body = self.pages.pop(0) if self.pages and method == "GET" else self.page
        else:
            body = self.xml

        async def chunks(size):
            yield body.encode()

        response = Mock(status=self.http_status)
        response.content.iter_chunked = chunks
        yield response


async def test_real_request_shape_and_preserved_fields(page, status):
    transport = Firmware(page, status)
    client = IfuWfClient(transport, "192.168.1.60")
    result = await client.async_set(temperature=26)
    assert result.target_temperature == 26
    assert not result.power
    posts = [call for call in transport.calls if call[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][1] == PAGE
    assert posts[0][2]["data"] == {
        "ifu1": "0",
        "ifu2": "1",
        "ifu3": "2",
        "ifu4": "260",
        "ifu5": "3",
    }
    assert posts[0][2]["allow_redirects"] is False
    assert posts[0][2]["timeout"].total == 10
    assert [call[:2] for call in transport.calls] == [
        ("GET", PAGE),
        ("GET", STATUS),
        ("POST", PAGE),
        ("GET", STATUS),
    ]


async def test_polls_read_only_status_after_first_page(page, status):
    transport = Firmware(page, status)
    client = IfuWfClient(transport, "ac.local")
    for _ in range(3):
        await client.async_get_state()
    assert [call[:2] for call in transport.calls] == [
        ("GET", PAGE),
        ("GET", STATUS),
        ("GET", STATUS),
        ("GET", STATUS),
    ]


async def test_truncated_page_is_retried(page, status):
    transport = Firmware(page, status)
    transport.pages = [
        page[: page.rindex("Getfspeed(")],
        page[: page.rindex("Getmode(")],
    ]
    state = await IfuWfClient(transport, "ac.local").async_get_state()
    assert state.device_id == "IFU-WF00112233"
    assert [call[1] for call in transport.calls] == [PAGE, PAGE, PAGE, STATUS]


async def test_page_retries_are_bounded(page, status):
    transport = Firmware(page, status)
    transport.pages = [page[: page.rindex("Getfspeed(")]] * 3
    with pytest.raises(IfuWfError):
        await IfuWfClient(transport, "ac.local").async_get_state()
    assert [call[1] for call in transport.calls] == [PAGE] * 3


async def test_turn_on_keeps_last_mode(page, status):
    transport = Firmware(page, status.replace("COOL", "DRY"))
    result = await IfuWfClient(transport, "ac.local").async_set(power=True)
    post = next(call for call in transport.calls if call[0] == "POST")
    assert (post[2]["data"]["ifu1"], post[2]["data"]["ifu5"]) == ("1", "2")
    assert (result.power, result.mode) == (True, "DRY")


async def test_commands_are_serialized(page, status):
    transport = Firmware(page, status)
    client = IfuWfClient(transport, "192.168.1.60")
    await asyncio.gather(client.async_set(temperature=26), client.async_set(fan="HI"))
    result = await client.async_get_state()
    assert (result.target_temperature, result.fan) == (26, "HI")


@pytest.mark.parametrize(
    "settings",
    [
        {"mode": "HEAT"},
        {"temperature": 25.5},
        {"temperature": float("nan")},
        {"temperature": 32},
        {"fan": "QUIET"},
        {"vane": "P9"},
    ],
)
async def test_invalid_command_never_posts(page, status, settings):
    transport = Firmware(page, status)
    with pytest.raises(IfuWfError):
        await IfuWfClient(transport, "ac.local").async_set(**settings)
    assert all(call[0] == "GET" for call in transport.calls)


@pytest.mark.parametrize("code", [401, 403, 302, 500])
async def test_http_errors(page, status, code):
    transport = Firmware(page, status)
    transport.http_status = code
    with pytest.raises(IfuWfAuthError if code in (401, 403) else IfuWfError):
        await IfuWfClient(transport, "ac.local").async_get_state()


async def test_timeout():
    session = Mock()
    session.request.return_value.__aenter__ = AsyncMock(side_effect=TimeoutError)
    session.request.return_value.__aexit__ = AsyncMock()
    with pytest.raises(IfuWfError):
        await IfuWfClient(session, "ac.local").async_get_state()


async def test_credentials_apply_to_reads_and_writes(page, status):
    import base64

    transport = Firmware(page, status)
    client = IfuWfClient(transport, "ac.local", "test-user", "test-password")
    await client.async_set(temperature=26)
    expected = "Basic " + base64.b64encode(b"test-user:test-password").decode()
    assert all(
        call[2]["headers"] == {"Authorization": expected} for call in transport.calls
    )


async def test_no_credentials_omit_authentication(page, status):
    transport = Firmware(page, status)
    await IfuWfClient(transport, "ac.local").async_get_state()
    assert all(call[2]["headers"] == {} for call in transport.calls)


@pytest.mark.parametrize("indicator", ["", " "])
def test_empty_indicator_with_valid_state_stays_available(device, status, indicator):
    state = parse_status(
        status.replace("<am3>1</am3>", f"<am3>{indicator}</am3>"), device
    )
    assert state.mode == "COOL"
    assert state.target_temperature == 25


@pytest.mark.parametrize(
    ("username", "password"), [("", "secret"), ("user:name", "secret")]
)
def test_invalid_credentials_rejected_before_requests(username, password):
    session = Mock()
    with pytest.raises(IfuWfAuthError):
        IfuWfClient(session, "ac.local", username, password)
    session.request.assert_not_called()
