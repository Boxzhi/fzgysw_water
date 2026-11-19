"""Data coordinator for the Fuzhou Public Water integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import base64
import json
import logging
from typing import Any

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ACCOUNT_ENDPOINT,
    BASE_URL,
    BILL_ENDPOINT,
    BILL_UPDATE_INTERVAL,
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
    account_last_successful_fetch: datetime | None
    bill_last_successful_fetch: datetime | None


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
        """Refresh account every six hours, bills every twelve hours."""
        apid_input = self._entry.data[CONF_APID]
        apid_raw, apid_encoded = self._derive_apid_pair(apid_input)
        configured_id = self._entry.data.get(CONF_ACCOUNT_ID)

        previous = self.data
        account = previous.account if previous else None
        bills = previous.bills if previous else []
        account_fetched = previous.account_last_successful_fetch if previous else None
        bill_fetched = previous.bill_last_successful_fetch if previous else None
        account_error: Exception | None = None

        try:
            items = await self._fetch_account_info(apid_encoded, apid_raw)
            if not isinstance(items, list) or not items or any(not isinstance(item, dict) for item in items):
                raise UpdateFailed("No valid account data returned")
            updated_account = items[0]
            if configured_id:
                updated_account = next(
                    (item for item in items if item.get("yhbh") == configured_id),
                    updated_account,
                )
            if not updated_account.get("yhbh"):
                raise UpdateFailed("No water account ID returned")

            # Never reuse another account's bill cache.
            if account and updated_account["yhbh"] != account.get("yhbh"):
                bills = []
                bill_fetched = None
            account = updated_account
            account_fetched = datetime.now(timezone.utc)
        except (ClientError, TimeoutError, ValueError, UpdateFailed) as err:
            account_error = err
            if not account:
                raise UpdateFailed("Unable to fetch initial water account data") from err
            _LOGGER.warning(
                "Water account refresh failed (%s); retaining cached account",
                type(err).__name__,
            )

        account_id = account.get("yhbh")
        if not account_id:
            raise UpdateFailed("No water account ID available")

        bill_due = (
            bill_fetched is None
            or datetime.now(timezone.utc) - bill_fetched
            >= timedelta(seconds=BILL_UPDATE_INTERVAL)
        )
        bill_succeeded = False
        if bill_due:
            try:
                start, end = self._compute_month_range()
                updated_bills = await self._fetch_bills(
                    apid_raw, apid_encoded, account_id, start, end
                )
                bills = updated_bills
                bill_fetched = datetime.now(timezone.utc)
                bill_succeeded = True
            except (ClientError, TimeoutError, ValueError, UpdateFailed) as err:
                _LOGGER.warning(
                    "Water bill refresh failed (%s); keeping previous bills for retry",
                    type(err).__name__,
                )
                if account_error:
                    raise UpdateFailed("Both water API refreshes failed") from err

        # With no successful endpoint, keep the coordinator's previous snapshot.
        if account_error and not bill_succeeded:
            raise UpdateFailed("Water account refresh failed") from account_error

        return FzgyswWaterData(
            account=account,
            bills=bills,
            account_last_successful_fetch=account_fetched,
            bill_last_successful_fetch=bill_fetched,
        )

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

        if not isinstance(payload, dict):
            raise UpdateFailed("Invalid bill API response")

        success = payload.get("Success")
        if success is not True and success != 1 and str(success).strip().lower() not in ("true", "1"):
            raise UpdateFailed("Bill API reported failure")

        # A successful request with an empty array is valid: no bills exist.
        # Missing/malformed data or an HTML login/error page is not a success.
        if "Data" not in payload:
            raise UpdateFailed("Bill API response is missing Data")
        data = payload["Data"]
        if data is None:
            return []
        if isinstance(data, list):
            bills = data
        elif isinstance(data, str):
            if data.lstrip("\ufeff").strip().startswith("<"):
                raise UpdateFailed("Bill API returned HTML instead of bills")
            bills = self._parse_json_array(data, log_context="bill")
        else:
            raise UpdateFailed("Invalid bill API data format")
        if any(not isinstance(item, dict) for item in bills):
            raise UpdateFailed("Invalid bill API record format")
        return bills

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
