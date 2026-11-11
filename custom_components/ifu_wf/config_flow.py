"""Handle setup and credential changes for IFU-WF."""

from typing import Any

import probatio
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import IfuWfAuthError, IfuWfClient, IfuWfError, normalize_host
from .const import DOMAIN, NAME


class IfuWfConfigFlow(ConfigFlow, domain=DOMAIN):
    """Validate credentials before saving or replacing an entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_configure("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_configure(
            "reconfigure", user_input, self._get_reconfigure_entry()
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_configure(
            "reauth_confirm", user_input, self._get_reauth_entry()
        )

    async def _async_configure(
        self,
        step: str,
        user_input: dict[str, Any] | None,
        entry: ConfigEntry | None = None,
    ) -> ConfigFlowResult:
        errors = {}
        defaults = entry.data if entry else {}
        if user_input is not None:
            try:
                host = normalize_host(
                    user_input.get(CONF_HOST, defaults.get(CONF_HOST, ""))
                )
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
            else:
                data = {CONF_HOST: host}
                username = user_input.get(CONF_USERNAME, "")
                password = user_input.get(CONF_PASSWORD, "")
                if username or password:
                    data.update({CONF_USERNAME: username, CONF_PASSWORD: password})
                if not entry:
                    self._async_abort_entries_match({CONF_HOST: host})
                try:
                    client = IfuWfClient(
                        async_get_clientsession(self.hass), host, username, password
                    )
                    state = await client.async_get_state()
                except IfuWfAuthError:
                    errors["base"] = "invalid_auth"
                except IfuWfError, TimeoutError:
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(state.device_id)
                    if entry:
                        self._abort_if_unique_id_mismatch()
                        return self.async_update_reload_and_abort(entry, data=data)
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                    return self.async_create_entry(title=f"{NAME} {host}", data=data)
        schema = {}
        if step != "reauth_confirm":
            schema[
                probatio.Required(CONF_HOST, default=defaults.get(CONF_HOST, ""))
            ] = str
        schema[
            probatio.Optional(CONF_USERNAME, default=defaults.get(CONF_USERNAME, ""))
        ] = str
        schema[probatio.Optional(CONF_PASSWORD)] = TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
        return self.async_show_form(
            step_id=step, data_schema=probatio.Schema(schema), errors=errors
        )
