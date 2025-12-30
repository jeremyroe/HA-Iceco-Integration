#!/usr/bin/env python3
"""
Example script demonstrating the Iceco protocol library.

This script shows how to:
1. Discover Iceco refrigerators
2. Connect to a refrigerator
3. Read status
4. Control temperature and settings
"""

import asyncio
import logging

from iceco_protocol import IcecoClient, IcecoStatus


# Configure logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def status_callback(status: IcecoStatus):
    """
    Callback function that gets called whenever status is received.

    Args:
        status: Current refrigerator status
    """
    print("\n=== Status Update ===")
    print(f"Left zone:  {status.left_temp}°C")
    print(f"Right zone: {status.right_temp}°C")
    print(f"Battery:    {status.battery_voltage}V (protection level {status.battery_protection_level})")
    print(f"Power:      {'ON' if status.power_on else 'OFF'}")
    print("====================\n")


async def discover_devices():
    """Discover nearby BLE devices."""
    print("Scanning for BLE devices...")
    devices = await IcecoClient.discover(timeout=5.0)

    if devices:
        print("\nFound devices:")
        for device in devices:
            print(f"  Name: {device.name}")
            print(f"  Address: {device.address}")
            print(f"  RSSI: {device.rssi} dBm")
            print()
    else:
        print("No devices found")

    return devices


async def example_usage(mac_address: str):
    """
    Example of using the Iceco client.

    Args:
        mac_address: MAC address of the refrigerator (e.g., "XX:XX:XX:XX:XX:XX")
    """
    # Create client with status callback
    async with IcecoClient(mac_address, status_callback=status_callback) as client:
        print(f"Connected to {mac_address}")

        # Wait for initial status
        print("Waiting for initial status...")
        status = await client.get_status(timeout=10.0)

        if status:
            print("\nInitial status received!")
        else:
            print("\nWarning: No status received within timeout")

        # Example: Set left zone to freezing mode (-18°C)
        print("\nSetting left zone to -18°C (freezing mode)...")
        await client.set_left_temperature(-18)
        await asyncio.sleep(1)  # Wait for confirmation

        # Example: Set right zone to refrigeration mode (2°C)
        print("Setting right zone to +2°C (refrigeration mode)...")
        await client.set_right_temperature(2)
        await asyncio.sleep(1)

        # Keep connection alive to receive status updates
        print("\nMonitoring status for 30 seconds...")
        print("(Status updates will appear as they arrive)")
        await asyncio.sleep(30)


async def main():
    """Main entry point."""
    print("Iceco Refrigerator Protocol Library - Example\n")

    # Step 1: Discover devices
    print("=" * 50)
    print("Step 1: Device Discovery")
    print("=" * 50)
    devices = await discover_devices()

    if not devices:
        print("\nNo devices found. Make sure your refrigerator is powered on")
        print("and Bluetooth is enabled on your system.")
        return

    # Step 2: Connect and control
    # IMPORTANT: Replace with your refrigerator's actual MAC address
    mac_address = "XX:XX:XX:XX:XX:XX"

    print("\n" + "=" * 50)
    print("Step 2: Connect and Control")
    print("=" * 50)
    print(f"\nTo connect, update the MAC address in example.py")
    print(f"Current MAC address: {mac_address}")

    # Uncomment the following line after setting the correct MAC address
    # await example_usage(mac_address)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        logging.exception("Exception occurred")
