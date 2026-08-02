"""Przepływy konfiguracji PTZ Proxy. / PTZ Proxy configuration flows."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import PtzProxyClient, PtzProxyError, get_safe_error_details, normalize_base_url
from .const import (
    CONF_API_TOKEN,
    CONF_BASE_URL,
    CONF_CAMERA_ID,
    CONF_CAMERA_IP,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_REQUEST_TIMEOUT,
    CONF_RTSP_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DEFAULT_REQUEST_TIMEOUT,
    DOMAIN,
    MAX_REQUEST_TIMEOUT,
    MIN_REQUEST_TIMEOUT,
    SUBENTRY_TYPE_CAMERA,
)
from .models import ErrorDetails

_LOGGER = logging.getLogger(__name__)


# PL: Schemat głównego serwera; hasło-token jest maskowane przez selektor.
# EN: Parent server schema; the token is masked by the password selector.
SERVER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): TextSelector(TextSelectorConfig()),
        vol.Required(CONF_BASE_URL): TextSelector(TextSelectorConfig()),
        vol.Optional(CONF_API_TOKEN, default=""): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_VERIFY_SSL, default=True): BooleanSelector(),
        vol.Required(CONF_REQUEST_TIMEOUT, default=DEFAULT_REQUEST_TIMEOUT): NumberSelector(
            NumberSelectorConfig(
                min=MIN_REQUEST_TIMEOUT,
                max=MAX_REQUEST_TIMEOUT,
                step=1,
                mode=NumberSelectorMode.BOX,
            )
        ),
    }
)

# PL: Schemat nowej kamery wymaga wszystkich danych logowania.
# EN: New-camera schema requires all camera credentials.
CAMERA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): TextSelector(TextSelectorConfig()),
        vol.Required(CONF_CAMERA_IP): TextSelector(TextSelectorConfig()),
        vol.Required(CONF_USERNAME): TextSelector(TextSelectorConfig()),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_RTSP_URL, default=""): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
    }
)

# PL: W rekonfiguracji puste hasło oznacza zachowanie poprzedniego.
# EN: During reconfiguration an empty password preserves the existing one.
CAMERA_RECONFIGURE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): TextSelector(TextSelectorConfig()),
        vol.Required(CONF_CAMERA_IP): TextSelector(TextSelectorConfig()),
        vol.Required(CONF_USERNAME): TextSelector(TextSelectorConfig()),
        vol.Optional(CONF_PASSWORD, default=""): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_RTSP_URL, default=""): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
    }
)


def _empty_placeholders() -> dict[str, str]:
    """PL: Utwórz puste, stabilne placeholdery opisu. EN: Create empty, stable description placeholders."""

    return {"error_code": "—", "status_code": "—", "error_detail": "—"}


def _url_error_details() -> ErrorDetails:
    """PL: Zwróć bezpieczny błąd walidacji URL. EN: Return a safe URL validation error."""

    return ErrorDetails(
        "invalid_url",
        "invalid_url",
        "Use an HTTP or HTTPS address without credentials, query, or fragment.",
    )


def _server_data(user_input: dict[str, Any], normalized_url: str) -> dict[str, Any]:
    """PL: Zbuduj kanoniczne dane serwera. EN: Build canonical server data."""

    return {
        CONF_NAME: str(user_input[CONF_NAME]).strip(),
        CONF_BASE_URL: normalized_url,
        CONF_API_TOKEN: str(user_input.get(CONF_API_TOKEN, "")),
        CONF_VERIFY_SSL: bool(user_input[CONF_VERIFY_SSL]),
        CONF_REQUEST_TIMEOUT: float(user_input[CONF_REQUEST_TIMEOUT]),
    }


def _camera_data(
    user_input: dict[str, Any], camera_id: str, previous_password: str | None = None
) -> dict[str, str]:
    """PL: Zbuduj prywatne dane kamery, zachowując puste stare hasło. EN: Build private camera data while preserving a password on blank input."""

    password = str(user_input.get(CONF_PASSWORD, ""))
    if not password and previous_password is not None:
        password = previous_password
    return {
        CONF_CAMERA_ID: camera_id,
        CONF_CAMERA_IP: str(user_input[CONF_CAMERA_IP]).strip(),
        CONF_USERNAME: str(user_input[CONF_USERNAME]).strip(),
        CONF_PASSWORD: password,
        CONF_RTSP_URL: str(user_input.get(CONF_RTSP_URL, "")).strip(),
    }


def _log_health_error(name: str, base_url: str, details: ErrorDetails) -> None:
    """PL: Zaloguj kategorię bez URL i sekretów. EN: Log the category without URLs or secrets."""

    parsed = urlsplit(base_url)
    target = parsed.hostname or "server"
    if parsed.port is not None:
        target = f"{target}:{parsed.port}"
    if details.http_status is None:
        _LOGGER.warning(
            "Health check failed for PTZ server %s (%s): error=%s",
            name,
            target,
            details.error_code,
        )
    else:
        _LOGGER.warning(
            "Health check failed for PTZ server %s (%s): error=%s status=%s",
            name,
            target,
            details.error_code,
            details.http_status,
        )


async def _async_validate_server(flow: ConfigFlow, data: dict[str, Any]) -> ErrorDetails | None:
    """PL: Wykonaj health check bez zapisywania danych. EN: Run a health check without persisting data."""

    client = PtzProxyClient(
        async_get_clientsession(flow.hass),
        data[CONF_BASE_URL],
        data[CONF_API_TOKEN],
        data[CONF_VERIFY_SSL],
        data[CONF_REQUEST_TIMEOUT],
    )
    try:
        await client.async_health()
    except PtzProxyError as err:
        details = get_safe_error_details(err)
    except Exception as err:
        details = get_safe_error_details(err)
    else:
        return None
    _log_health_error(data[CONF_NAME], data[CONF_BASE_URL], details)
    return details


class PtzProxyConfigFlow(ConfigFlow, domain=DOMAIN):
    """PL: Konfiguruj i rekonfiguruj serwer PTZ. EN: Configure and reconfigure a PTZ server."""

    VERSION = 1
    MINOR_VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """PL: Udostępnij flow kamer dla wpisu serwera. EN: Expose camera subentry flows for a server entry."""

        return {SUBENTRY_TYPE_CAMERA: CameraSubentryFlowHandler}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """PL: Dodaj serwer po udanym health check. EN: Add a server after a successful health check."""

        details: ErrorDetails | None = None
        if user_input is not None:
            try:
                normalized_url = normalize_base_url(str(user_input[CONF_BASE_URL]))
            except (TypeError, ValueError):
                details = _url_error_details()
            else:
                data = _server_data(user_input, normalized_url)
                details = await _async_validate_server(self, data)
                if details is None:
                    await self.async_set_unique_id(normalized_url)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=data[CONF_NAME], data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SERVER_SCHEMA, user_input or {}),
            errors={"base": details.translation_key} if details else {},
            description_placeholders=(
                details.as_placeholders() if details else _empty_placeholders()
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """PL: Zmień serwer dopiero po udanym health check. EN: Update a server only after a successful health check."""

        entry = self._get_reconfigure_entry()
        details: ErrorDetails | None = None
        if user_input is not None:
            submitted = dict(user_input)
            if not submitted.get(CONF_API_TOKEN):
                submitted[CONF_API_TOKEN] = entry.data.get(CONF_API_TOKEN, "")
            try:
                normalized_url = normalize_base_url(str(submitted[CONF_BASE_URL]))
            except (TypeError, ValueError):
                details = _url_error_details()
            else:
                data = _server_data(submitted, normalized_url)
                details = await _async_validate_server(self, data)
                if details is None:
                    for other_entry in self._async_current_entries(include_ignore=False):
                        if (
                            other_entry.entry_id != entry.entry_id
                            and other_entry.unique_id == normalized_url
                        ):
                            return self.async_abort(reason="already_configured")
                    return self.async_update_and_abort(
                        entry,
                        title=data[CONF_NAME],
                        unique_id=normalized_url,
                        data=data,
                    )

        if user_input is None:
            suggested = dict(entry.data)
            suggested[CONF_API_TOKEN] = ""
        else:
            suggested = user_input
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(SERVER_SCHEMA, suggested),
            errors={"base": details.translation_key} if details else {},
            description_placeholders=(
                details.as_placeholders() if details else _empty_placeholders()
            ),
        )


class CameraSubentryFlowHandler(ConfigSubentryFlow):
    """PL: Dodawaj i rekonfiguruj kamery jako subentries. EN: Add and reconfigure cameras as subentries."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """PL: Dodaj kamerę z losowym, stabilnym UUID. EN: Add a camera with a random, stable UUID."""

        errors: dict[str, str] = {}
        if user_input is not None:
            required_values = (
                CONF_NAME,
                CONF_CAMERA_IP,
                CONF_USERNAME,
                CONF_PASSWORD,
            )
            for key in required_values:
                if not str(user_input.get(key, "")).strip():
                    errors[key] = "required"
            if not errors:
                camera_id = str(uuid4())
                return self.async_create_entry(
                    title=str(user_input[CONF_NAME]).strip(),
                    data=_camera_data(user_input, camera_id),
                    unique_id=camera_id,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(CAMERA_SCHEMA, user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """PL: Zmień kamerę bez zmiany UUID i przypadkowej utraty hasła. EN: Update a camera without changing its UUID or accidentally erasing its password."""

        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            for key in (CONF_NAME, CONF_CAMERA_IP, CONF_USERNAME):
                if not str(user_input.get(key, "")).strip():
                    errors[key] = "required"
            if not errors:
                camera_id = str(
                    subentry.data.get(CONF_CAMERA_ID) or subentry.unique_id or subentry.subentry_id
                )
                data = _camera_data(
                    user_input,
                    camera_id,
                    previous_password=str(subentry.data[CONF_PASSWORD]),
                )
                return self.async_update_and_abort(
                    entry,
                    subentry,
                    title=str(user_input[CONF_NAME]).strip(),
                    unique_id=camera_id,
                    data=data,
                )

        if user_input is None:
            suggested = {
                CONF_NAME: subentry.title,
                CONF_CAMERA_IP: subentry.data[CONF_CAMERA_IP],
                CONF_USERNAME: subentry.data[CONF_USERNAME],
                CONF_PASSWORD: "",
                CONF_RTSP_URL: subentry.data.get(CONF_RTSP_URL, ""),
            }
        else:
            suggested = user_input
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(CAMERA_RECONFIGURE_SCHEMA, suggested),
            errors=errors,
        )
