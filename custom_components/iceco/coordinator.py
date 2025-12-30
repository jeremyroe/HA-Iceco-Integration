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

from iceco_protocol import IcecoClient, IcecoProtocol, IcecoStatus

from .const import (
    ALARM_HYSTERESIS,
    CONF_POLL_INTERVAL,
    CONF_POWER_LOSS_TIMEOUT,
    CONF_TEMP_DEVIATION_DURATION,
    CONF_TEMP_DEVIATION_THRESHOLD,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class IcecoData:
    """Data managed by coordinator."""

    status: Optional[IcecoStatus] = None
    last_update: Optional[datetime] = None
    connection_state: str = "disconnected"  # disconnected/connected/reconnecting

    # User setpoints (stored locally since protocol doesn't report them)
    left_setpoint: Optional[int] = None
    right_setpoint: Optional[int] = None

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
            # Schedule reconnection
            await self._schedule_reconnect()
            raise UpdateFailed(f"Failed to connect: {err}")

    def _notification_callback(self, sender: int, data: bytes) -> None:
        """Handle incoming BLE notifications."""
        _LOGGER.debug("Received notification: %s", data)

        # Parse notification using protocol library
        status = IcecoProtocol.parse_notification(data)

        if status:
            # Update data with new status
            self.data.status = status
            self.data.last_update = datetime.now()
            self.data.power_loss_alarm = False  # Clear power loss alarm on successful update

            # Check temperature alarms
            self._check_temperature_alarms()

            # Notify entities of update
            self.async_set_updated_data(self.data)
        else:
            _LOGGER.debug("Could not parse notification (may be secondary status)")

    def _check_temperature_alarms(self) -> None:
        """Check for temperature deviation alarms."""
        self.data.left_temp_alarm = self._check_zone_alarm("left")
        self.data.right_temp_alarm = self._check_zone_alarm("right")

    def _check_zone_alarm(self, zone: str) -> bool:
        """Check if specific zone should alarm."""
        if not self.data.status:
            return False

        # Get current temp and setpoint
        if zone == "left":
            actual = self.data.status.left_temp
            setpoint = self.data.left_setpoint
            alarm_start = self.data._left_alarm_start
        else:
            actual = self.data.status.right_temp
            setpoint = self.data.right_setpoint
            alarm_start = self.data._right_alarm_start

        # No alarm if no setpoint configured
        if setpoint is None:
            return False

        # Calculate deviation
        deviation = abs(actual - setpoint)
        threshold = self._options.get(
            CONF_TEMP_DEVIATION_THRESHOLD, ALARM_HYSTERESIS + 1
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
                    minutes=self._options.get(CONF_TEMP_DEVIATION_DURATION, 15)
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

        # Schedule reconnection
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
                minutes=self._options.get(CONF_POWER_LOSS_TIMEOUT, 30)
            )

            if time_since_update > power_loss_timeout:
                self.data.power_loss_alarm = True
            else:
                self.data.power_loss_alarm = False

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
        if not self._client or not self._client.is_connected:
            raise UpdateFailed("Not connected to refrigerator")

        try:
            # Send command via protocol
            command = IcecoProtocol.set_left_temperature(temp)
            await self._client.write_gatt_char(IcecoProtocol.WRITE_UUID, command)

            # Store setpoint
            self.data.left_setpoint = temp
            _LOGGER.info("Set left zone temperature to %d°C", temp)

        except Exception as err:
            _LOGGER.error("Failed to set left temperature: %s", err)
            raise UpdateFailed(f"Failed to set temperature: {err}")

    async def async_set_right_temperature(self, temp: int) -> None:
        """Set right zone temperature and store setpoint."""
        if not self._client or not self._client.is_connected:
            raise UpdateFailed("Not connected to refrigerator")

        try:
            # Send command via protocol
            command = IcecoProtocol.set_right_temperature(temp)
            await self._client.write_gatt_char(IcecoProtocol.WRITE_UUID, command)

            # Store setpoint
            self.data.right_setpoint = temp
            _LOGGER.info("Set right zone temperature to %d°C", temp)

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

    async def async_shutdown(self) -> None:
        """Clean shutdown of coordinator."""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()

        if self._client and self._client.is_connected:
            await self._client.disconnect()
            _LOGGER.info("Disconnected from refrigerator")
