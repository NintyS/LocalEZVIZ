"""Testy klienta HTTP. / HTTP client tests."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.ptz_proxy.api import (
    PtzProxyAuthenticationError,
    PtzProxyClient,
    PtzProxyHttpError,
    PtzProxyInvalidResponseError,
    _safe_health_payload_summary,
    normalize_base_url,
)
from custom_components.ptz_proxy.models import CameraConfig, PtzAction, PtzDirection


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("192.168.1.20:8080/", "http://192.168.1.20:8080"),
        ("http://HOST:8080/", "http://host:8080"),
        ("https://host/api/", "https://host/api"),
        ("https://host/api/health", "https://host/api"),
    ],
)
def test_normalize_base_url(raw: str, expected: str) -> None:
    """PL: Normalizacja zachowuje ścieżkę i usuwa /health. EN: Normalization preserves base paths and strips /health."""

    assert normalize_base_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "ftp://host",
        "https://admin:secret@host",
        "https://host/path?token=secret",
        "https://host/path#fragment",
        "",
    ],
)
def test_normalize_base_url_rejects_unsafe_values(raw: str) -> None:
    """PL: Niebezpieczne URL są odrzucane. EN: Unsafe URLs are rejected."""

    with pytest.raises(ValueError):
        normalize_base_url(raw)


def test_health_log_summary_redacts_unknown_fields() -> None:
    """PL: Log health pokazuje HCNet, ale ukrywa sekrety. EN: The health log shows HCNet data while hiding secrets."""

    summary = _safe_health_payload_summary(
        {
            "ok": True,
            "backend": "hcnet",
            "connected_sessions": 0,
            "api_token": "top-secret",
            "password": "camera-secret",
        }
    )

    assert '"backend": "hcnet"' in summary
    assert '"connected_sessions": 0' in summary
    assert '"other_fields_count": 2' in summary
    assert "top-secret" not in summary
    assert "camera-secret" not in summary
    assert "api_token" not in summary
    assert "password" not in summary


async def test_health_success(hass: HomeAssistant, aioclient_mock) -> None:
    """PL: Poprawny JSON health jest mapowany na model. EN: Valid health JSON is mapped to a model."""

    aioclient_mock.get(
        "http://ptz.lan:8080/health",
        json={"status": "ok", "version": "1.0.0", "name": "controller"},
    )
    client = PtzProxyClient(async_get_clientsession(hass), "http://ptz.lan:8080", "token", True, 3)

    result = await client.async_health()

    assert result.status == "ok"
    assert result.version == "1.0.0"
    request = aioclient_mock.mock_calls[0]
    assert request[3]["Authorization"] == "Bearer token"


async def test_health_hcnet_boolean_success(hass: HomeAssistant, aioclient_mock) -> None:
    """PL: Format HCNet z ok=true jest akceptowany. EN: The HCNet format with ok=true is accepted."""

    aioclient_mock.get(
        "http://ptz.lan:8080/health",
        json={"ok": True, "backend": "hcnet", "connected_sessions": 0},
    )
    client = PtzProxyClient(async_get_clientsession(hass), "http://ptz.lan:8080", "", True, 3)

    result = await client.async_health()

    assert result.status == "ok"


@pytest.mark.parametrize("status", [HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN])
async def test_health_invalid_auth(hass: HomeAssistant, aioclient_mock, status: HTTPStatus) -> None:
    """PL: 401 i 403 mają kategorię invalid_auth. EN: 401 and 403 use the invalid_auth category."""

    aioclient_mock.get("http://ptz.lan/health", status=status)
    client = PtzProxyClient(async_get_clientsession(hass), "http://ptz.lan", "bad", True, 3)
    with pytest.raises(PtzProxyAuthenticationError) as caught:
        await client.async_health()
    assert caught.value.details.error_code == "invalid_auth"
    assert caught.value.details.http_status == status


@pytest.mark.parametrize("status", [404, 500, 503])
async def test_health_http_error(hass: HomeAssistant, aioclient_mock, status: int) -> None:
    """PL: Inne błędy zachowują rzeczywisty status. EN: Other HTTP failures preserve the real status."""

    aioclient_mock.get("http://ptz.lan/health", status=status)
    client = PtzProxyClient(async_get_clientsession(hass), "http://ptz.lan", "", True, 3)
    with pytest.raises(PtzProxyHttpError) as caught:
        await client.async_health()
    assert caught.value.details.translation_key == "http_error"
    assert caught.value.details.http_status == status


@pytest.mark.parametrize("payload", ["not-json", "[]", '{"status":"error"}', '{"ok":false}', "{}"])
async def test_health_invalid_response(hass: HomeAssistant, aioclient_mock, payload: str) -> None:
    """PL: Niepoprawna treść nigdy nie wystarcza do zapisu. EN: Invalid content never qualifies for persistence."""

    aioclient_mock.get("http://ptz.lan/health", text=payload)
    client = PtzProxyClient(async_get_clientsession(hass), "http://ptz.lan", "", True, 3)
    with pytest.raises(PtzProxyInvalidResponseError):
        await client.async_health()


@pytest.mark.parametrize(
    ("action", "direction", "status"),
    [
        (PtzAction.START, PtzDirection.UP, 200),
        (PtzAction.STOP, PtzDirection.UP, 204),
        (PtzAction.STOP, PtzDirection.ALL, 204),
    ],
)
async def test_move_exact_payload(
    hass: HomeAssistant,
    aioclient_mock,
    action: PtzAction,
    direction: PtzDirection,
    status: int,
) -> None:
    """PL: Ruch wysyła jeden dokładny POST. EN: Movement sends one exact POST request."""

    aioclient_mock.post("http://ptz.lan/ptz", status=status)
    camera = CameraConfig("id", "Salon", "192.168.1.50", "admin", "secret")
    client = PtzProxyClient(async_get_clientsession(hass), "http://ptz.lan", "", True, 3)

    await client.async_move(camera, action, direction)

    assert len(aioclient_mock.mock_calls) == 1
    assert aioclient_mock.mock_calls[0][2] == {
        "ip": "192.168.1.50",
        "login": "admin",
        "password": "secret",
        "action": action.value,
        "direction": direction.value,
    }


async def test_move_rejects_start_all(hass: HomeAssistant) -> None:
    """PL: start/all jest odrzucane przed siecią. EN: start/all is rejected before network I/O."""

    camera = CameraConfig("id", "Salon", "host", "admin", "secret")
    client = PtzProxyClient(async_get_clientsession(hass), "http://ptz.lan", "", True, 3)
    with pytest.raises(ValueError):
        await client.async_move(camera, PtzAction.START, PtzDirection.ALL)
