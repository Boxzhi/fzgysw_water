"""Sensor platform for the Fuzhou Public Water integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FzgyswWaterDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            FzgyswWaterAccountSensor(coordinator, entry, ACCOUNT_DESCRIPTION),
            FzgyswWaterBillSensor(coordinator, entry, BILL_DESCRIPTION),
        ]
    )


# =========================================================
# Base
# =========================================================
class FzgyswWaterBaseSensor(CoordinatorEntity, SensorEntity):

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
        account_id = account.get("yhbh")

        unique_suffix = account_id or entry.entry_id

        # -------------------------
        # 唯一ID（必须）
        # -------------------------
        self._attr_unique_id = f"{DOMAIN}_{unique_suffix}_{description.key}"

        self.entity_id = f"sensor.fuzhou_water_{unique_suffix}_{description.key}"

        # UI名称
        self._attr_name = description.name

    # -----------------------------------------------------
    # 设备信息
    # -----------------------------------------------------
    @property
    def device_info(self) -> DeviceInfo:
        account = self.coordinator.data.account if self.coordinator.data else {}

        account_name = self._mask_account_name(account.get("yhmc"))
        account_id = account.get("yhbh") or "未知户号"
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


# =========================================================
# 余额
# =========================================================
class FzgyswWaterAccountSensor(FzgyswWaterBaseSensor):

    @property
    def native_value(self) -> str | None:
        account = self.coordinator.data.account if self.coordinator.data else None
        return account.get("xyyc") if account else None


# =========================================================
# 账单
# =========================================================
class FzgyswWaterBillSensor(FzgyswWaterBaseSensor):

    @property
    def native_value(self) -> str | None:
        account = self.coordinator.data.account if self.coordinator.data else None
        return account.get("zjje") if account else None
