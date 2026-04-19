"""Tests for Iceco config flow and options flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.iceco.const import (
    CONF_DEVICE_ADDRESS,
    CONF_POLL_INTERVAL,
    CONF_POWER_LOSS_TIMEOUT,
    CONF_TEMP_DEVIATION_DURATION,
    CONF_TEMP_DEVIATION_THRESHOLD,
    DOMAIN,
)

TEST_ADDRESS = "AA:BB:CC:DD:EE:FF"
TEST_NAME = "Iceco Fridge"


def _make_bt_discovery(address: str = TEST_ADDRESS, name: str = TEST_NAME):
    """Build a BluetoothServiceInfoBleak for testing."""
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-60,
        manufacturer_data={},
        service_data={},
        service_uuids=["0000fff0-0000-1000-8000-00805f9b34fb"],
        source="local",
        device=MagicMock(),
        advertisement=MagicMock(),
        connectable=True,
        time=0.0,
        tx_power=-127,
    )


def _make_discovered_device(address: str = TEST_ADDRESS, name: str = TEST_NAME):
    """Build a minimal discovered device for async_discovered_service_info."""
    device = MagicMock()
    device.address = address
    device.name = name
    device.service_uuids = ["0000fff0-0000-1000-8000-00805f9b34fb"]
    return device


# ---------------------------------------------------------------------------
# Bluetooth discovery path
# ---------------------------------------------------------------------------


class TestBluetoothDiscovery:
    async def test_discovery_shows_confirm_form(self, hass, enable_bluetooth):
        discovery = _make_bt_discovery()
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_BLUETOOTH},
            data=discovery,
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "confirm"

    async def test_discovery_creates_entry_on_confirm(self, hass, enable_bluetooth):
        discovery = _make_bt_discovery()
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_BLUETOOTH},
            data=discovery,
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={},
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_DEVICE_ADDRESS] == TEST_ADDRESS

    async def test_discovery_duplicate_aborts(self, hass, enable_bluetooth):
        existing = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_DEVICE_ADDRESS: TEST_ADDRESS},
            unique_id=TEST_ADDRESS,
        )
        existing.add_to_hass(hass)

        discovery = _make_bt_discovery()
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_BLUETOOTH},
            data=discovery,
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"

    async def test_discovery_title_uses_device_name(self, hass, enable_bluetooth):
        discovery = _make_bt_discovery(name="My Iceco")
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_BLUETOOTH},
            data=discovery,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={},
        )

        assert result["title"] == "My Iceco"

    async def test_discovery_falls_back_title_when_no_name(self, hass, enable_bluetooth):
        discovery = MagicMock(spec=BluetoothServiceInfoBleak)
        discovery.address = TEST_ADDRESS
        discovery.name = None
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_BLUETOOTH},
            data=discovery,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={},
        )

        assert result["title"] == "Iceco Refrigerator"


# ---------------------------------------------------------------------------
# Manual user path — no devices found
# ---------------------------------------------------------------------------


class TestManualFlowNoDevices:
    async def test_shows_manual_entry_form_when_no_devices(self, hass, enable_bluetooth):
        with patch(
            "custom_components.iceco.config_flow.async_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

    async def test_manual_entry_creates_entry(self, hass, enable_bluetooth):
        with patch(
            "custom_components.iceco.config_flow.async_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
            )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"address": TEST_ADDRESS},
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_DEVICE_ADDRESS] == TEST_ADDRESS


# ---------------------------------------------------------------------------
# Manual user path — devices found (select_device step)
# ---------------------------------------------------------------------------


class TestManualFlowWithDevices:
    async def test_shows_select_device_form_when_devices_found(
        self, hass, enable_bluetooth
    ):
        fake_device = _make_discovered_device()
        with patch(
            "custom_components.iceco.config_flow.async_discovered_service_info",
            return_value=[fake_device],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "select_device"

    async def test_select_device_creates_entry(self, hass, enable_bluetooth):
        fake_device = _make_discovered_device()
        with patch(
            "custom_components.iceco.config_flow.async_discovered_service_info",
            return_value=[fake_device],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
            )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"address": TEST_ADDRESS},
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_DEVICE_ADDRESS] == TEST_ADDRESS

    async def test_select_device_duplicate_aborts(self, hass, enable_bluetooth):
        existing = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_DEVICE_ADDRESS: TEST_ADDRESS},
            unique_id=TEST_ADDRESS,
        )
        existing.add_to_hass(hass)

        fake_device = _make_discovered_device()
        with patch(
            "custom_components.iceco.config_flow.async_discovered_service_info",
            return_value=[fake_device],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
            )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"address": TEST_ADDRESS},
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


class TestOptionsFlow:
    async def test_options_flow_shows_init_form(self, hass, enable_bluetooth):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_DEVICE_ADDRESS: TEST_ADDRESS},
            unique_id=TEST_ADDRESS,
            options={},
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

    async def test_options_flow_saves_values(self, hass, enable_bluetooth):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_DEVICE_ADDRESS: TEST_ADDRESS},
            unique_id=TEST_ADDRESS,
            options={},
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_POLL_INTERVAL: 90,
                CONF_POWER_LOSS_TIMEOUT: 20,
                CONF_TEMP_DEVIATION_THRESHOLD: 4,
                CONF_TEMP_DEVIATION_DURATION: 10,
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_POLL_INTERVAL] == 90
        assert result["data"][CONF_POWER_LOSS_TIMEOUT] == 20
