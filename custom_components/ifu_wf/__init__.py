"""Set up the IFU-WF integration."""

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IfuWfClient
from .coordinator import IfuWfConfigEntry, IfuWfCoordinator

PLATFORMS = [Platform.CLIMATE]


async def async_setup_entry(hass: HomeAssistant, entry: IfuWfConfigEntry) -> bool:
    """Validate the first update before forwarding platform setup."""
    client = IfuWfClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data.get(CONF_USERNAME, ""),
        entry.data.get(CONF_PASSWORD, ""),
    )
    coordinator = IfuWfCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IfuWfConfigEntry) -> bool:
    """Unload entities; Home Assistant owns the HTTP session."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
