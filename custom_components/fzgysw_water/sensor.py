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
    """Description for Fzgysw Water sensor."""

    key: str


ACCOUNT_DESCRIPTION = FzgyswWaterSensorEntityDescription(
    key="account",
    name="Water Balance",
    icon="mdi:water",
)

BILL_DESCRIPTION = FzgyswWaterSensorEntityDescription(
    key="bill",
    name="Latest Water Bill",
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


class FzgyswWaterBaseSensor(CoordinatorEntity[FzgyswWaterDataCoordinator], SensorEntity):
    """Base sensor for Fzgysw Water."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: FzgyswWaterDataCoordinator,
        entry: ConfigEntry,
        description: FzgyswWaterSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        account = coordinator.data.account if coordinator.data else {}
        account_id = account.get("yhbh") if account else None
        unique_suffix = account_id or entry.entry_id
        self._attr_unique_id = f"{unique_suffix}-{description.key}"
        base_name = f"抚州自来水{account_id}" if account_id else "抚州自来水"
        if description.key == "account":
            self._attr_name = f"{base_name}余额"
        else:
            self._attr_name = f"{base_name}账单"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the water account."""
        account = self.coordinator.data.account if self.coordinator.data else {}
        account_name = self._mask_account_name(account.get("yhmc"))
        account_id = account.get("yhbh") or "未知户号"
        address = account.get("yhdz") or "抚州公用水务"

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.data[CONF_APID])},
            manufacturer="抚州公用水务有限公司",
            name=f"户号：{account_name} - {account_id}",
            model=address,
        )

    @staticmethod
    def _mask_account_name(name: str | None) -> str:
        """Mask the first character of the account name."""
        if not name:
            return "未知用户"
        return f"*{name[1:]}" if len(name) > 1 else "*"


class FzgyswWaterAccountSensor(FzgyswWaterBaseSensor):
    """Sensor for water account balance."""

    @property
    def native_value(self) -> str | None:
        account = self.coordinator.data.account if self.coordinator.data else None
        if not account:
            return None
        return account.get("xyyc")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        account = self.coordinator.data.account if self.coordinator.data else None
        if not account:
            return None
        return {
            "account_id": account.get("yhbh"),
            "account_name": account.get("yhmc"),
            "address": account.get("yhdz"),
            "total_due": account.get("zjje"),
            "total_paid": account.get("zlje"),
            "current_balance": account.get("xyyc"),
            "arrears": account.get("yjje"),
            "amount_due": account.get("fkje"),
        }


class FzgyswWaterBillSensor(FzgyswWaterBaseSensor):
    """Sensor for latest water bill."""

    @property
    def native_value(self) -> str | None:
        bill = self._latest_bill()
        if not bill:
            return None
        return bill.get("YSJE")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        bills = self.coordinator.data.bills if self.coordinator.data else []
        bill = self._latest_bill()
        if not bill:
            return None
        return {
            "billing_month": bill.get("CBNY"),
            "read_date": bill.get("CBRQ"),
            "start_meter": bill.get("SYBS"),
            "end_meter": bill.get("BYBS"),
            "usage": bill.get("FBYSL"),
            "charge": bill.get("ZJJE"),
            "amount_due": bill.get("YSJE"),
            "late_fee": bill.get("WYJ"),
            "surcharge": bill.get("WSJE"),
            "payment_status": bill.get("SFZT"),
            "payment_date": bill.get("SFRQ"),
            "recent_bills": bills,
        }

    def _latest_bill(self) -> dict[str, Any] | None:
        bills = self.coordinator.data.bills if self.coordinator.data else []
        if not bills:
            return None
        return max(bills, key=lambda item: item.get("CBNY", ""))
