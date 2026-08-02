"""Testy redakcji diagnostyki. / Diagnostics redaction tests."""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace

from homeassistant.config_entries import ConfigSubentry

from custom_components.ptz_proxy.const import (
    CONF_API_TOKEN,
    CONF_BASE_URL,
    CONF_CAMERA_ID,
    CONF_CAMERA_IP,
    CONF_PASSWORD,
    CONF_REQUEST_TIMEOUT,
    CONF_RTSP_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    SUBENTRY_TYPE_CAMERA,
)
from custom_components.ptz_proxy.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_contains_no_secrets() -> None:
    """PL: Token, hasło, username i pełny RTSP są nieobecne. EN: Token, password, username, and full RTSP are absent."""

    subentry = ConfigSubentry(
        subentry_id="sub-id",
        subentry_type=SUBENTRY_TYPE_CAMERA,
        title="Salon",
        unique_id="camera-id",
        data=MappingProxyType(
            {
                CONF_CAMERA_ID: "camera-id",
                CONF_CAMERA_IP: "192.168.1.50",
                CONF_USERNAME: "admin-secret-name",
                CONF_PASSWORD: "camera-secret",
                CONF_RTSP_URL: "rtsp://admin-secret-name:camera-secret@camera/stream",
            }
        ),
    )
    entry = SimpleNamespace(
        title="Server",
        data={
            CONF_BASE_URL: "http://ptz.lan:8080/base",
            CONF_API_TOKEN: "api-secret",
            CONF_VERIFY_SSL: True,
            CONF_REQUEST_TIMEOUT: 3,
        },
        subentries={subentry.subentry_id: subentry},
    )
    result = await async_get_config_entry_diagnostics(None, entry)
    serialized = str(result)
    for secret in (
        "api-secret",
        "camera-secret",
        "admin-secret-name",
        "rtsp://",
    ):
        assert secret not in serialized
    assert result["server"]["api_token_configured"] is True
    assert result["cameras"][0]["password_configured"] is True
