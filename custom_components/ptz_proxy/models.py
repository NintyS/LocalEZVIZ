"""Modele danych PTZ Proxy. / PTZ Proxy data models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry

from .const import (
    CONF_CAMERA_ID,
    CONF_CAMERA_IP,
    CONF_PASSWORD,
    CONF_RTSP_URL,
    CONF_USERNAME,
)


class PtzAction(StrEnum):
    """PL: Dozwolona faza ruchu PTZ. EN: Allowed PTZ movement phase."""

    START = "start"
    STOP = "stop"


class PtzDirection(StrEnum):
    """PL: Dozwolony kierunek ruchu MVP. EN: Allowed MVP movement direction."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    ALL = "all"


@dataclass(slots=True, frozen=True)
class HealthResponse:
    """PL: Sprawdzona odpowiedź endpointu health. EN: Validated health response."""

    status: str
    version: str | None = None
    name: str | None = None


@dataclass(slots=True, frozen=True)
class CameraConfig:
    """PL: Prywatne dane kamery używane tylko w backendzie. EN: Private camera data used only by the backend."""

    camera_id: str
    name: str
    camera_ip: str
    username: str
    password: str
    rtsp_url: str = ""

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> CameraConfig:
        """PL: Zbuduj model z config subentry. EN: Build the model from a config subentry."""

        data = subentry.data
        return cls(
            camera_id=str(data.get(CONF_CAMERA_ID) or subentry.unique_id or subentry.subentry_id),
            name=subentry.title,
            camera_ip=str(data[CONF_CAMERA_IP]),
            username=str(data[CONF_USERNAME]),
            password=str(data[CONF_PASSWORD]),
            rtsp_url=str(data.get(CONF_RTSP_URL, "")),
        )

    def as_request_payload(self, action: PtzAction, direction: PtzDirection) -> dict[str, str]:
        """PL: Zbuduj poufny payload żądania PTZ. EN: Build the confidential PTZ request payload."""

        return {
            "ip": self.camera_ip,
            "login": self.username,
            "password": self.password,
            "action": action.value,
            "direction": direction.value,
        }


@dataclass(slots=True, frozen=True)
class ErrorDetails:
    """PL: Bezpieczny opis błędu dla UI i logów. EN: Safe error description for the UI and logs."""

    translation_key: str
    error_code: str
    detail: str
    http_status: int | None = None

    def as_placeholders(self) -> dict[str, str]:
        """PL: Zwróć bezpieczne placeholdery formularza. EN: Return safe form placeholders."""

        return {
            "error_code": self.error_code,
            "status_code": str(self.http_status) if self.http_status is not None else "—",
            "error_detail": self.detail,
        }


@dataclass(slots=True)
class PtzProxyRuntimeData:
    """PL: Typowane dane dostępne podczas działania wpisu. EN: Typed runtime data for a loaded entry."""

    client: Any


# PL: Alias wymusza typ runtime_data w całej integracji.
# EN: The alias enforces the runtime_data type throughout the integration.
type PtzProxyConfigEntry = ConfigEntry[PtzProxyRuntimeData]


# PL: Czytelny typ dla danych wejściowych formularzy.
# EN: Readable type for form input data.
type FormData = Mapping[str, Any]
