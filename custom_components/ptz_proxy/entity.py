"""Wspólna baza encji PTZ Proxy. / Shared PTZ Proxy entity base."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import CONF_BASE_URL, DOMAIN
from .models import CameraConfig, PtzProxyConfigEntry


class PtzProxyEntity(Entity):
    """PL: Wspólna tożsamość encji i urządzenia kamery. EN: Shared camera entity and device identity."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: PtzProxyConfigEntry, subentry: ConfigSubentry) -> None:
        """PL: Połącz encję z parent entry i camera subentry. EN: Link the entity to its parent entry and camera subentry."""

        self._entry = entry
        self._subentry = subentry
        self._camera = CameraConfig.from_subentry(subentry)
        self._attr_unique_id = f"{entry.entry_id}_{self._camera.camera_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._camera.camera_id)},
            name=self._camera.name,
            manufacturer="Generic",
            model="PTZ Proxy Camera",
            configuration_url=str(entry.data[CONF_BASE_URL]),
        )
