"""Exercise user-visible setup paths without real hardware."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ifu_wf.api import IfuWfError
from custom_components.ifu_wf.config_flow import IfuWfConfigFlow


@pytest.fixture
def flow() -> IfuWfConfigFlow:
    flow = IfuWfConfigFlow()
    flow.hass = Mock()
    flow.hass.config_entries.async_entries.return_value = []
    return flow


async def test_user_form(flow: IfuWfConfigFlow) -> None:
    result = await flow.async_step_user()
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_invalid_host(flow: IfuWfConfigFlow) -> None:
    result = await flow.async_step_user({CONF_HOST: "http://192.168.1.60/"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "invalid_host"}


async def test_create_entry(flow: IfuWfConfigFlow, state) -> None:
    flow.context = {"source": "user"}
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = None
    with (
        patch("custom_components.ifu_wf.config_flow.async_get_clientsession"),
        patch.object(flow, "_async_in_progress", return_value=[]),
        patch(
            "custom_components.ifu_wf.api.IfuWfClient.async_get_state",
            new=AsyncMock(return_value=state),
        ),
    ):
        result = await flow.async_step_user({CONF_HOST: "192.168.1.60"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "192.168.1.60"}
    assert flow.unique_id == state.device_id


async def test_connection_failure_keeps_form(flow: IfuWfConfigFlow) -> None:
    with (
        patch("custom_components.ifu_wf.config_flow.async_get_clientsession"),
        patch(
            "custom_components.ifu_wf.api.IfuWfClient.async_get_state",
            new=AsyncMock(side_effect=IfuWfError("offline")),
        ),
    ):
        result = await flow.async_step_user({CONF_HOST: "192.168.1.60"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_device_at_different_address(flow, state):
    from homeassistant.data_entry_flow import AbortFlow

    flow.context = {"source": "user"}
    existing = Mock(data={CONF_HOST: "old.local"}, source="user")
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = existing
    flow.hass.config_entries.async_update_entry.return_value = False
    with (
        patch("custom_components.ifu_wf.config_flow.async_get_clientsession"),
        patch.object(flow, "_async_in_progress", return_value=[]),
        patch(
            "custom_components.ifu_wf.api.IfuWfClient.async_get_state",
            new=AsyncMock(return_value=state),
        ),
        pytest.raises(AbortFlow, match="already_configured"),
    ):
        await flow.async_step_user({CONF_HOST: "new.local"})
    flow.hass.config_entries.async_update_entry.assert_called_once_with(
        existing, data={CONF_HOST: "new.local"}
    )


async def test_auth_error(flow):
    from custom_components.ifu_wf.api import IfuWfAuthError

    with (
        patch("custom_components.ifu_wf.config_flow.async_get_clientsession"),
        patch(
            "custom_components.ifu_wf.api.IfuWfClient.async_get_state",
            new=AsyncMock(side_effect=IfuWfAuthError),
        ),
    ):
        result = await flow.async_step_user({CONF_HOST: "ac.local"})
    assert result["errors"] == {"base": "invalid_auth"}


async def test_credentials_saved_only_after_validation(flow, state):
    flow.context = {"source": "user"}
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = None
    data = {CONF_HOST: "ac.local", "username": "test-user", "password": "test-password"}
    with (
        patch("custom_components.ifu_wf.config_flow.async_get_clientsession"),
        patch.object(flow, "_async_in_progress", return_value=[]),
        patch("custom_components.ifu_wf.config_flow.IfuWfClient") as client,
    ):
        client.return_value.async_get_state = AsyncMock(return_value=state)
        result = await flow.async_step_user(data)
        assert client.call_args.args[1:] == ("ac.local", "test-user", "test-password")
    assert result["data"] == data


@pytest.mark.parametrize("step", ["reconfigure", "reauth_confirm"])
async def test_existing_credentials_updated_in_place(flow, state, step):
    flow.context = {"source": "reconfigure" if step == "reconfigure" else "reauth"}
    entry = Mock(data={CONF_HOST: "ac.local"}, unique_id=state.device_id)
    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=entry),
        patch.object(flow, "_get_reauth_entry", return_value=entry),
        patch.object(flow, "_async_in_progress", return_value=[]),
        patch.object(
            flow,
            "async_update_reload_and_abort",
            return_value={"type": FlowResultType.ABORT},
        ) as update,
        patch("custom_components.ifu_wf.config_flow.async_get_clientsession"),
        patch("custom_components.ifu_wf.config_flow.IfuWfClient") as client,
    ):
        client.return_value.async_get_state = AsyncMock(return_value=state)
        data = {"username": "test-user", "password": "test-password"}
        await getattr(flow, "async_step_" + step)(data)
        update.assert_called_once_with(entry, data={CONF_HOST: "ac.local", **data})
