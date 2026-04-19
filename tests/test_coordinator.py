"""Tests for IcecoDataUpdateCoordinator notification processing and alarm logic.

BLE client calls are mocked — no hardware required.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from custom_components.iceco.const import (
    CONF_POWER_LOSS_TIMEOUT,
    CONF_TEMP_DEVIATION_DURATION,
    CONF_TEMP_DEVIATION_THRESHOLD,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POWER_LOSS_TIMEOUT,
    DEFAULT_TEMP_DEVIATION_DURATION,
    DEFAULT_TEMP_DEVIATION_THRESHOLD,
)
from custom_components.iceco.coordinator import IcecoData, IcecoDataUpdateCoordinator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_ADDRESS = "AA:BB:CC:DD:EE:FF"


def _make_entry(address: str = TEST_ADDRESS, options: dict | None = None):
    entry = MagicMock()
    entry.data = {"device_address": address}
    entry.options = options or {}
    entry.entry_id = "test_entry_id"
    return entry


def _make_hass(entry=None):
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = entry or _make_entry()
    return hass


def _make_coord(address: str = TEST_ADDRESS, options: dict | None = None):
    entry = _make_entry(address, options)
    hass = _make_hass(entry)
    ble_device = MagicMock()
    ble_device.address = address
    coord = IcecoDataUpdateCoordinator(hass, ble_device, entry)
    # Suppress HA coordinator machinery — we're testing data logic only
    coord.async_set_updated_data = MagicMock()
    return coord


# Raw notification bytes
PRIMARY_ON_UNLOCKED = b",-18,-15,1,126,1\n"   # power_status=1: on, unlocked
PRIMARY_ON_LOCKED = b",-18,-15,1,126,2\n"      # power_status=2: on, locked
PRIMARY_OFF = b",-18,-15,1,126,0\n"            # power_status=0: off
PRIMARY_POSITIVE = b",4,0,2,130,1\n"           # positive setpoints, 13.0V
SECONDARY_CELSIUS = b"/S00/U/2,1,1,-15,-12\n"  # ECO on, Celsius current temps
SECONDARY_FAHRENHEIT = b"/S00/U/2,0,2,14,32\n" # MAX mode, Fahrenheit current temps
SECONDARY_MAX = b"/S00/U/2,0,1,-15,-12\n"      # MAX mode, Celsius


# ---------------------------------------------------------------------------
# PRIMARY notification processing
# ---------------------------------------------------------------------------


class TestPrimaryNotification:
    def test_sets_left_setpoint(self):
        coord = _make_coord()
        coord._notification_callback(0, PRIMARY_ON_UNLOCKED)
        assert coord.data.left_setpoint == -18

    def test_sets_right_setpoint(self):
        coord = _make_coord()
        coord._notification_callback(0, PRIMARY_ON_UNLOCKED)
        assert coord.data.right_setpoint == -15

    def test_power_status_1_is_on(self):
        coord = _make_coord()
        coord._notification_callback(0, PRIMARY_ON_UNLOCKED)
        assert coord.data.power_on is True

    def test_power_status_2_is_on(self):
        coord = _make_coord()
        coord._notification_callback(0, PRIMARY_ON_LOCKED)
        assert coord.data.power_on is True

    def test_power_status_0_is_off(self):
        coord = _make_coord()
        coord._notification_callback(0, PRIMARY_OFF)
        assert coord.data.power_on is False

    def test_power_status_2_sets_locked(self):
        coord = _make_coord()
        coord._notification_callback(0, PRIMARY_ON_LOCKED)
        assert coord.data.locked is True

    def test_power_status_1_is_unlocked(self):
        coord = _make_coord()
        coord._notification_callback(0, PRIMARY_ON_UNLOCKED)
        assert coord.data.locked is False

    def test_battery_voltage_decoded(self):
        coord = _make_coord()
        coord._notification_callback(0, PRIMARY_ON_UNLOCKED)
        assert coord.data.status.battery_voltage == pytest.approx(12.6)

    def test_clears_power_loss_alarm(self):
        coord = _make_coord()
        coord.data.power_loss_alarm = True
        coord._notification_callback(0, PRIMARY_ON_UNLOCKED)
        assert coord.data.power_loss_alarm is False

    def test_sets_last_update(self):
        coord = _make_coord()
        before = datetime.now()
        coord._notification_callback(0, PRIMARY_ON_UNLOCKED)
        assert coord.data.last_update >= before

    def test_triggers_ha_update(self):
        coord = _make_coord()
        coord._notification_callback(0, PRIMARY_ON_UNLOCKED)
        coord.async_set_updated_data.assert_called_once()

    def test_positive_setpoints(self):
        coord = _make_coord()
        coord._notification_callback(0, PRIMARY_POSITIVE)
        assert coord.data.left_setpoint == 4
        assert coord.data.right_setpoint == 0


# ---------------------------------------------------------------------------
# SECONDARY notification processing
# ---------------------------------------------------------------------------


class TestSecondaryNotification:
    def test_sets_left_current_temp_celsius(self):
        coord = _make_coord()
        coord._notification_callback(0, SECONDARY_CELSIUS)
        assert coord.data.left_current_temp == -15

    def test_sets_right_current_temp_celsius(self):
        coord = _make_coord()
        coord._notification_callback(0, SECONDARY_CELSIUS)
        assert coord.data.right_current_temp == -12

    def test_fahrenheit_converts_left_to_celsius(self):
        # 14°F → (14-32)*5/9 = -10°C
        coord = _make_coord()
        coord._notification_callback(0, SECONDARY_FAHRENHEIT)
        assert coord.data.left_current_temp == -10

    def test_fahrenheit_converts_right_to_celsius(self):
        # 32°F → 0°C
        coord = _make_coord()
        coord._notification_callback(0, SECONDARY_FAHRENHEIT)
        assert coord.data.right_current_temp == 0

    def test_eco_max_1_means_eco_mode_true(self):
        # eco_max=1 in SECONDARY → ECO mode is active
        coord = _make_coord()
        coord._notification_callback(0, SECONDARY_CELSIUS)
        assert coord.data.eco_mode is True

    def test_eco_max_0_means_eco_mode_false(self):
        # eco_max=0 → MAX mode
        coord = _make_coord()
        coord._notification_callback(0, SECONDARY_MAX)
        assert coord.data.eco_mode is False

    def test_unit_mode_celsius(self):
        coord = _make_coord()
        coord._notification_callback(0, SECONDARY_CELSIUS)
        assert coord.data.unit_mode == "C"

    def test_unit_mode_fahrenheit(self):
        coord = _make_coord()
        coord._notification_callback(0, SECONDARY_FAHRENHEIT)
        assert coord.data.unit_mode == "F"

    def test_triggers_ha_update(self):
        coord = _make_coord()
        coord._notification_callback(0, SECONDARY_CELSIUS)
        coord.async_set_updated_data.assert_called_once()


# ---------------------------------------------------------------------------
# Unknown / malformed notifications
# ---------------------------------------------------------------------------


class TestUnknownNotification:
    def test_garbage_data_does_not_update(self):
        coord = _make_coord()
        coord._notification_callback(0, b"garbage\n")
        coord.async_set_updated_data.assert_not_called()

    def test_empty_bytes_does_not_raise(self):
        coord = _make_coord()
        coord._notification_callback(0, b"")
        coord.async_set_updated_data.assert_not_called()

    def test_non_ascii_does_not_raise(self):
        coord = _make_coord()
        coord._notification_callback(0, b"\xff\xfe\xfd")
        coord.async_set_updated_data.assert_not_called()


# ---------------------------------------------------------------------------
# Temperature alarm logic
# ---------------------------------------------------------------------------


class TestZoneAlarm:
    def test_no_alarm_without_current_temp(self):
        coord = _make_coord()
        coord.data.left_setpoint = -18
        # left_current_temp is None
        assert coord._check_zone_alarm("left") is False

    def test_no_alarm_without_setpoint(self):
        coord = _make_coord()
        coord.data.left_current_temp = -10
        # left_setpoint is None
        assert coord._check_zone_alarm("left") is False

    def test_no_alarm_within_threshold(self):
        coord = _make_coord()
        coord.data.left_current_temp = -15
        coord.data.left_setpoint = -18  # deviation=3, threshold=5
        assert coord._check_zone_alarm("left") is False

    def test_no_alarm_immediately_when_threshold_exceeded(self):
        # First observation above threshold starts the timer but does not alarm yet
        coord = _make_coord()
        coord.data.left_current_temp = -10
        coord.data.left_setpoint = -18  # deviation=8 > threshold=5
        result = coord._check_zone_alarm("left")
        assert result is False
        assert coord.data._left_alarm_start is not None

    def test_alarm_fires_after_duration(self):
        coord = _make_coord(options={
            CONF_TEMP_DEVIATION_THRESHOLD: DEFAULT_TEMP_DEVIATION_THRESHOLD,
            CONF_TEMP_DEVIATION_DURATION: DEFAULT_TEMP_DEVIATION_DURATION,
        })
        coord.data.left_current_temp = -10
        coord.data.left_setpoint = -18  # deviation=8 > threshold=5
        # Simulate alarm_start exceeding duration threshold
        coord.data._left_alarm_start = datetime.now() - timedelta(
            minutes=DEFAULT_TEMP_DEVIATION_DURATION + 1
        )
        assert coord._check_zone_alarm("left") is True

    def test_alarm_does_not_fire_before_duration(self):
        coord = _make_coord(options={
            CONF_TEMP_DEVIATION_THRESHOLD: DEFAULT_TEMP_DEVIATION_THRESHOLD,
            CONF_TEMP_DEVIATION_DURATION: DEFAULT_TEMP_DEVIATION_DURATION,
        })
        coord.data.left_current_temp = -10
        coord.data.left_setpoint = -18
        # alarm_start less than duration threshold ago
        coord.data._left_alarm_start = datetime.now() - timedelta(
            minutes=DEFAULT_TEMP_DEVIATION_DURATION - 1
        )
        assert coord._check_zone_alarm("left") is False

    def test_alarm_clears_when_back_within_threshold(self):
        coord = _make_coord()
        coord.data.left_current_temp = -18
        coord.data.left_setpoint = -18  # deviation=0
        coord.data.left_temp_alarm = True
        result = coord._check_zone_alarm("left")
        assert result is False
        assert coord.data._left_alarm_start is None

    def test_hysteresis_prevents_clear_near_threshold(self):
        # Alarm was active; deviation=4, effective clear threshold=5-2=3.
        # 4 > 3, so alarm should stay active.
        coord = _make_coord(options={CONF_TEMP_DEVIATION_THRESHOLD: 5})
        coord.data.left_current_temp = -14
        coord.data.left_setpoint = -18  # deviation=4
        coord.data.left_temp_alarm = True
        coord.data._left_alarm_start = datetime.now() - timedelta(
            minutes=DEFAULT_TEMP_DEVIATION_DURATION + 1
        )
        assert coord._check_zone_alarm("left") is True

    def test_hysteresis_allows_clear_below_effective_threshold(self):
        # Alarm was active; deviation=2, effective clear threshold=5-2=3.
        # 2 <= 3, so alarm should clear.
        coord = _make_coord(options={CONF_TEMP_DEVIATION_THRESHOLD: 5})
        coord.data.left_current_temp = -16
        coord.data.left_setpoint = -18  # deviation=2
        coord.data.left_temp_alarm = True
        assert coord._check_zone_alarm("left") is False

    def test_right_zone_alarm(self):
        coord = _make_coord(options={
            CONF_TEMP_DEVIATION_THRESHOLD: DEFAULT_TEMP_DEVIATION_THRESHOLD,
            CONF_TEMP_DEVIATION_DURATION: DEFAULT_TEMP_DEVIATION_DURATION,
        })
        coord.data.right_current_temp = -5
        coord.data.right_setpoint = -18  # deviation=13 > threshold=5
        coord.data._right_alarm_start = datetime.now() - timedelta(
            minutes=DEFAULT_TEMP_DEVIATION_DURATION + 1
        )
        assert coord._check_zone_alarm("right") is True


# ---------------------------------------------------------------------------
# Power loss detection
# ---------------------------------------------------------------------------


class TestPowerLossAlarm:
    async def test_power_loss_alarm_triggers_after_timeout(self):
        coord = _make_coord(options={CONF_POWER_LOSS_TIMEOUT: DEFAULT_POWER_LOSS_TIMEOUT})
        coord.data.last_update = datetime.now() - timedelta(
            minutes=DEFAULT_POWER_LOSS_TIMEOUT + 1
        )
        # Keep connection_state as "reconnecting" to avoid triggering reconnect logic
        coord.data.connection_state = "reconnecting"

        await coord._async_update_data()

        assert coord.data.power_loss_alarm is True

    async def test_power_loss_alarm_clears_when_recent_update(self):
        coord = _make_coord(options={CONF_POWER_LOSS_TIMEOUT: DEFAULT_POWER_LOSS_TIMEOUT})
        coord.data.last_update = datetime.now() - timedelta(minutes=1)
        coord.data.power_loss_alarm = True
        coord.data.connection_state = "reconnecting"

        await coord._async_update_data()

        assert coord.data.power_loss_alarm is False

    async def test_no_alarm_without_last_update(self):
        coord = _make_coord()
        coord.data.last_update = None

        await coord._async_update_data()

        # No last_update means the check is skipped entirely
        assert coord.data.power_loss_alarm is False
