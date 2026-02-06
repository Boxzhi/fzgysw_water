"""Sensor platform for the Fuzhou Public Water integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_APID, DOMAIN
from .coordinator import FzgyswWaterDataCoordinator


@dataclass(frozen=True, kw_only=True)
class FzgyswWaterSensorEntityDescription(SensorEntityDescription):
    key: str


ACCOUNT_DESCRIPTION = FzgyswWaterSensorEntityDescription(
    key="balance",
    name="余额",
    icon="mdi:water",
)

BILL_DESCRIPTION = FzgyswWaterSensorEntityDescription(
    key="bill",
    name="账单",
    icon="mdi:receipt",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: callable,
) -> None:
    """Set up sensors from config entry."""
    coordinator: FzgyswWaterDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            FzgyswWaterAccountSensor(coordinator, entry, ACCOUNT_DESCRIPTION),
            FzgyswWaterBillSensor(coordinator, entry, BILL_DESCRIPTION),
        ]
    )


class FzgyswWaterBaseSensor(
    CoordinatorEntity[FzgyswWaterDataCoordinator], SensorEntity
):
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: FzgyswWaterDataCoordinator,
        entry: ConfigEntry,
        description: FzgyswWaterSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)

        self.entity_description = description
        self._entry = entry

        account = coordinator.data.account if coordinator.data else {}
        account_id = account.get("yhbh") or entry.entry_id

        # 设置 unique_id
        self._attr_unique_id = f"fuzhou_water_{account_id}_{description.key}"

        # 设置显示名称（中文）
        if description.key == "balance":
            self._attr_name = f"抚州公用水务{account_id}余额"
        else:
            self._attr_name = f"抚州公用水务{account_id}账单"

        # ⭐ 强制设置 entity_id
        self.entity_id = f"sensor.fuzhou_water_{account_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the water account."""
        account = self.coordinator.data.account if self.coordinator.data else {}
        account_name = self._mask_account_name(account.get("yhmc"))
        address = account.get("yhdz") or "抚州公用水务"

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.data[CONF_APID])},
            manufacturer="抚州公用水务有限公司",
            name=address,
            model=f"户名：{account_name}",
        )

    @staticmethod
    def _mask_account_name(name: str | None) -> str:
        if not name:
            return "未知用户"
        return f"*{name[1:]}" if len(name) > 1 else "*"


class FzgyswWaterAccountSensor(FzgyswWaterBaseSensor):
    @property
    def native_value(self) -> str | None:
        account = self.coordinator.data.account if self.coordinator.data else None
        if not account:
            return None
        return account.get("xyyc")


class FzgyswWaterBillSensor(FzgyswWaterBaseSensor):
    @property
    def native_value(self) -> str | None:
        bill = self._latest_bill()
        if not bill:
            return None
        return bill.get("YSJE")

    def _latest_bill(self) -> dict[str, Any] | None:
        bills = self.coordinator.data.bills if self.coordinator.data else []
        if not bills:
            return None
        return max(bills, key=lambda item: item.get("CBNY", ""))
