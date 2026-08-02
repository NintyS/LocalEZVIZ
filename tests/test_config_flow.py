"""Testy formularzy konfiguracji. / Configuration-flow tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ptz_proxy.api import (
    PtzProxyAuthenticationError,
    PtzProxyConnectionError,
    PtzProxyHttpError,
    PtzProxyInvalidResponseError,
    PtzProxyTimeoutError,
    PtzProxyTlsError,
)
from custom_components.ptz_proxy.const import (
    CONF_API_TOKEN,
    CONF_BASE_URL,
    CONF_NAME,
    CONF_REQUEST_TIMEOUT,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.ptz_proxy.models import ErrorDetails, HealthResponse


def _suggested_value(result, field: str):
    """PL: Odczytaj wartość sugerowaną ze schematu HA. EN: Read a suggested value from an HA schema."""

    for marker in result["data_schema"].schema:
        if marker.schema == field:
            return marker.description.get("suggested_value")
    raise AssertionError(f"Missing schema field: {field}")


def _error(details: ErrorDetails, error_type=PtzProxyConnectionError):
    """PL: Zbuduj kontrolowany wyjątek testowy. EN: Build a controlled test exception."""

    return error_type(details)


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (_error(ErrorDetails("timeout", "timeout", "safe"), PtzProxyTimeoutError), "timeout"),
        (_error(ErrorDetails("dns_error", "dns_error", "safe")), "dns_error"),
        (
            _error(ErrorDetails("connection_refused", "connection_refused", "safe")),
            "connection_refused",
        ),
        (
            _error(ErrorDetails("network_unreachable", "network_unreachable", "safe")),
            "network_unreachable",
        ),
        (
            _error(
                ErrorDetails("tls_verification_failed", "tls_verification_failed", "safe"),
                PtzProxyTlsError,
            ),
            "tls_verification_failed",
        ),
        (
            _error(
                ErrorDetails("invalid_auth", "invalid_auth", "safe", 401),
                PtzProxyAuthenticationError,
            ),
            "invalid_auth",
        ),
        (
            _error(
                ErrorDetails("invalid_auth", "invalid_auth", "safe", 403),
                PtzProxyAuthenticationError,
            ),
            "invalid_auth",
        ),
        (
            _error(ErrorDetails("http_error", "http_error", "safe", 404), PtzProxyHttpError),
            "http_error",
        ),
        (
            _error(ErrorDetails("http_error", "http_error", "safe", 500), PtzProxyHttpError),
            "http_error",
        ),
        (
            _error(ErrorDetails("http_error", "http_error", "safe", 503), PtzProxyHttpError),
            "http_error",
        ),
        (
            _error(
                ErrorDetails("invalid_json", "invalid_json", "safe"), PtzProxyInvalidResponseError
            ),
            "invalid_json",
        ),
        (
            _error(
                ErrorDetails("invalid_health_response", "invalid_health_response", "safe"),
                PtzProxyInvalidResponseError,
            ),
            "invalid_health_response",
        ),
    ],
)
async def test_error_keeps_same_form_and_values(
    hass: HomeAssistant,
    server_data: dict[str, object],
    exception: Exception,
    expected: str,
) -> None:
    """PL: Każda awaria zachowuje formularz i wszystkie pola. EN: Every failure preserves the form and every field."""

    with patch(
        "custom_components.ptz_proxy.config_flow.PtzProxyClient.async_health",
        AsyncMock(side_effect=exception),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=server_data
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": expected}
    for field in (
        CONF_NAME,
        CONF_BASE_URL,
        CONF_API_TOKEN,
        CONF_VERIFY_SSL,
        CONF_REQUEST_TIMEOUT,
    ):
        assert _suggested_value(result, field) == server_data[field]
    assert result["description_placeholders"]["error_code"] == expected
    assert "server-secret" not in str(result["description_placeholders"])
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_unknown_error_is_sanitized(
    hass: HomeAssistant, server_data: dict[str, object]
) -> None:
    """PL: Surowy nieznany wyjątek nie trafia do formularza. EN: A raw unknown exception never reaches the form."""

    raw_secret = "Authorization: Bearer never-show-this"
    with patch(
        "custom_components.ptz_proxy.config_flow.PtzProxyClient.async_health",
        AsyncMock(side_effect=RuntimeError(raw_secret)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=server_data
        )
    assert result["errors"] == {"base": "unknown"}
    assert raw_secret not in str(result["description_placeholders"])


async def test_retry_in_same_flow_succeeds(
    hass: HomeAssistant, server_data: dict[str, object]
) -> None:
    """PL: Zmiana jednego pola w tym samym flow kończy konfigurację. EN: Correcting one field in the same flow completes setup."""

    health = AsyncMock(
        side_effect=[
            _error(ErrorDetails("connection_refused", "connection_refused", "safe")),
            HealthResponse("ok"),
        ]
    )
    with patch("custom_components.ptz_proxy.config_flow.PtzProxyClient.async_health", health):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=server_data
        )
        corrected = dict(server_data)
        corrected[CONF_BASE_URL] = "http://ptz-fixed.lan:8080"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], corrected)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BASE_URL] == "http://ptz-fixed.lan:8080"
    assert result["data"][CONF_API_TOKEN] == "server-secret"


async def test_duplicate_server_is_rejected(
    hass: HomeAssistant, server_data: dict[str, object]
) -> None:
    """PL: Znormalizowany duplikat nie tworzy drugiego wpisu. EN: A normalized duplicate does not create a second entry."""

    existing = MockConfigEntry(
        domain=DOMAIN,
        data=server_data,
        unique_id="http://ptz.lan:8080",
    )
    existing.add_to_hass(hass)
    with patch(
        "custom_components.ptz_proxy.config_flow.PtzProxyClient.async_health",
        AsyncMock(return_value=HealthResponse("ok")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=server_data
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_blank_token_preserves_existing(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, server_data: dict[str, object]
) -> None:
    """PL: Pusty token nie nadpisuje działającego. EN: A blank token does not overwrite the working token."""

    submitted = dict(server_data)
    submitted[CONF_API_TOKEN] = ""
    submitted[CONF_BASE_URL] = "http://new-ptz.lan:8080"
    with patch(
        "custom_components.ptz_proxy.config_flow.PtzProxyClient.async_health",
        AsyncMock(return_value=HealthResponse("ok")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": SOURCE_RECONFIGURE,
                "entry_id": mock_config_entry.entry_id,
            },
            data=submitted,
        )
    assert result["type"] is FlowResultType.ABORT
    assert mock_config_entry.data[CONF_API_TOKEN] == "server-secret"
    assert mock_config_entry.data[CONF_BASE_URL] == "http://new-ptz.lan:8080"
