"""Data coordinator for the Fuzhou Public Water integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import json
import logging
from typing import Any

from aiohttp import ClientResponseError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ACCOUNT_ENDPOINT,
    BASE_URL,
    BILL_ENDPOINT,
    COORDINATOR_UPDATE_INTERVAL,
    CONF_ACCOUNT_ID,
    CONF_APID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class FzgyswWaterData:
    """Container for water account and bill data."""

    account: dict[str, Any] | None
    bills: list[dict[str, Any]]


class FzgyswWaterDataCoordinator(DataUpdateCoordinator[FzgyswWaterData]):
    """Coordinator to manage fetching data from Fuzhou Public Water."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=COORDINATOR_UPDATE_INTERVAL),
        )
        self._entry = entry
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> FzgyswWaterData:
        """Fetch data from the API endpoints."""
        apid = self._entry.data[CONF_APID]
        account_id = self._entry.data.get(CONF_ACCOUNT_ID)
        try:
            account_info = await self._fetch_account_info(apid)
            if not account_info:
                raise UpdateFailed("No account data returned")
            account = account_info[0]
            if account_id:
                account = next(
                    (item for item in account_info if item.get("yhbh") == account_id),
                    account,
                )
            else:
                account_id = account.get("yhbh")

            bills = []
            if account_id:
                start, end = self._compute_month_range()
                bills = await self._fetch_bills(apid, account_id, start, end)

            return FzgyswWaterData(account=account, bills=bills)
        except (ClientResponseError, ValueError, json.JSONDecodeError) as err:
            raise UpdateFailed(f"API error: {err}") from err

    async def _fetch_account_info(self, apid: str) -> list[dict[str, Any]]:
        """Fetch account info from the API."""
        url = f"{BASE_URL}/{ACCOUNT_ENDPOINT}"
        params = {
            "apid": apid,
            "Search": "TGlzdA==",
        }
        async with self._session.get(url, params=params) as resp:
            resp.raise_for_status()
            raw = await resp.read()
            text = raw.decode("gb2312", errors="ignore")
            return json.loads(text)

    async def _fetch_bills(
        self, apid: str, account_id: str, start: str, end: str
    ) -> list[dict[str, Any]]:
        """Fetch bill data from the API."""
        url = f"{BASE_URL}/{BILL_ENDPOINT}"
        params = {
            "yhbh": account_id,
            "txtStart": start,
            "txtEnd": end,
            "Search": "Select",
            "apid": apid,
        }
        async with self._session.post(url, params=params) as resp:
            resp.raise_for_status()
            payload = await resp.json(content_type=None)

        if not payload.get("Success"):
            return []

        data = payload.get("Data") or "[]"
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            _LOGGER.warning("Unable to decode bill data payload")
            return []

    @staticmethod
    def _compute_month_range(today: date | None = None) -> tuple[str, str]:
        """Compute YYYYMM range for the most recent 12 months."""
        current = today or date.today()
        end = current.strftime("%Y%m")

        year = current.year
        month = current.month
        for _ in range(11):
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        start = f"{year}{month:02d}"
        return start, end
