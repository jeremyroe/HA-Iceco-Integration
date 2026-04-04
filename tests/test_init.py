"""Tests for Iceco integration setup and unload lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.iceco.const import CONF_DEVICE_ADDRESS, DOMAIN

TEST_ADDRESS = "AA:BB:CC:DD:EE:FF"


@pytest.fixture
def mock_config_entry():
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DEVICE_ADDRESS: TEST_ADDRESS},
        unique_id=TEST_ADDRESS,
    )


# ---------------------------------------------------------------------------
# Setup failure paths
# ---------------------------------------------------------------------------


class TestSetupEntry:
    async def test_setup_raises_config_entry_not_ready_when_no_ble_device(
        self, hass, mock_config_entry
    ):
        mock_config_entry.add_to_hass(hass)

        with patch(
            "custom_components.iceco.bluetooth.async_ble_device_from_address",
            return_value=None,
        ):
            await hass.config_entries.async_setup(mock_config_entry.entry_id)

        assert mock_config_entry.state == ConfigEntryState.SETUP_RETRY

    async def test_setup_raises_config_entry_not_ready_when_coordinator_fails(
        self, hass, mock_config_entry
    ):
        mock_config_entry.add_to_hass(hass)

        mock_ble_device = MagicMock()
        mock_ble_device.address = TEST_ADDRESS

        with patch(
            "custom_components.iceco.bluetooth.async_ble_device_from_address",
            return_value=mock_ble_device,
        ), patch(
            "custom_components.iceco.IcecoDataUpdateCoordinator"
        ) as mock_coord_cls:
            mock_coord = MagicMock()
            mock_coord.async_config_entry_first_refresh = AsyncMock(
                side_effect=Exception("BLE connection failed")
            )
            mock_coord_cls.return_value = mock_coord

            await hass.config_entries.async_setup(mock_config_entry.entry_id)

        assert mock_config_entry.state == ConfigEntryState.SETUP_RETRY


# ---------------------------------------------------------------------------
# Unload
# ---------------------------------------------------------------------------


class TestUnloadEntry:
    async def test_unload_not_loaded_entry_is_safe(self, hass, mock_config_entry):
        # An entry that was never loaded (e.g. failed with SETUP_RETRY) can be
        # unloaded without error. HA returns False in this case.
        mock_config_entry.add_to_hass(hass)

        result = await hass.config_entries.async_unload(mock_config_entry.entry_id)

        assert mock_config_entry.state == ConfigEntryState.NOT_LOADED
        # HA returns True when unloading an entry that was never loaded (no-op)
        assert result is True
