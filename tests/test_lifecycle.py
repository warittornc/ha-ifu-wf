"""Config entry setup, unload, and coordinator failure handling."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ifu_wf import PLATFORMS, async_setup_entry, async_unload_entry
from custom_components.ifu_wf.api import IfuWfError
from custom_components.ifu_wf.coordinator import IfuWfCoordinator


async def test_setup_refreshes_before_platform_setup():
    hass = Mock()
    entry = Mock(data={"host": "ac.local"})
    coordinator = Mock()
    coordinator.async_config_entry_first_refresh = AsyncMock()

    async def forward(actual_entry, platforms):
        coordinator.async_config_entry_first_refresh.assert_awaited_once()
        assert actual_entry.runtime_data is coordinator
        assert platforms == PLATFORMS

    hass.config_entries.async_forward_entry_setups = AsyncMock(side_effect=forward)
    with (
        patch("custom_components.ifu_wf.async_get_clientsession"),
        patch("custom_components.ifu_wf.IfuWfCoordinator", return_value=coordinator),
    ):
        assert await async_setup_entry(hass, entry)
    hass.config_entries.async_forward_entry_setups.assert_awaited_once()


async def test_first_refresh_failure_prevents_entities():
    hass = Mock()
    entry = Mock(data={"host": "ac.local"})
    coordinator = Mock()
    coordinator.async_config_entry_first_refresh = AsyncMock(
        side_effect=ConfigEntryNotReady
    )
    with (
        patch("custom_components.ifu_wf.async_get_clientsession"),
        patch("custom_components.ifu_wf.IfuWfCoordinator", return_value=coordinator),
    ):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)
    hass.config_entries.async_forward_entry_setups.assert_not_called()


async def test_unload():
    hass = Mock()
    entry = Mock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    assert await async_unload_entry(hass, entry)
    hass.config_entries.async_unload_platforms.assert_awaited_once_with(
        entry, PLATFORMS
    )


async def test_coordinator_failure_and_recovery(state):
    coordinator = Mock()
    coordinator.client.async_get_state = AsyncMock(
        side_effect=[IfuWfError("offline"), state]
    )
    with pytest.raises(UpdateFailed):
        await IfuWfCoordinator._async_update_data(coordinator)
    assert await IfuWfCoordinator._async_update_data(coordinator) == state


async def test_auth_failure_requests_reauthentication():
    from homeassistant.exceptions import ConfigEntryAuthFailed

    from custom_components.ifu_wf.api import IfuWfAuthError

    coordinator = Mock()
    coordinator.client.async_get_state = AsyncMock(side_effect=IfuWfAuthError)
    with pytest.raises(ConfigEntryAuthFailed):
        await IfuWfCoordinator._async_update_data(coordinator)
