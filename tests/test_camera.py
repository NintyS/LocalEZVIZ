"""Testy encji kamery. / Camera entity tests."""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.components.camera import CameraEntityFeature
from homeassistant.config_entries import ConfigSubentry

from custom_components.ptz_proxy.camera import PtzProxyCamera
from custom_components.ptz_proxy.const import (
    CONF_BASE_URL,
    CONF_CAMERA_ID,
    CONF_CAMERA_IP,
    CONF_PASSWORD,
    CONF_RTSP_URL,
    CONF_USERNAME,
    DOMAIN,
    SUBENTRY_TYPE_CAMERA,
)
from custom_components.ptz_proxy.models import PtzAction, PtzDirection


def _entity(
    rtsp_url: str = "rtsp://admin:camera-secret@camera/stream",
) -> tuple[PtzProxyCamera, AsyncMock]:
    """PL: Utwórz encję bez uruchamiania platformy. EN: Create an entity without setting up the platform."""

    client = AsyncMock()
    entry = SimpleNamespace(
        entry_id="server-id",
        data={CONF_BASE_URL: "http://ptz.lan"},
        runtime_data=SimpleNamespace(client=client),
    )
    subentry = ConfigSubentry(
        subentry_id="subentry-id",
        subentry_type=SUBENTRY_TYPE_CAMERA,
        title="Kamera salon",
        unique_id="camera-uuid",
        data=MappingProxyType(
            {
                CONF_CAMERA_ID: "camera-uuid",
                CONF_CAMERA_IP: "192.168.1.50",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "camera-secret",
                CONF_RTSP_URL: rtsp_url,
            }
        ),
    )
    return PtzProxyCamera(entry, subentry), client


def test_camera_identity_and_no_secret_attributes() -> None:
    """PL: Encja ma stabilne ID i nie ujawnia sekretów. EN: The entity has a stable ID and exposes no secrets."""

    entity, _client = _entity()
    assert entity.unique_id == "server-id_camera-uuid"
    assert entity.should_poll is False
    assert entity.available is True
    assert len(entity.access_tokens) == 1
    assert entity.device_info["identifiers"] == {(DOMAIN, "camera-uuid")}
    assert "camera-secret" not in str(entity.extra_state_attributes)


async def test_camera_exposes_private_rtsp_stream() -> None:
    """PL: RTSP aktywuje stream i snapshoty ze streamu. EN: RTSP enables streaming and stream-derived stills."""

    entity, _client = _entity()
    assert await entity.async_camera_image() is None
    assert await entity.stream_source() == "rtsp://admin:camera-secret@camera/stream"
    assert entity.supported_features & CameraEntityFeature.STREAM
    assert entity.use_stream_for_stills is True


async def test_camera_without_rtsp_remains_available() -> None:
    """PL: Brak RTSP wyłącza obraz, ale nie encję PTZ. EN: Missing RTSP disables imagery but not the PTZ entity."""

    entity, _client = _entity("")
    assert entity.available is True
    assert await entity.stream_source() is None
    assert entity.supported_features == CameraEntityFeature(0)
    assert entity.use_stream_for_stills is False


async def test_camera_move_uses_private_backend_config() -> None:
    """PL: Usługa przekazuje klientowi prywatny model backendu. EN: The service passes the private backend model to the client."""

    entity, client = _entity()
    await entity.async_ptz_move("start", "left")
    camera, action, direction = client.async_move.await_args.args
    assert camera.password == "camera-secret"
    assert action is PtzAction.START
    assert direction is PtzDirection.LEFT
