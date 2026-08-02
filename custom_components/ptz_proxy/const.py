"""Stałe integracji PTZ Proxy. / Constants for the PTZ Proxy integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

# PL: Tożsamość integracji i wersja zasobu frontendowego.
# EN: Integration identity and frontend asset version.
DOMAIN: Final = "ptz_proxy"
INTEGRATION_NAME: Final = "PTZ Proxy"
VERSION: Final = "0.2.1"
PLATFORMS: Final = (Platform.CAMERA,)

# PL: Klucze danych serwera zapisywane w głównym config entry.
# EN: Server data keys stored in the parent config entry.
CONF_NAME: Final = "name"
CONF_BASE_URL: Final = "base_url"
CONF_API_TOKEN: Final = "api_token"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_REQUEST_TIMEOUT: Final = "request_timeout"
DEFAULT_REQUEST_TIMEOUT: Final = 3
MIN_REQUEST_TIMEOUT: Final = 1
MAX_REQUEST_TIMEOUT: Final = 30

# PL: Klucze prywatnej konfiguracji kamery zapisywane w config subentry.
# EN: Private camera configuration keys stored in a config subentry.
SUBENTRY_TYPE_CAMERA: Final = "camera"
CONF_CAMERA_ID: Final = "camera_id"
CONF_CAMERA_IP: Final = "camera_ip"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_RTSP_URL: Final = "rtsp_url"

# PL: Nazwy akcji i pól wywołania usługi Home Assistanta.
# EN: Home Assistant action and service-call field names.
SERVICE_MOVE: Final = "move"
ATTR_ACTION: Final = "action"
ATTR_DIRECTION: Final = "direction"

# PL: Ścieżki API serwera PTZ oraz automatycznie ładowanego modułu karty.
# EN: PTZ server API paths and the automatically loaded card module path.
HEALTH_PATH: Final = "/health"
PTZ_PATH: Final = "/ptz"
FRONTEND_URL: Final = "/ptz_proxy_static/ptz-camera-card.js"
