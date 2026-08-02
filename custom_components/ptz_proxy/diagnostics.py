"""Bezpieczna diagnostyka PTZ Proxy. / Safe PTZ Proxy diagnostics."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import (
    CONF_API_TOKEN,
    CONF_BASE_URL,
    CONF_CAMERA_IP,
    CONF_REQUEST_TIMEOUT,
    CONF_VERIFY_SSL,
    DOMAIN,
    SUBENTRY_TYPE_CAMERA,
    VERSION,
)
from .models import CameraConfig, PtzProxyConfigEntry


def _redact_url(raw_url: str) -> str:
    """PL: Usuń userinfo, query i fragment z URL. EN: Remove userinfo, query, and fragment from a URL."""

    parsed = urlsplit(raw_url)
    host = parsed.hostname or "redacted-host"
    if ":" in host:
        host = f"[{host}]"
    netloc = f"{host}:{parsed.port}" if parsed.port is not None else host
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _camera_diagnostics(camera: CameraConfig) -> dict[str, Any]:
    """PL: Zwróć wyłącznie bezpieczne fakty o kamerze. EN: Return only safe facts about a camera."""

    return {
        "name": camera.name,
        CONF_CAMERA_IP: camera.camera_ip,
        "username_configured": bool(camera.username),
        "password_configured": bool(camera.password),
        "rtsp_url_configured": bool(camera.rtsp_url),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PtzProxyConfigEntry
) -> dict[str, Any]:
    """PL: Zbuduj diagnostykę serwera bez sekretów. EN: Build secret-free server diagnostics."""

    cameras = [
        CameraConfig.from_subentry(subentry)
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_CAMERA
    ]
    return {
        "integration_version": VERSION,
        "server": {
            "name": entry.title,
            CONF_BASE_URL: _redact_url(str(entry.data[CONF_BASE_URL])),
            CONF_VERIFY_SSL: bool(entry.data[CONF_VERIFY_SSL]),
            CONF_REQUEST_TIMEOUT: entry.data[CONF_REQUEST_TIMEOUT],
            "api_token_configured": bool(entry.data.get(CONF_API_TOKEN)),
            "camera_count": len(cameras),
        },
        "cameras": [_camera_diagnostics(camera) for camera in cameras],
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: PtzProxyConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """PL: Zbuduj diagnostykę wskazanego urządzenia-kamery. EN: Build diagnostics for the selected camera device."""

    camera_ids = {identifier[1] for identifier in device.identifiers if identifier[0] == DOMAIN}
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_CAMERA:
            continue
        camera = CameraConfig.from_subentry(subentry)
        if camera.camera_id in camera_ids:
            return _camera_diagnostics(camera)
    return {"camera": "not_found"}
