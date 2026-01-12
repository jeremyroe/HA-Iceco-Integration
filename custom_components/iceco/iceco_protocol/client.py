"""
Iceco Refrigerator BLE Client

This module provides the main client class for connecting to and controlling
an Iceco refrigerator via Bluetooth Low Energy.
"""

import asyncio
import logging
from typing import Optional, Callable, Awaitable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from .protocol import IcecoProtocol, IcecoStatus

logger = logging.getLogger(__name__)


class IcecoClient:
    """
    BLE client for Iceco refrigerator.

    Handles connection, command sending, and status notifications.

    Example:
        async with IcecoClient("XX:XX:XX:XX:XX:XX") as client:
            await client.set_left_temperature(-18)
            status = await client.get_status()
            print(f"Left zone: {status.left_temp}°C")
    """

    def __init__(
        self,
        address: str,
        status_callback: Optional[Callable[[IcecoStatus], Awaitable[None]]] = None,
    ):
        """
        Initialize the Iceco client.

        Args:
            address: Bluetooth MAC address of the refrigerator
            status_callback: Optional async callback for status updates
        """
        self.address = address
        self.status_callback = status_callback
        self._client: Optional[BleakClient] = None
        self._latest_status: Optional[IcecoStatus] = None
        self._status_event = asyncio.Event()

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """
        Connect to the refrigerator and start receiving notifications.

        Raises:
            Exception: If connection fails
        """
        logger.info(f"Connecting to Iceco refrigerator at {self.address}")

        self._client = BleakClient(self.address)
        await self._client.connect()

        # Start receiving notifications from characteristic FFF4
        await self._client.start_notify(
            IcecoProtocol.NOTIFY_UUID,
            self._notification_handler
        )

        logger.info("Connected and subscribed to notifications")

    async def disconnect(self) -> None:
        """Disconnect from the refrigerator."""
        if self._client and self._client.is_connected:
            await self._client.disconnect()
            logger.info("Disconnected from refrigerator")

    @property
    def is_connected(self) -> bool:
        """Check if currently connected to the refrigerator."""
        return self._client is not None and self._client.is_connected

    def _notification_handler(self, sender: int, data: bytes) -> None:
        """
        Handle incoming notifications from the refrigerator.

        This is called automatically when the refrigerator sends status updates.

        Args:
            sender: Handle that sent the notification
            data: Raw notification data
        """
        logger.debug(f"Received notification from handle {sender}: {data}")

        # Parse the notification
        status = IcecoProtocol.parse_notification(data)

        if status:
            logger.debug(f"Parsed status: {status}")
            self._latest_status = status
            self._status_event.set()

            # Call user callback if provided
            if self.status_callback:
                asyncio.create_task(self.status_callback(status))
        else:
            logger.warning(f"Failed to parse notification: {data}")

    async def _send_command(self, command: bytes) -> None:
        """
        Send a command to the refrigerator.

        Args:
            command: Command bytes to send

        Raises:
            RuntimeError: If not connected
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to refrigerator")

        logger.debug(f"Sending command: {command}")
        await self._client.write_gatt_char(IcecoProtocol.WRITE_UUID, command)

    async def get_status(self, timeout: float = 5.0) -> Optional[IcecoStatus]:
        """
        Get the latest status from the refrigerator.

        Waits for a status notification if none has been received yet.

        Args:
            timeout: Maximum time to wait for status (seconds)

        Returns:
            IcecoStatus object or None if timeout
        """
        if self._latest_status:
            return self._latest_status

        # Wait for first status notification
        try:
            await asyncio.wait_for(self._status_event.wait(), timeout=timeout)
            return self._latest_status
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for status notification")
            return None

    async def set_left_temperature(self, temp: int) -> None:
        """
        Set the left zone temperature.

        Args:
            temp: Temperature in Celsius
                  Negative values = freezing mode (e.g., -18)
                  Positive values = refrigeration mode (e.g., 4)
        """
        command = IcecoProtocol.set_left_temperature(temp)
        await self._send_command(command)
        logger.info(f"Set left zone temperature to {temp}°C")

    async def set_right_temperature(self, temp: int) -> None:
        """
        Set the right zone temperature.

        Args:
            temp: Temperature in Celsius
                  Negative values = freezing mode (e.g., -18)
                  Positive values = refrigeration mode (e.g., 2)
        """
        command = IcecoProtocol.set_right_temperature(temp)
        await self._send_command(command)
        logger.info(f"Set right zone temperature to {temp}°C")

    async def toggle_power(self) -> None:
        """
        Toggle power state (on/off).

        Note: The same command is used for both turning on and off.
        """
        command = IcecoProtocol.toggle_power()
        await self._send_command(command)
        logger.info("Toggled power state")

    async def toggle_eco_mode(self) -> None:
        """Toggle ECO/MAX mode."""
        command = IcecoProtocol.toggle_eco_mode()
        await self._send_command(command)
        logger.info("Toggled ECO/MAX mode")

    async def toggle_lock(self) -> None:
        """Toggle control panel lock."""
        command = IcecoProtocol.toggle_lock()
        await self._send_command(command)
        logger.info("Toggled control panel lock")

    @staticmethod
    async def discover(timeout: float = 5.0) -> list[BLEDevice]:
        """
        Discover nearby Iceco refrigerators by service UUID.

        Filters for devices advertising the Iceco service UUID (FFF0).

        Args:
            timeout: Scan duration in seconds

        Returns:
            List of discovered Iceco BLE devices
        """
        logger.info(f"Scanning for Iceco devices for {timeout} seconds...")
        devices = await BleakScanner.discover(
            timeout=timeout,
            service_uuids=[IcecoProtocol.SERVICE_UUID]
        )

        logger.info(f"Found {len(devices)} Iceco device(s)")
        for device in devices:
            logger.info(f"  {device.name or 'Unknown'}: {device.address}")

        return devices

    @staticmethod
    async def identify_device(address: str, timeout: float = 5.0) -> dict:
        """
        Connect to a device and read its current status to help identify it.

        Useful during setup to distinguish between multiple Iceco devices.

        Args:
            address: BLE MAC address of the device
            timeout: Timeout for connection and status read

        Returns:
            Dictionary with device info including current temperatures

        Raises:
            TimeoutError: If unable to get status within timeout
            Exception: If connection fails
        """
        logger.info(f"Identifying device at {address}...")

        async with IcecoClient(address) as client:
            status = await client.get_status(timeout=timeout)

            if status:
                return {
                    "address": address,
                    "left_temp": status.left_temp,
                    "right_temp": status.right_temp,
                    "battery_voltage": status.battery_voltage,
                    "power_on": status.power_on,
                }
            else:
                raise TimeoutError(f"No status received from device {address}")

