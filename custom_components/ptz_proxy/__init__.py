"""Inicjalizacja integracji PTZ Proxy. / PTZ Proxy integration initialization."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_register_platform_entity_service

from .api import PtzProxyClient
from .const import (
    ATTR_ACTION,
    ATTR_DIRECTION,
    CONF_API_TOKEN,
    CONF_BASE_URL,
    CONF_REQUEST_TIMEOUT,
    CONF_VERIFY_SSL,
    DOMAIN,
    FRONTEND_URL,
    PLATFORMS,
    SERVICE_MOVE,
    VERSION,
)
from .models import PtzAction, PtzDirection, PtzProxyConfigEntry, PtzProxyRuntimeData

_LOGGER = logging.getLogger(__name__)

# PL: Schemat danych usługi; target encji dodaje helper Home Assistanta.
# EN: Service data schema; Home Assistant's helper adds the entity target.
MOVE_SERVICE_SCHEMA = {
    vol.Required(ATTR_ACTION): vol.Coerce(PtzAction),
    vol.Required(ATTR_DIRECTION): vol.Coerce(PtzDirection),
}


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """PL: Jednorazowo zarejestruj akcję i kartę. EN: Register the action and card exactly once."""

    _LOGGER.info("Loading PTZ Proxy integration version %s", VERSION)
    async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_MOVE,
        entity_domain=Platform.CAMERA,
        func="async_ptz_move",
        schema=MOVE_SERVICE_SCHEMA,
    )

    frontend_file = Path(__file__).parent / "frontend" / "ptz-camera-card.js"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                FRONTEND_URL,
                str(frontend_file),
                cache_headers=True,
            )
        ]
    )
    add_extra_js_url(hass, f"{FRONTEND_URL}?v={VERSION}")
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: PtzProxyConfigEntry) -> None:
    """PL: Przeładuj parent entry po zmianie serwera lub kamery. EN: Reload the parent entry after a server or camera change."""

    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: PtzProxyConfigEntry) -> bool:
    """PL: Utwórz klienta runtime i załaduj encje kamer. EN: Create the runtime client and load camera entities."""

    entry.runtime_data = PtzProxyRuntimeData(
        client=PtzProxyClient(
            async_get_clientsession(hass),
            str(entry.data[CONF_BASE_URL]),
            str(entry.data.get(CONF_API_TOKEN, "")),
            bool(entry.data[CONF_VERIFY_SSL]),
            float(entry.data[CONF_REQUEST_TIMEOUT]),
        )
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PtzProxyConfigEntry) -> bool:
    """PL: Usuń encje tego serwera bez ruszania globalnej akcji. EN: Unload this server's entities without removing the global action."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
