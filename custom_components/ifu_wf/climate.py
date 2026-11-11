"""Climate entity for a local IFU-WF module."""

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import IfuWfError
from .const import DOMAIN
from .coordinator import IfuWfConfigEntry, IfuWfCoordinator

MODE_TO_HA = {
    "HEAT": HVACMode.HEAT,
    "DRY": HVACMode.DRY,
    "COOL": HVACMode.COOL,
    "FAN": HVACMode.FAN_ONLY,
    "AUTO": HVACMode.AUTO,
}
HA_TO_MODE = {value: key for key, value in MODE_TO_HA.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IfuWfConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([IfuWfClimate(entry.runtime_data)])


class IfuWfClimate(CoordinatorEntity[IfuWfCoordinator], ClimateEntity):
    """Expose only capabilities advertised by this indoor unit."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: IfuWfCoordinator) -> None:
        super().__init__(coordinator)
        state = coordinator.data
        caps = state.capabilities
        self._attr_unique_id = state.device_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, state.device_id)},
            name=state.device_id,
            manufacturer="Electronic Technology Research",
            model="IFU-WF",
            configuration_url=f"http://{coordinator.client.host}/login/ifuwf.htm",
        )
        self._attr_hvac_modes = [
            HVACMode.OFF,
            *(MODE_TO_HA[mode] for mode in caps.modes),
        ]
        self._attr_fan_modes = list(caps.fans)
        self._attr_swing_modes = list(caps.vanes)
        self._attr_min_temp = min(caps.temperatures)
        self._attr_max_temp = max(caps.temperatures)
        self._attr_target_temperature_step = caps.temperatures[1] - caps.temperatures[0]
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        if caps.vanes:
            self._attr_supported_features |= ClimateEntityFeature.SWING_MODE

    @property
    def hvac_mode(self) -> HVACMode:
        state = self.coordinator.data
        return MODE_TO_HA[state.mode] if state.power else HVACMode.OFF

    @property
    def native_current_temperature(self) -> float:
        return self.coordinator.data.current_temperature

    @property
    def native_target_temperature(self) -> float:
        return self.coordinator.data.target_temperature

    @property
    def fan_mode(self) -> str:
        return self.coordinator.data.fan

    @property
    def swing_mode(self) -> str | None:
        state = self.coordinator.data
        return state.vane if state.capabilities.vanes else None

    async def _async_command(self, **settings: Any) -> None:
        try:
            state = await self.coordinator.client.async_set(**settings)
        except IfuWfError as err:
            self.coordinator.async_set_update_error(err)
            raise HomeAssistantError(str(err)) from err
        self.coordinator.async_set_updated_data(state)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode not in self.hvac_modes:
            raise HomeAssistantError("Unsupported HVAC mode")
        if hvac_mode == HVACMode.OFF:
            await self._async_command(power=False)
        else:
            await self._async_command(power=True, mode=HA_TO_MODE[hvac_mode])

    async def async_turn_on(self) -> None:
        await self._async_command(power=True)

    async def async_turn_off(self) -> None:
        await self._async_command(power=False)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        settings = {"temperature": kwargs[ATTR_TEMPERATURE]}
        if "hvac_mode" in kwargs:
            mode = kwargs["hvac_mode"]
            if mode not in self.hvac_modes:
                raise HomeAssistantError("Unsupported HVAC mode")
            settings["power"] = mode != HVACMode.OFF
            if mode != HVACMode.OFF:
                settings["mode"] = HA_TO_MODE[mode]
        await self._async_command(**settings)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self._async_command(fan=fan_mode)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        if not self.swing_modes:
            raise HomeAssistantError("Vane control is unavailable")
        await self._async_command(vane=swing_mode)
