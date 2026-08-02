"""Encje kamer PTZ Proxy. / PTZ Proxy camera entities."""

from __future__ import annotations

import logging

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import PtzProxyError, get_safe_error_details
from .const import DOMAIN, SUBENTRY_TYPE_CAMERA, VERSION
from .entity import PtzProxyEntity
from .models import PtzAction, PtzDirection, PtzProxyConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PtzProxyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """PL: Utwórz jedną encję dla każdej camera subentry. EN: Create one entity for every camera subentry."""

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_CAMERA:
            continue
        async_add_entities(
            [PtzProxyCamera(entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class PtzProxyCamera(PtzProxyEntity, Camera):
    """PL: Kamera RTSP z bezpiecznym sterowaniem PTZ. EN: RTSP camera with secure PTZ control."""

    _attr_name = None

    def __init__(self, entry: PtzProxyConfigEntry, subentry: ConfigSubentry) -> None:
        """PL: Zainicjalizuj bazę Camera i włącz stream, gdy podano RTSP. EN: Initialize the Camera base and enable streaming when RTSP is configured."""

        super().__init__(entry, subentry)
        self._attr_supported_features = (
            CameraEntityFeature.STREAM if self._camera.rtsp_url else CameraEntityFeature(0)
        )

    @property
    def use_stream_for_stills(self) -> bool:
        """PL: Twórz podgląd statyczny ze streamu RTSP. EN: Generate still previews from the RTSP stream."""

        return bool(self._camera.rtsp_url)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """PL: Bez RTSP nie istnieje osobny endpoint snapshotu. EN: Without RTSP there is no separate snapshot endpoint."""

        return None

    async def stream_source(self) -> str | None:
        """PL: Zwróć prywatny adres RTSP wyłącznie backendowi HA. EN: Return the private RTSP URL only to the HA backend."""

        return self._camera.rtsp_url or None

    async def async_ptz_move(self, action: PtzAction | str, direction: PtzDirection | str) -> None:
        """PL: Zweryfikuj i wykonaj komendę PTZ dla tej encji. EN: Validate and execute a PTZ command for this entity."""

        try:
            parsed_action = PtzAction(action)
            parsed_direction = PtzDirection(direction)
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_movement",
            ) from err
        if parsed_action is PtzAction.START and parsed_direction is PtzDirection.ALL:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="start_all_not_allowed",
            )

        _LOGGER.info(
            "PTZ Proxy %s command: camera=%s action=%s direction=%s",
            VERSION,
            self._camera.name,
            parsed_action.value,
            parsed_direction.value,
        )
        try:
            await self._entry.runtime_data.client.async_move(
                self._camera, parsed_action, parsed_direction
            )
        except PtzProxyError as err:
            details = get_safe_error_details(err)
            _LOGGER.warning(
                "PTZ command failed for camera %s: error=%s status=%s",
                self._camera.name,
                details.error_code,
                details.http_status if details.http_status is not None else "none",
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="ptz_command_failed",
                translation_placeholders={"error_code": details.error_code},
            ) from err
        _LOGGER.info(
            "PTZ Proxy %s command succeeded: camera=%s action=%s direction=%s",
            VERSION,
            self._camera.name,
            parsed_action.value,
            parsed_direction.value,
        )
