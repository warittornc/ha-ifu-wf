"""Climate mappings and command behavior."""

from dataclasses import replace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.ifu_wf.api import IfuWfError
from custom_components.ifu_wf.climate import IfuWfClimate


@pytest.fixture
def climate(state):
    coordinator = Mock(data=state)
    coordinator.client.host = "192.168.1.60"
    coordinator.client.async_set = AsyncMock(return_value=state)
    return IfuWfClimate(coordinator)


def test_properties(climate):
    assert climate.hvac_mode == HVACMode.OFF
    assert climate.current_temperature is None
    assert climate.native_target_temperature == 25
    assert climate.native_temperature_unit == "°C"
    assert climate.min_temp == 16
    assert climate.max_temp == 31
    assert climate.target_temperature_step == 1
    assert HVACMode.HEAT not in climate.hvac_modes
    climate.coordinator.data = replace(climate.coordinator.data, power=True, mode="FAN")
    assert climate.hvac_mode == HVACMode.FAN_ONLY


@pytest.mark.parametrize(
    ("method", "args", "expected"),
    [
        ("async_turn_on", (), {"power": True}),
        ("async_turn_off", (), {"power": False}),
        ("async_set_hvac_mode", (HVACMode.COOL,), {"power": True, "mode": "COOL"}),
        ("async_set_hvac_mode", (HVACMode.OFF,), {"power": False}),
        ("async_set_fan_mode", ("HI",), {"fan": "HI"}),
        ("async_set_swing_mode", ("Swing",), {"vane": "Swing"}),
    ],
)
async def test_command(climate, method, args, expected):
    await getattr(climate, method)(*args)
    climate.coordinator.client.async_set.assert_awaited_once_with(**expected)
    climate.coordinator.async_set_updated_data.assert_called_once_with(
        climate.coordinator.data
    )


async def test_temperature_and_mode_are_one_command(climate):
    await climate.async_set_temperature(temperature=26, hvac_mode=HVACMode.DRY)
    climate.coordinator.client.async_set.assert_awaited_once_with(
        temperature=26, power=True, mode="DRY"
    )


async def test_failed_command_marks_unavailable(climate):
    climate.coordinator.client.async_set.side_effect = IfuWfError("offline")
    with pytest.raises(HomeAssistantError):
        await climate.async_turn_on()
    climate.coordinator.async_set_updated_data.assert_not_called()
    climate.coordinator.async_set_update_error.assert_called_once()


async def test_unsupported_mode(climate):
    with pytest.raises(HomeAssistantError):
        await climate.async_set_hvac_mode(HVACMode.HEAT)
    climate.coordinator.client.async_set.assert_not_called()
