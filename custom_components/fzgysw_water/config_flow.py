"""Config flow for the Fuzhou Public Water integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_ACCOUNT_ID, CONF_APID, DEFAULT_NAME, DOMAIN


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input."""
    if not data[CONF_APID].strip():
        raise ValueError("APID is required")
    return {"title": DEFAULT_NAME}


class FzgyswWaterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fuzhou Public Water."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _validate_input(self.hass, user_input)
            except ValueError:
                errors["base"] = "invalid_auth"
            else:
                await self.async_set_unique_id(user_input[CONF_APID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_APID): str,
                vol.Optional(CONF_ACCOUNT_ID): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
