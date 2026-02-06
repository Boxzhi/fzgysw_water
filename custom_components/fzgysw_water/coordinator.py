"""Data coordinator for the Fuzhou Public Water integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import base64
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
        apid_input = self._entry.data[CONF_APID]
        apid_raw, apid_encoded = self._derive_apid_pair(apid_input)
        account_id = self._entry.data.get(CONF_ACCOUNT_ID)
        try:
            account_info = await self._fetch_account_info(apid_encoded, apid_raw)
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
                bills = await self._fetch_bills(
                    apid_raw, apid_encoded, account_id, start, end
                )

            return FzgyswWaterData(account=account, bills=bills)
        except (ClientResponseError, ValueError, json.JSONDecodeError) as err:
            raise UpdateFailed(f"API error: {err}") from err

    async def _fetch_account_info(
        self, apid_encoded: str, apid_raw: str
    ) -> list[dict[str, Any]]:
        """Fetch account info from the API."""
        url = f"{BASE_URL}/{ACCOUNT_ENDPOINT}"
        params = {
            "apid": apid_encoded,
            "Search": "TGlzdA==",
        }
        async with self._session.get(
            url,
            params=params,
            headers=self._build_headers(
                referer=(
                    "http://www.fzgysw.cn/weixincx/mnewmenu/FrmZXJF.aspx"
                    f"?userid={apid_raw}"
                )
            ),
        ) as resp:
            resp.raise_for_status()
            raw = await resp.read()
            text = raw.decode("gb2312", errors="ignore")
            return self._parse_json_array(text)

    async def _fetch_bills(
        self,
        apid_raw: str,
        apid_encoded: str,
        account_id: str,
        start: str,
        end: str,
    ) -> list[dict[str, Any]]:
        """Fetch bill data from the API."""
        url = f"{BASE_URL}/{BILL_ENDPOINT}"
        params = {
            "yhbh": account_id,
            "txtStart": start,
            "txtEnd": end,
            "Search": "Select",
            "apid": apid_raw,
        }
        async with self._session.post(
            url,
            params=params,
            headers=self._build_headers(
                referer=(
                    "http://www.fzgysw.cn/weixincx/mnewmenu/FrmYscxMX.aspx"
                    f"?YHBH={account_id}&txtStart={start}&txtEnd={end}&apid={apid_encoded}"
                ),
                origin="http://www.fzgysw.cn",
            ),
        ) as resp:
            resp.raise_for_status()
            payload = await resp.json(content_type=None)

        if not payload.get("Success"):
            return []

        data = payload.get("Data") or "[]"
        return self._parse_json_array(data, log_context="bill")

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

    @staticmethod
    def _parse_json_array(
        text: str, log_context: str = "account"
    ) -> list[dict[str, Any]]:
        """Parse a JSON array from raw text, tolerating wrapped content."""
        cleaned = text.lstrip("\ufeff").strip()
        if not cleaned:
            return []

        if cleaned.startswith("<"):
            _LOGGER.warning("Received HTML response for %s payload", log_context)
            return []

        if cleaned.startswith("{") and cleaned.endswith("}"):
            try:
                payload = json.loads(cleaned)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                nested = payload.get("Data")
                if isinstance(nested, str):
                    return self._parse_json_array(nested, log_context=log_context)
                return []

        if cleaned.startswith("[") and cleaned.endswith("]"):
            return json.loads(cleaned)

        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end != -1 and end > start:
            snippet = cleaned[start : end + 1]
            return json.loads(snippet)

        raise ValueError(f"Unexpected {log_context} payload: {cleaned[:80]}")

    @staticmethod
    def _derive_apid_pair(apid_input: str) -> tuple[str, str]:
        """Return raw APID and base64-encoded APID for API calls."""
        apid_input = apid_input.strip()
        try:
            padded = apid_input + "=" * (-len(apid_input) % 4)
            decoded = base64.b64decode(padded.encode(), validate=False)
            apid_raw = decoded.decode("utf-8")
            if not apid_raw:
                raise ValueError("empty decode")
        except (ValueError, UnicodeDecodeError):
            apid_raw = apid_input

        apid_encoded = base64.b64encode(apid_raw.encode("utf-8")).decode("utf-8")
        return apid_raw, apid_encoded

    @staticmethod
    def _build_headers(referer: str, origin: str | None = None) -> dict[str, str]:
        """Build request headers to match the expected WeChat flow."""
        headers = {
            "Accept": "*/*",
            "Referer": referer,
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 15_4_1 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
                "MicroMessenger/8.0.68(0x18004431) NetType/4G Language/zh_CN"
            ),
            "X-Requested-With": "XMLHttpRequest",
        }
        if origin:
            headers["Origin"] = origin
        return headers
