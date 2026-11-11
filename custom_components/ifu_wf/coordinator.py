"""Coordinate polling of a single IFU-WF device."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeviceState, IfuWfAuthError, IfuWfClient, IfuWfError
from .const import DOMAIN

type IfuWfConfigEntry = ConfigEntry[IfuWfCoordinator]


class IfuWfCoordinator(DataUpdateCoordinator[DeviceState]):
    """Fetch state for all entities using one request per poll."""

    def __init__(
        self, hass: HomeAssistant, entry: IfuWfConfigEntry, client: IfuWfClient
    ) -> None:
        """Initialize shared polling for this device."""
        super().__init__(
            hass,
            logging.getLogger(__name__),
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
            always_update=False,
        )
        self.client = client

    async def _async_update_data(self) -> DeviceState:
        """Translate protocol failures into Home Assistant availability."""
        try:
            return await self.client.async_get_state()
        except IfuWfAuthError as err:
            raise ConfigEntryAuthFailed("Device credentials are invalid") from err
        except (IfuWfError, TimeoutError) as err:
            raise UpdateFailed(str(err)) from err
