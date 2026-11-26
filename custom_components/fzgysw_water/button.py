"""Full refresh button for Fuzhou Public Water."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_APID, DOMAIN
from .coordinator import FzgyswWaterDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FzgyswWaterRefreshButton(coordinator, entry)])


class FzgyswWaterRefreshButton(ButtonEntity):
    """Refresh both account and bill data."""

    _attr_has_entity_name = True
    _attr_name = "刷新数据"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: FzgyswWaterDataCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        account = coordinator.data.account if coordinator.data else None
        suffix = (account or {}).get("yhbh") or entry.entry_id
        self._attr_unique_id = f"{DOMAIN}_{suffix}_refresh"
        self.entity_id = f"button.fuzhou_water_{suffix}_refresh"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.data[CONF_APID])})

    async def async_press(self) -> None:
        await self._coordinator.async_refresh_all()
