"""Testy config subentries kamer. / Camera config-subentry tests."""

from __future__ import annotations

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    SubentryFlowContext,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ptz_proxy.const import (
    CONF_CAMERA_ID,
    CONF_CAMERA_IP,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_RTSP_URL,
    CONF_USERNAME,
    SUBENTRY_TYPE_CAMERA,
)


async def _async_add_camera(hass: HomeAssistant, entry: MockConfigEntry):
    """PL: Dodaj kamerę przez rzeczywisty manager subentries. EN: Add a camera through the real subentry manager."""

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_CAMERA),
        context=SubentryFlowContext(source=SOURCE_USER),
    )
    return await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Salon",
            CONF_CAMERA_IP: "192.168.1.50",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "old-secret",
            CONF_RTSP_URL: "",
        },
    )


async def test_add_camera_creates_stable_uuid(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """PL: Dodanie tworzy camera subentry z UUID. EN: Adding creates a camera subentry with a UUID."""

    result = await _async_add_camera(hass, mock_config_entry)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["unique_id"]
    assert result["data"][CONF_CAMERA_ID] == result["unique_id"]
    assert len(mock_config_entry.subentries) == 1


async def test_reconfigure_preserves_blank_password(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """PL: Rekonfiguracja zachowuje UUID i stare hasło. EN: Reconfiguration preserves the UUID and old password."""

    await _async_add_camera(hass, mock_config_entry)
    subentry = next(iter(mock_config_entry.subentries.values()))
    original_unique_id = subentry.unique_id
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_CAMERA),
        context=SubentryFlowContext(
            source=SOURCE_RECONFIGURE,
            subentry_id=subentry.subentry_id,
        ),
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Salon po zmianie",
            CONF_CAMERA_IP: "192.168.1.51",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "",
            CONF_RTSP_URL: "",
        },
    )
    assert result["type"] is FlowResultType.ABORT
    updated = mock_config_entry.subentries[subentry.subentry_id]
    assert updated.unique_id == original_unique_id
    assert updated.data[CONF_PASSWORD] == "old-secret"
    assert updated.data[CONF_CAMERA_IP] == "192.168.1.51"
