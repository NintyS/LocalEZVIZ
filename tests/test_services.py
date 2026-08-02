"""Testy walidacji akcji encji. / Entity-action validation tests."""

from __future__ import annotations

import pytest
from homeassistant.exceptions import ServiceValidationError

from .test_camera import _entity


@pytest.mark.parametrize(
    ("action", "direction"),
    [("start", "all"), ("invalid", "left"), ("start", "diagonal")],
)
async def test_invalid_service_values_are_rejected(action: str, direction: str) -> None:
    """PL: Niedozwolone kombinacje kończą się błędem HA. EN: Invalid combinations raise an HA validation error."""

    entity, client = _entity()
    with pytest.raises(ServiceValidationError):
        await entity.async_ptz_move(action, direction)
    client.async_move.assert_not_awaited()


async def test_stop_all_is_allowed() -> None:
    """PL: Awaryjne stop/all jest dozwolone. EN: Emergency stop/all is allowed."""

    entity, client = _entity()
    await entity.async_ptz_move("stop", "all")
    client.async_move.assert_awaited_once()
