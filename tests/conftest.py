"""Wspólne fixture testów. / Shared test fixtures."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ptz_proxy.const import (
    CONF_API_TOKEN,
    CONF_BASE_URL,
    CONF_NAME,
    CONF_REQUEST_TIMEOUT,
    CONF_VERIFY_SSL,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """PL: Włącz ładowanie custom integration. EN: Enable custom-integration loading."""

    yield


@pytest.fixture
def server_data() -> dict[str, object]:
    """PL: Zwróć poprawne dane przykładowego serwera. EN: Return valid sample server data."""

    return {
        CONF_NAME: "Serwer kamer",
        CONF_BASE_URL: "http://ptz.lan:8080",
        CONF_API_TOKEN: "server-secret",
        CONF_VERIFY_SSL: True,
        CONF_REQUEST_TIMEOUT: 3,
    }


@pytest.fixture
def mock_config_entry(hass: HomeAssistant, server_data: dict[str, object]) -> MockConfigEntry:
    """PL: Dodaj przykładowy config entry do HA. EN: Add a sample config entry to HA."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Serwer kamer",
        data=server_data,
        unique_id="http://ptz.lan:8080",
    )
    entry.add_to_hass(hass)
    return entry
