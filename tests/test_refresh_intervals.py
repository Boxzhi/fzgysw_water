"""Offline regression tests for split six-hour/twelve-hour water API polling."""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))


def stub(name, **attributes):
    module = types.ModuleType(name)
    module.__dict__.update(attributes)
    if name in (
        "homeassistant", "homeassistant.helpers", "homeassistant.components"
    ):
        module.__path__ = []
    sys.modules[name] = module
    return module


class DataUpdateCoordinator:
    def __init__(self, *args, **kwargs):
        self.data = None
        self.update_interval = kwargs["update_interval"]
        self._refresh_lock = asyncio.Lock()

    async def async_refresh(self):
        async with self._refresh_lock:
            try:
                self.data = await self._async_update_data()
            except UpdateFailed:
                pass

    @classmethod
    def __class_getitem__(cls, item):
        return cls


class UpdateFailed(Exception):
    pass


class CoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator


@dataclass(frozen=True, kw_only=True)
class SensorEntityDescription:
    key: str
    name: str
    icon: str


stub("aiohttp", ClientError=type("ClientError", (Exception,), {}))
stub("homeassistant")
stub("homeassistant.config_entries", ConfigEntry=object)
stub("homeassistant.core", HomeAssistant=object)
stub("homeassistant.exceptions", HomeAssistantError=type("HomeAssistantError", (Exception,), {}))
stub("homeassistant.helpers")
stub("homeassistant.helpers.aiohttp_client", async_get_clientsession=lambda hass: None)
stub("homeassistant.helpers.update_coordinator",
     DataUpdateCoordinator=DataUpdateCoordinator,
     UpdateFailed=UpdateFailed,
     CoordinatorEntity=CoordinatorEntity)
stub("homeassistant.helpers.entity", DeviceInfo=dict)
stub("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
stub("homeassistant.components")
stub("homeassistant.components.button", ButtonEntity=type("ButtonEntity", (), {}))
stub("homeassistant.components.sensor",
     SensorEntity=type("SensorEntity", (), {}),
     SensorEntityDescription=SensorEntityDescription)

from fzgysw_water.const import ARREARS_UPDATE_INTERVAL, BILL_UPDATE_INTERVAL, COORDINATOR_UPDATE_INTERVAL
from fzgysw_water.coordinator import FzgyswWaterDataCoordinator, HomeAssistantError
from fzgysw_water.button import FzgyswWaterRefreshButton
from fzgysw_water.sensor import (
    ACCOUNT_DESCRIPTION, BILL_DESCRIPTION,
    FzgyswWaterAccountSensor, FzgyswWaterBillSensor,
)


def make_coordinator():
    entry = SimpleNamespace(data={"apid": "example-apid"}, entry_id="test")
    coordinator = FzgyswWaterDataCoordinator(None, entry)
    coordinator._fetch_account_info = AsyncMock(
        return_value=[{"yhbh": "001", "xyyc": "12.5"}]
    )
    coordinator._fetch_bills = AsyncMock(
        return_value=[{"CBNY": "202611", "ZJJE": "30.6"}]
    )
    return coordinator, entry


class TestWaterRefresh(unittest.IsolatedAsyncioTestCase):
    async def test_intervals_and_independent_timestamps(self):
        coordinator, entry = make_coordinator()
        self.assertEqual(COORDINATOR_UPDATE_INTERVAL, 6 * 3600)
        self.assertEqual(BILL_UPDATE_INTERVAL, 12 * 3600)
        self.assertEqual(coordinator.update_interval, timedelta(hours=6))

        first = await coordinator._async_update_data()
        coordinator.data = first
        self.assertEqual(coordinator._fetch_account_info.await_count, 1)
        self.assertEqual(coordinator._fetch_bills.await_count, 1)
        self.assertIsNotNone(first.account_last_successful_fetch)
        self.assertIsNotNone(first.bill_last_successful_fetch)

        # Simulate the next six-hour coordinator tick: only the account is due.
        prior_bill_time = datetime.now(timezone.utc) - timedelta(hours=6)
        first.bill_last_successful_fetch = prior_bill_time
        second = await coordinator._async_update_data()
        coordinator.data = second
        self.assertEqual(coordinator._fetch_account_info.await_count, 2)
        self.assertEqual(coordinator._fetch_bills.await_count, 1)
        self.assertEqual(second.bill_last_successful_fetch, prior_bill_time)

        balance = FzgyswWaterAccountSensor(
            coordinator, entry, ACCOUNT_DESCRIPTION
        )
        bill = FzgyswWaterBillSensor(coordinator, entry, BILL_DESCRIPTION)
        self.assertEqual(
            balance.extra_state_attributes["last_successful_fetch"],
            second.account_last_successful_fetch.isoformat(),
        )
        self.assertEqual(
            bill.extra_state_attributes["last_successful_fetch"],
            prior_bill_time.isoformat(),
        )

        # After twelve hours, both APIs must be called again.
        second.bill_last_successful_fetch = (
            datetime.now(timezone.utc) - timedelta(hours=12, seconds=1)
        )
        third = await coordinator._async_update_data()
        self.assertEqual(coordinator._fetch_account_info.await_count, 3)
        self.assertEqual(coordinator._fetch_bills.await_count, 2)
        self.assertGreater(third.bill_last_successful_fetch, prior_bill_time)

    async def test_bill_failure_keeps_previous_bills_and_retries(self):
        coordinator, _ = make_coordinator()
        first = await coordinator._async_update_data()
        old_bill_time = datetime.now(timezone.utc) - timedelta(hours=13)
        first.bill_last_successful_fetch = old_bill_time
        coordinator.data = first
        coordinator._fetch_bills.side_effect = UpdateFailed("bill endpoint failed")
        second = await coordinator._async_update_data()
        self.assertEqual(second.bills, first.bills)
        self.assertEqual(second.bill_last_successful_fetch, old_bill_time)
        self.assertGreaterEqual(
            second.account_last_successful_fetch,
            first.account_last_successful_fetch,
        )
        coordinator.data = second
        coordinator._fetch_bills.side_effect = None
        third = await coordinator._async_update_data()
        self.assertEqual(coordinator._fetch_bills.await_count, 2)
        self.assertEqual(third.bill_last_successful_fetch, old_bill_time)
        coordinator.data = third
        coordinator._bill_retry_after = datetime.now(timezone.utc) - timedelta(seconds=1)
        fourth = await coordinator._async_update_data()
        self.assertEqual(coordinator._fetch_bills.await_count, 3)
        self.assertGreater(fourth.bill_last_successful_fetch, old_bill_time)

    async def test_balance_failure_does_not_block_due_bill(self):
        coordinator, _ = make_coordinator()
        first = await coordinator._async_update_data()
        first.bill_last_successful_fetch = (
            datetime.now(timezone.utc) - timedelta(hours=13)
        )
        coordinator.data = first
        coordinator._fetch_account_info.side_effect = TimeoutError("offline")
        next_data = await coordinator._async_update_data()
        self.assertEqual(
            next_data.account_last_successful_fetch,
            first.account_last_successful_fetch,
        )
        self.assertGreater(
            next_data.bill_last_successful_fetch,
            first.bill_last_successful_fetch,
        )

    async def test_both_fail_keeps_previous_snapshot(self):
        coordinator, _ = make_coordinator()
        first = await coordinator._async_update_data()
        first.bill_last_successful_fetch = (
            datetime.now(timezone.utc) - timedelta(hours=13)
        )
        coordinator.data = first
        coordinator._fetch_account_info.side_effect = TimeoutError()
        coordinator._fetch_bills.side_effect = UpdateFailed()
        with self.assertRaises(UpdateFailed):
            await coordinator._async_update_data()
        self.assertIs(coordinator.data, first)

    async def test_initial_bill_failure_does_not_block_balance(self):
        coordinator, _ = make_coordinator()
        coordinator._fetch_bills.side_effect = UpdateFailed()
        initial = await coordinator._async_update_data()
        self.assertEqual(initial.account["xyyc"], "12.5")
        self.assertIsNotNone(initial.account_last_successful_fetch)
        self.assertIsNone(initial.bill_last_successful_fetch)

    async def test_initial_account_failure_still_fails_setup(self):
        coordinator, _ = make_coordinator()
        coordinator._fetch_account_info.side_effect = TimeoutError()
        with self.assertRaises(UpdateFailed):
            await coordinator._async_update_data()

    async def test_account_switch_invalidates_old_bill_cache(self):
        coordinator, _ = make_coordinator()
        initial = await coordinator._async_update_data()
        coordinator.data = initial
        coordinator._fetch_account_info.return_value = [
            {"yhbh": "002", "xyyc": "24"}
        ]
        coordinator._fetch_bills.side_effect = UpdateFailed()
        updated = await coordinator._async_update_data()
        self.assertEqual(updated.account["yhbh"], "002")
        self.assertEqual(updated.bills, [])
        self.assertIsNone(updated.bill_last_successful_fetch)
        self.assertEqual(coordinator._fetch_bills.await_count, 2)

    async def test_dynamic_account_interval(self):
        coordinator, _ = make_coordinator()
        self.assertEqual(ARREARS_UPDATE_INTERVAL, 1800)
        for raw, hours in [("0", 6), ("6.08", 0.5), (None, 0.5),
                           ("unknown", 0.5), ("NaN", 0.5), ("inf", 0.5),
                           (True, 0.5), ("0.00", 6), ("-1", 6)]:
            with self.subTest(raw=raw):
                coordinator._fetch_account_info.return_value = [
                    {"yhbh": "001", "xyyc": "38.32", "yjje": raw}
                ]
                coordinator.data = await coordinator._async_update_data()
                self.assertEqual(coordinator.update_interval, timedelta(hours=hours))
        self.assertEqual(coordinator._fetch_bills.await_count, 1)

    async def test_account_failure_retains_overdue_interval(self):
        coordinator, _ = make_coordinator()
        coordinator._fetch_account_info.return_value = [
            {"yhbh": "001", "xyyc": "38.32", "yjje": "6.08"}
        ]
        coordinator.data = await coordinator._async_update_data()
        coordinator._fetch_account_info.side_effect = TimeoutError()
        with self.assertRaises(UpdateFailed):
            await coordinator._async_update_data()
        self.assertEqual(coordinator.update_interval, timedelta(minutes=30))

    async def test_manual_forces_both_and_resets_interval(self):
        coordinator, entry = make_coordinator()
        coordinator.data = await coordinator._async_update_data()
        before = coordinator.data
        coordinator._bill_retry_after = datetime.now(timezone.utc) + timedelta(hours=6)
        coordinator._fetch_account_info.return_value = [
            {"yhbh": "001", "xyyc": "38.32", "yjje": "6.08"}
        ]
        button = FzgyswWaterRefreshButton(coordinator, entry)
        self.assertEqual(button.entity_id, "button.fuzhou_water_001_refresh")
        await button.async_press()
        self.assertEqual(coordinator._fetch_account_info.await_count, 2)
        self.assertEqual(coordinator._fetch_bills.await_count, 2)
        self.assertEqual(coordinator.update_interval, timedelta(minutes=30))
        self.assertGreaterEqual(coordinator.data.account_last_successful_fetch, before.account_last_successful_fetch)
        self.assertGreaterEqual(coordinator.data.bill_last_successful_fetch, before.bill_last_successful_fetch)
        self.assertIsNone(coordinator._bill_retry_after)
        with self.assertRaises(HomeAssistantError):
            await button.async_press()
        self.assertEqual(coordinator._fetch_bills.await_count, 2)
        coordinator._manual_refresh_until = 0
        coordinator._fetch_account_info.return_value = [
            {"yhbh": "001", "xyyc": "93.92", "yjje": "-93.92"}
        ]
        await button.async_press()
        self.assertEqual(coordinator.update_interval, timedelta(hours=6))
        coordinator.data = await coordinator._async_update_data()
        self.assertEqual(coordinator._fetch_bills.await_count, 3)

    async def test_manual_partial_failure_preserves_cache_and_short_cooldown(self):
        coordinator, _ = make_coordinator()
        coordinator.data = await coordinator._async_update_data()
        before = coordinator.data
        coordinator._fetch_bills.side_effect = UpdateFailed()
        with patch("fzgysw_water.coordinator.monotonic", return_value=100):
            with self.assertRaises(HomeAssistantError):
                await coordinator.async_refresh_all()
        self.assertEqual(coordinator._manual_refresh_until, 110)
        self.assertEqual(coordinator.data.bill_last_successful_fetch, before.bill_last_successful_fetch)
        self.assertGreaterEqual(coordinator.data.account_last_successful_fetch, before.account_last_successful_fetch)
        self.assertFalse(coordinator._manual_pending)

    async def test_manual_account_failure_still_fetches_bills(self):
        coordinator, _ = make_coordinator()
        coordinator.data = await coordinator._async_update_data()
        before = coordinator.data
        coordinator._fetch_account_info.side_effect = TimeoutError()
        with self.assertRaises(HomeAssistantError):
            await coordinator.async_refresh_all()
        self.assertEqual(coordinator._fetch_bills.await_count, 2)
        self.assertEqual(coordinator.data.account_last_successful_fetch, before.account_last_successful_fetch)
        self.assertGreaterEqual(coordinator.data.bill_last_successful_fetch, before.bill_last_successful_fetch)

    async def test_manual_both_fail_and_cooldown(self):
        coordinator, _ = make_coordinator()
        coordinator.data = await coordinator._async_update_data()
        before = coordinator.data
        coordinator._fetch_account_info.side_effect = TimeoutError()
        coordinator._fetch_bills.side_effect = UpdateFailed()
        with patch("fzgysw_water.coordinator.monotonic", return_value=100):
            with self.assertRaises(HomeAssistantError):
                await coordinator.async_refresh_all()
            with self.assertRaises(HomeAssistantError):
                await coordinator.async_refresh_all()
        self.assertIs(coordinator.data, before)
        self.assertEqual(coordinator._fetch_bills.await_count, 2)
        self.assertEqual(coordinator._manual_refresh_until, 110)

    async def test_concurrent_manual_refresh_and_success_cooldown(self):
        coordinator, _ = make_coordinator()
        coordinator.data = await coordinator._async_update_data()
        entered, proceed = asyncio.Event(), asyncio.Event()
        async def slow(*args):
            entered.set()
            await proceed.wait()
            return [{"yhbh": "001", "xyyc": "93.92", "yjje": "-93.92"}]
        coordinator._fetch_account_info.side_effect = slow
        with patch("fzgysw_water.coordinator.monotonic", return_value=100):
            running = asyncio.create_task(coordinator.async_refresh_all())
            await entered.wait()
            try:
                with self.assertRaises(HomeAssistantError):
                    await coordinator.async_refresh_all()
            finally:
                proceed.set()
            await running
            self.assertEqual(coordinator._manual_refresh_until, 160)
            with self.assertRaises(HomeAssistantError):
                await coordinator.async_refresh_all()
        self.assertEqual(coordinator._fetch_bills.await_count, 2)

    async def test_scheduled_task_does_not_consume_manual_intent(self):
        coordinator, _ = make_coordinator()
        coordinator.data = await coordinator._async_update_data()
        await coordinator._refresh_lock.acquire()
        manual = asyncio.create_task(coordinator.async_refresh_all())
        await asyncio.sleep(0)
        try:
            self.assertTrue(coordinator._manual_pending)
            coordinator.data = await coordinator._async_update_data()
            self.assertEqual(coordinator._fetch_bills.await_count, 1)
        finally:
            coordinator._refresh_lock.release()
        await manual
        self.assertEqual(coordinator._fetch_bills.await_count, 2)


if __name__ == "__main__":
    unittest.main()
