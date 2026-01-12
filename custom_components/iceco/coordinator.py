"""Coordinator for Iceco refrigerator integration."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Optional

from bleak.backends.device import BLEDevice
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .iceco_protocol import IcecoClient, IcecoProtocol, IcecoStatus

from .const import (
    ALARM_HYSTERESIS,
    CONF_POLL_INTERVAL,
    CONF_POWER_LOSS_TIMEOUT,
    CONF_TEMP_DEVIATION_DURATION,
    CONF_TEMP_DEVIATION_THRESHOLD,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POWER_LOSS_TIMEOUT,
    DEFAULT_TEMP_DEVIATION_DURATION,
    DEFAULT_TEMP_DEVIATION_THRESHOLD,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class IcecoData:
    """Data managed by coordinator."""

    status: Optional[IcecoStatus] = None
    last_update: Optional[datetime] = None
    connection_state: str = "disconnected"  # disconnected/connected/reconnecting

    # Current temps (from SECONDARY notification)
    left_current_temp: Optional[int] = None
    right_current_temp: Optional[int] = None

    # User setpoints in Fahrenheit (read from PRIMARY notification)
    # PRIMARY reports setpoints in Celsius, we convert and store in F
    left_setpoint: Optional[int] = None
    right_setpoint: Optional[int] = None

    # Fridge unit mode: "F" or "C" (detected from secondary status)
    unit_mode: str = "F"  # Default to Fahrenheit

    # Alarm states
    left_temp_alarm: bool = False
    right_temp_alarm: bool = False
    power_loss_alarm: bool = False

    # Alarm timing tracking
    _left_alarm_start: Optional[datetime] = field(default=None, repr=False)
    _right_alarm_start: Optional[datetime] = field(default=None, repr=False)


class IcecoDataUpdateCoordinator(DataUpdateCoordinator[IcecoData]):
    """Coordinator for managing Iceco refrigerator BLE connection."""

    def __init__(
        self,
        hass: HomeAssistant,
        ble_device: BLEDevice,
        entry_id: str,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=hass.config_entries.async_get_entry(entry_id)
                .options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            ),
        )

        self._ble_device = ble_device
        self._entry_id = entry_id
        self._client: Optional[BleakClientWithServiceCache] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._reconnect_count = 0
        self._manual_disconnect = False  # Flag to prevent auto-reconnect

        # Initialize data
        self.data = IcecoData()

    @property
    def _options(self) -> dict:
        """Get current options from config entry."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        return entry.options if entry else {}

    async def _async_setup(self) -> None:
        """Set up the coordinator - called once on entry setup."""
        await self._async_connect()

    async def _async_connect(self) -> None:
        """Establish BLE connection to refrigerator."""
        try:
            _LOGGER.debug("Attempting to connect to %s", self._ble_device.address)
            self.data.connection_state = "connecting"

            # Use bleak-retry-connector for reliable connection
            self._client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self._ble_device.address,
                disconnected_callback=self._handle_disconnect,
                use_services_cache=True,
                ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                    self.hass, self._ble_device.address, connectable=True
                ),
            )

            # Start receiving notifications
            await self._client.start_notify(
                IcecoProtocol.NOTIFY_UUID, self._notification_callback
            )

            self.data.connection_state = "connected"
            self._reconnect_count = 0
            _LOGGER.info("Connected to Iceco refrigerator at %s", self._ble_device.address)

        except Exception as err:
            _LOGGER.error("Failed to connect to refrigerator: %s", err)
            self.data.connection_state = "disconnected"
            # Don't schedule reconnect here - just fail and let HA retry
            raise UpdateFailed(f"Failed to connect: {err}")

    def _notification_callback(self, sender: int, data: bytes) -> None:
        """Handle incoming BLE notifications."""
        _LOGGER.debug("Received notification: %s", data)
        _LOGGER.warning("RAW NOTIFICATION DATA: %s", data)

        # Try parsing as PRIMARY notification (contains SETPOINTS in Celsius)
        status = IcecoProtocol.parse_notification(data)

        if status:
            # PRIMARY notification contains SETPOINTS in Celsius, NOT current temps!
            # Convert setpoints from Celsius to Fahrenheit for HA
            left_setpoint_f = round((status.left_temp * 9 / 5) + 32)
            right_setpoint_f = round((status.right_temp * 9 / 5) + 32)

            _LOGGER.warning("PARSED PRIMARY (SETPOINTS) - left=%d°C (%d°F), right=%d°C (%d°F), battery=%.1fV, power=%s",
                          status.left_temp, left_setpoint_f, status.right_temp, right_setpoint_f,
                          status.battery_voltage, status.power_on)

            # Update data with new status and setpoints
            self.data.status = status
            self.data.left_setpoint = left_setpoint_f
            self.data.right_setpoint = right_setpoint_f
            self.data.last_update = datetime.now()
            self.data.power_loss_alarm = False  # Clear power loss alarm on successful update

            # Check temperature alarms
            self._check_temperature_alarms()

            # Notify entities of update
            self.async_set_updated_data(self.data)
        else:
            # Try parsing as SECONDARY notification (contains CURRENT temps in user's unit)
            secondary = IcecoProtocol.parse_secondary_status(data)
            if secondary:
                # SECONDARY contains actual CURRENT temperatures in fridge's current unit mode
                # (These are NOT setpoints - setpoints come from PRIMARY!)
                unit_mode = secondary['unit_mode']  # 1=C, 2=F
                zone_count = secondary.get('zone_count', 0)  # Number from /S00/U/X
                eco_max = secondary.get('eco_max', 1)  # 0=ECO, 1=MAX
                left_temp = secondary['left_setpoint']  # Misnamed field - actually current temp
                right_temp = secondary['right_setpoint']  # Misnamed field - actually current temp

                # HA uses Fahrenheit, so convert if fridge is in Celsius mode
                if unit_mode == 1:  # Celsius mode
                    left_temp_f = round((left_temp * 9 / 5) + 32)
                    right_temp_f = round((right_temp * 9 / 5) + 32)
                    _LOGGER.warning("PARSED SECONDARY (CURRENT TEMPS) - zones=%d, eco_max=%d, unit=C, left=%d°C (%d°F), right=%d°C (%d°F)",
                                  zone_count, eco_max, left_temp, left_temp_f, right_temp, right_temp_f)
                    left_temp = left_temp_f
                    right_temp = right_temp_f
                else:  # Fahrenheit mode
                    _LOGGER.warning("PARSED SECONDARY (CURRENT TEMPS) - zones=%d, eco_max=%d, unit=F, left=%d°F, right=%d°F",
                                  zone_count, eco_max, left_temp, right_temp)

                # Update current temperatures (NOT setpoints!)
                self.data.left_current_temp = left_temp
                self.data.right_current_temp = right_temp

                # NOTE: Setpoints are read from PRIMARY notification, not SECONDARY!
                # Do not initialize or update setpoints from current temps

                # Notify entities of update
                self.async_set_updated_data(self.data)
            else:
                _LOGGER.debug("Could not parse notification")

    def _check_temperature_alarms(self) -> None:
        """Check for temperature deviation alarms."""
        self.data.left_temp_alarm = self._check_zone_alarm("left")
        self.data.right_temp_alarm = self._check_zone_alarm("right")

    def _check_zone_alarm(self, zone: str) -> bool:
        """Check if specific zone should alarm."""
        # Get current temp (from SECONDARY) and setpoint (from PRIMARY)
        if zone == "left":
            actual = self.data.left_current_temp
            setpoint = self.data.left_setpoint
            alarm_start = self.data._left_alarm_start
        else:
            actual = self.data.right_current_temp
            setpoint = self.data.right_setpoint
            alarm_start = self.data._right_alarm_start

        # No alarm if no current temp or setpoint available
        if actual is None or setpoint is None:
            return False

        # Calculate deviation (in Fahrenheit)
        deviation = abs(actual - setpoint)
        threshold = self._options.get(
            CONF_TEMP_DEVIATION_THRESHOLD, DEFAULT_TEMP_DEVIATION_THRESHOLD
        )

        # Check if currently alarmed
        currently_alarmed = (
            self.data.left_temp_alarm if zone == "left" else self.data.right_temp_alarm
        )

        # Apply hysteresis when clearing alarm
        effective_threshold = threshold - ALARM_HYSTERESIS if currently_alarmed else threshold

        if deviation > effective_threshold:
            # Deviation detected
            if alarm_start is None:
                # Start tracking
                if zone == "left":
                    self.data._left_alarm_start = datetime.now()
                else:
                    self.data._right_alarm_start = datetime.now()
                return False  # Don't alarm immediately
            else:
                # Check if sustained long enough
                duration = datetime.now() - alarm_start
                duration_threshold = timedelta(
                    minutes=self._options.get(CONF_TEMP_DEVIATION_DURATION, DEFAULT_TEMP_DEVIATION_DURATION)
                )
                return duration >= duration_threshold
        else:
            # Within threshold - reset alarm tracking
            if zone == "left":
                self.data._left_alarm_start = None
            else:
                self.data._right_alarm_start = None
            return False

    @callback
    def _handle_disconnect(self, client: BleakClientWithServiceCache) -> None:
        """Handle BLE disconnection."""
        _LOGGER.warning("Disconnected from refrigerator")
        self.data.connection_state = "disconnected"
        self.async_set_updated_data(self.data)

        # Only schedule reconnection if not manually disconnected
        if not self._manual_disconnect:
            if not self._reconnect_task or self._reconnect_task.done():
                self._reconnect_task = self.hass.async_create_task(
                    self._schedule_reconnect()
                )

    async def _schedule_reconnect(self) -> None:
        """Schedule reconnection with exponential backoff."""
        # Exponential backoff: 1s, 2s, 4s, 8s, ..., max 60s
        delay = min(2**self._reconnect_count, 60)
        self._reconnect_count += 1

        _LOGGER.info("Scheduling reconnection in %ds (attempt %d)", delay, self._reconnect_count)
        self.data.connection_state = "reconnecting"

        await asyncio.sleep(delay)

        try:
            await self._async_connect()
        except Exception as err:
            _LOGGER.error("Reconnection failed: %s", err)
            # Will retry on next health check

    async def _async_update_data(self) -> IcecoData:
        """Periodic health check (not data update - notifications handle that)."""
        # Check for power loss
        if self.data.last_update:
            time_since_update = datetime.now() - self.data.last_update
            power_loss_timeout = timedelta(
                minutes=self._options.get(CONF_POWER_LOSS_TIMEOUT, DEFAULT_POWER_LOSS_TIMEOUT)
            )

            prev_alarm_state = self.data.power_loss_alarm
            if time_since_update > power_loss_timeout:
                self.data.power_loss_alarm = True
            else:
                self.data.power_loss_alarm = False

            # If alarm state changed, log it
            if prev_alarm_state != self.data.power_loss_alarm:
                _LOGGER.warning(
                    "Power loss alarm %s (no update for %s)",
                    "TRIGGERED" if self.data.power_loss_alarm else "cleared",
                    time_since_update
                )

            # Check connection health
            poll_interval = timedelta(seconds=self.update_interval.total_seconds())
            if time_since_update > poll_interval * 2:
                _LOGGER.warning(
                    "No status update in %s, checking connection health",
                    time_since_update,
                )
                # If no recent update and not already reconnecting, trigger reconnect
                if self.data.connection_state == "connected":
                    _LOGGER.warning("Connection appears stale, reconnecting")
                    await self._async_connect()

        return self.data

    async def async_set_left_temperature(self, temp: int) -> None:
        """Set left zone temperature and store setpoint."""
        _LOGGER.info(
            "async_set_left_temperature called: temp=%d, connected=%s",
            temp,
            self._client.is_connected if self._client else False,
        )

        if not self._client or not self._client.is_connected:
            _LOGGER.error("Cannot set left temperature: not connected to refrigerator")
            raise UpdateFailed("Not connected to refrigerator")

        try:
            # Fridge ALWAYS interprets commands in Celsius, regardless of display unit mode
            temp_celsius = round((temp - 32) * 5 / 9)
            command = IcecoProtocol.set_left_temperature(temp_celsius)
            _LOGGER.info("Sending left temperature command: %d°F → %d°C → %s", temp, temp_celsius, command)
            await self._client.write_gatt_char(IcecoProtocol.WRITE_UUID, command)

            # Store the celsius value converted back to F (like mobile app does)
            # This shows the actual setpoint the fridge accepted, accounting for rounding
            temp_stored_f = round((temp_celsius * 9 / 5) + 32)
            self.data.left_setpoint = temp_stored_f
            self.async_set_updated_data(self.data)
            _LOGGER.info("Successfully set left zone setpoint to %d°F (stored as %d°C → %d°F)", temp, temp_celsius, temp_stored_f)

        except Exception as err:
            _LOGGER.error("Failed to set left temperature: %s", err)
            raise UpdateFailed(f"Failed to set temperature: {err}")

    async def async_set_right_temperature(self, temp: int) -> None:
        """Set right zone temperature and store setpoint."""
        _LOGGER.info(
            "async_set_right_temperature called: temp=%d, connected=%s",
            temp,
            self._client.is_connected if self._client else False,
        )

        if not self._client or not self._client.is_connected:
            _LOGGER.error("Cannot set right temperature: not connected to refrigerator")
            raise UpdateFailed("Not connected to refrigerator")

        try:
            # Fridge ALWAYS interprets commands in Celsius, regardless of display unit mode
            temp_celsius = round((temp - 32) * 5 / 9)
            command = IcecoProtocol.set_right_temperature(temp_celsius)
            _LOGGER.info("Sending right temperature command: %d°F → %d°C → %s", temp, temp_celsius, command)
            await self._client.write_gatt_char(IcecoProtocol.WRITE_UUID, command)

            # Store the celsius value converted back to F (like mobile app does)
            # This shows the actual setpoint the fridge accepted, accounting for rounding
            temp_stored_f = round((temp_celsius * 9 / 5) + 32)
            self.data.right_setpoint = temp_stored_f
            self.async_set_updated_data(self.data)
            _LOGGER.info("Successfully set right zone setpoint to %d°F (stored as %d°C → %d°F)", temp, temp_celsius, temp_stored_f)

        except Exception as err:
            _LOGGER.error("Failed to set right temperature: %s", err)
            raise UpdateFailed(f"Failed to set temperature: {err}")

    async def async_toggle_power(self) -> None:
        """Toggle power state."""
        if not self._client or not self._client.is_connected:
            raise UpdateFailed("Not connected to refrigerator")

        try:
            command = IcecoProtocol.toggle_power()
            await self._client.write_gatt_char(IcecoProtocol.WRITE_UUID, command)
            _LOGGER.info("Toggled power state")

        except Exception as err:
            _LOGGER.error("Failed to toggle power: %s", err)
            raise UpdateFailed(f"Failed to toggle power: {err}")

    async def async_toggle_eco_mode(self) -> None:
        """Toggle ECO mode."""
        if not self._client or not self._client.is_connected:
            raise UpdateFailed("Not connected to refrigerator")

        try:
            command = IcecoProtocol.toggle_eco_mode()
            await self._client.write_gatt_char(IcecoProtocol.WRITE_UUID, command)
            _LOGGER.info("Toggled ECO mode")

        except Exception as err:
            _LOGGER.error("Failed to toggle ECO mode: %s", err)
            raise UpdateFailed(f"Failed to toggle ECO mode: {err}")

    async def async_toggle_lock(self) -> None:
        """Toggle control panel lock."""
        if not self._client or not self._client.is_connected:
            raise UpdateFailed("Not connected to refrigerator")

        try:
            command = IcecoProtocol.toggle_lock()
            await self._client.write_gatt_char(IcecoProtocol.WRITE_UUID, command)
            _LOGGER.info("Toggled lock")

        except Exception as err:
            _LOGGER.error("Failed to toggle lock: %s", err)
            raise UpdateFailed(f"Failed to toggle lock: {err}")

    async def async_manual_disconnect(self) -> None:
        """Manually disconnect from refrigerator (for mobile app access)."""
        _LOGGER.info("Manual disconnect requested")

        # Set flag to prevent auto-reconnect
        self._manual_disconnect = True

        # Cancel any reconnection attempts
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()

        # Disconnect if connected
        if self._client and self._client.is_connected:
            await self._client.disconnect()
            _LOGGER.info("Manually disconnected from refrigerator")

        self.data.connection_state = "disconnected"
        self.async_set_updated_data(self.data)

    async def async_manual_reconnect(self) -> None:
        """Manually reconnect to refrigerator."""
        _LOGGER.info("Manual reconnect requested")

        # Clear manual disconnect flag
        self._manual_disconnect = False

        await self._async_connect()

    async def async_shutdown(self) -> None:
        """Clean shutdown of coordinator."""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()

        if self._client and self._client.is_connected:
            await self._client.disconnect()
            _LOGGER.info("Disconnected from refrigerator")
