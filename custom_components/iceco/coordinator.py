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
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .iceco_protocol import IcecoProtocol, IcecoStatus

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

    # Setpoints in °C (read from PRIMARY notification — always °C)
    left_setpoint: Optional[int] = None
    right_setpoint: Optional[int] = None

    # Fridge display unit: "F" or "C" (detected from SECONDARY unit_mode field).
    # Used only to interpret SECONDARY current temperatures — not for commands or PRIMARY.
    unit_mode: str = "F"  # Default; overwritten on first SECONDARY received

    # Alarm states
    left_temp_alarm: bool = False
    right_temp_alarm: bool = False
    power_loss_alarm: bool = False

    # ECO mode state (from SECONDARY eco_max field: 1=ECO, 0=MAX)
    eco_mode: Optional[bool] = None  # True=ECO, False=MAX, None=unknown

    # Power and lock state (promoted from IcecoStatus for entity access)
    power_on: Optional[bool] = None  # True=on, False=off, None=unknown
    locked: Optional[bool] = None    # True=locked, False=unlocked, None=unknown

    # Alarm timing tracking
    _left_alarm_start: Optional[datetime] = field(default=None, repr=False)
    _right_alarm_start: Optional[datetime] = field(default=None, repr=False)


class IcecoDataUpdateCoordinator(DataUpdateCoordinator[IcecoData]):
    """Coordinator for managing Iceco refrigerator BLE connection."""

    def __init__(
        self,
        hass: HomeAssistant,
        ble_device: BLEDevice,
        entry: ConfigEntry,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            ),
        )

        self._ble_device = ble_device
        self._entry = entry
        self._client: Optional[BleakClientWithServiceCache] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._reconnect_count = 0
        self._manual_disconnect = False  # Flag to prevent auto-reconnect
        self._write_lock = asyncio.Lock()  # Serialise BLE writes to prevent concurrent GATT ops


        # Event set on first received notification - used to verify data is flowing after connect
        self._first_notification_event = asyncio.Event()

        # Initialize data
        self.data = IcecoData()

    @property
    def _options(self) -> dict:
        """Get current options from config entry."""
        return self._entry.options

    async def _async_setup(self) -> None:
        """Set up the coordinator - called once on entry setup."""
        await self._async_connect()

    async def _async_connect(self) -> None:
        """Establish BLE connection to refrigerator."""
        try:
            _LOGGER.debug("Attempting to connect to %s", self._ble_device.address)
            self.data.connection_state = "connecting"

            # Reset notification event before connecting so we can verify data flows after
            self._first_notification_event.clear()

            # Use bleak-retry-connector for reliable connection.
            # Service cache is disabled: a stale cache causes "Characteristic not found"
            # errors after HA restarts or device power cycles, requiring multiple retries
            # or a power cycle to recover. Fresh GATT service discovery on every connection
            # is slightly slower but eliminates this failure mode.
            self._client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self._ble_device.address,
                disconnected_callback=self._handle_disconnect,
                use_services_cache=False,
                ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                    self.hass, self._ble_device.address, connectable=True
                ),
            )

            # Subscribe to status notifications from characteristic FFF4
            await self._client.start_notify(
                IcecoProtocol.NOTIFY_UUID, self._notification_callback
            )

            # Wait for first notification to confirm data is actually flowing.
            # A successful BLE connection does not guarantee the fridge is sending data —
            # the notification subscription can silently fail if the fridge BLE stack is
            # in a bad state (e.g. after rapid reconnects during an HA restart/update).
            try:
                await asyncio.wait_for(self._first_notification_event.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                _LOGGER.error(
                    "No notifications received within 10s of connecting to %s — "
                    "fridge BLE stack may be in a bad state",
                    self._ble_device.address,
                )
                raise UpdateFailed("Connected but no data received — fridge not sending notifications")

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
        # Signal that notifications are flowing (verifies connection quality on startup)
        self._first_notification_event.set()

        # Try parsing as PRIMARY notification (setpoints + battery/power status)
        status = IcecoProtocol.parse_notification(data)

        if status:
            # PRIMARY always in °C — store directly.
            self.data.status = status
            self.data.left_setpoint = status.left_temp
            self.data.right_setpoint = status.right_temp
            self.data.power_on = status.power_on
            self.data.locked = status.locked
            self.data.last_update = datetime.now()
            self.data.power_loss_alarm = False

            self._check_temperature_alarms()
            self.async_set_updated_data(self.data)
        else:
            # Try parsing as SECONDARY notification (current temperatures in fridge's display unit)
            secondary = IcecoProtocol.parse_secondary_status(data)
            if secondary:
                unit_mode = secondary['unit_mode']
                left_temp = secondary['left_setpoint']
                right_temp = secondary['right_setpoint']

                # SECONDARY reports in fridge's display unit — convert to °C for storage.
                if unit_mode == 2:  # Fahrenheit
                    left_temp = round((left_temp - 32) * 5 / 9)
                    right_temp = round((right_temp - 32) * 5 / 9)
                # unit_mode == 1 is already °C

                self.data.left_current_temp = left_temp
                self.data.right_current_temp = right_temp
                self.data.unit_mode = "C" if unit_mode == 1 else "F"

                new_eco_mode = (secondary['eco_max'] == 1)  # 1=ECO, 0=MAX
                if new_eco_mode != self.data.eco_mode:
                    _LOGGER.info("ECO mode changed: raw eco_max=%d → eco_mode=%s", secondary['eco_max'], new_eco_mode)
                self.data.eco_mode = new_eco_mode

                self.async_set_updated_data(self.data)

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
                if self.data.connection_state == "connected":
                    # BLE layer says connected but fridge has gone silent. Must disconnect
                    # cleanly before reconnecting — calling _async_connect() on an active
                    # client causes start_notify() to fail, which flips state to
                    # "disconnected" and then the next health check skips reconnect entirely.
                    _LOGGER.warning("Connection appears stale, disconnecting and reconnecting")
                    try:
                        async with asyncio.timeout(60):
                            self._manual_disconnect = True  # prevent _handle_disconnect from scheduling another reconnect
                            try:
                                if self._client and self._client.is_connected:
                                    await self._client.disconnect()
                            except Exception as disc_err:
                                _LOGGER.debug("Error disconnecting stale client: %s", disc_err)
                            self._manual_disconnect = False
                            self.data.connection_state = "disconnected"
                            await self._async_connect()
                    except TimeoutError:
                        _LOGGER.error("Timed out during stale connection recovery")
                        self._manual_disconnect = False
                elif self.data.connection_state == "disconnected":
                    # Disconnected with no active reconnect task — scheduled reconnect
                    # either never started or failed without rescheduling itself.
                    if not self._reconnect_task or self._reconnect_task.done():
                        _LOGGER.warning("Disconnected with no active reconnect task, triggering reconnect")
                        try:
                            async with asyncio.timeout(60):
                                await self._async_connect()
                        except TimeoutError:
                            _LOGGER.error("Timed out during health-check reconnect")

        return self.data

    async def async_set_left_temperature(self, temp: int) -> None:
        """Set left zone temperature (°C) and store setpoint."""
        if not self._client or not self._client.is_connected:
            raise UpdateFailed("Not connected to refrigerator")

        try:
            command = IcecoProtocol.set_left_temperature(temp)
            async with self._write_lock:
                await self._client.write_gatt_char(IcecoProtocol.WRITE_UUID, command, response=False)
            self.data.left_setpoint = temp
            _LOGGER.info("Left zone setpoint → %d°C", temp)
            self.async_set_updated_data(self.data)

        except Exception as err:
            _LOGGER.error("Failed to set left temperature: %s", err)
            raise UpdateFailed(f"Failed to set temperature: {err}")

    async def async_set_right_temperature(self, temp: int) -> None:
        """Set right zone temperature (°C) and store setpoint."""
        if not self._client or not self._client.is_connected:
            raise UpdateFailed("Not connected to refrigerator")

        try:
            command = IcecoProtocol.set_right_temperature(temp)
            async with self._write_lock:
                await self._client.write_gatt_char(IcecoProtocol.WRITE_UUID, command, response=False)
            self.data.right_setpoint = temp
            _LOGGER.info("Right zone setpoint → %d°C", temp)
            self.async_set_updated_data(self.data)

        except Exception as err:
            _LOGGER.error("Failed to set right temperature: %s", err)
            raise UpdateFailed(f"Failed to set temperature: {err}")

    async def async_toggle_power(self) -> None:
        """Toggle power state."""
        if not self._client or not self._client.is_connected:
            raise UpdateFailed("Not connected to refrigerator")

        try:
            command = IcecoProtocol.toggle_power()
            async with self._write_lock:
                await self._client.write_gatt_char(IcecoProtocol.WRITE_UUID, command, response=False)
            _LOGGER.info("Toggled power state")

        except Exception as err:
            _LOGGER.error("Failed to toggle power: %s", err)
            raise UpdateFailed(f"Failed to toggle power: {err}")

    async def async_set_eco_mode(self, eco_on: bool) -> None:
        """Set ECO mode on or off."""
        if not self._client or not self._client.is_connected:
            raise UpdateFailed("Not connected to refrigerator")

        try:
            command = IcecoProtocol.set_eco_mode(eco_on)
            async with self._write_lock:
                await self._client.write_gatt_char(IcecoProtocol.WRITE_UUID, command, response=False)
            _LOGGER.info("ECO mode → %s", "ECO" if eco_on else "MAX")

        except Exception as err:
            _LOGGER.error("Failed to set ECO mode: %s", err)
            raise UpdateFailed(f"Failed to set ECO mode: {err}")

    async def async_set_lock(self, locked: bool) -> None:
        """Lock or unlock the control panel."""
        if not self._client or not self._client.is_connected:
            raise UpdateFailed("Not connected to refrigerator")

        try:
            command = IcecoProtocol.set_lock(locked)
            async with self._write_lock:
                await self._client.write_gatt_char(IcecoProtocol.WRITE_UUID, command, response=False)
            _LOGGER.info("Lock → %s", "locked" if locked else "unlocked")

        except Exception as err:
            _LOGGER.error("Failed to set lock: %s", err)
            raise UpdateFailed(f"Failed to set lock: {err}")

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
