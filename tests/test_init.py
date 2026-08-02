"""Testy cyklu życia integracji. / Integration lifecycle tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.ptz_proxy import async_setup


async def test_global_setup_registers_frontend_and_service(hass: HomeAssistant) -> None:
    """PL: Setup rejestruje akcję i zasób karty. EN: Setup registers the action and card asset."""

    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    with (
        patch("custom_components.ptz_proxy.async_register_platform_entity_service") as service,
        patch("custom_components.ptz_proxy.add_extra_js_url") as frontend,
    ):
        assert await async_setup(hass, {}) is True
    service.assert_called_once()
    hass.http.async_register_static_paths.assert_awaited_once()
    frontend.assert_called_once()
