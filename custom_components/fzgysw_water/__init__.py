"""The Fuzhou Public Water integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN
from .coordinator import FzgyswWaterDataCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Fuzhou Public Water from a config entry."""
    coordinator = FzgyswWaterDataCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    account = coordinator.data.account if coordinator.data else None
    account_id = account.get("yhbh") if account else None
    if account_id:
        desired_title = f"抚州公用水务 - {account_id}"
        if entry.title != desired_title:
            hass.config_entries.async_update_entry(entry, title=desired_title)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
