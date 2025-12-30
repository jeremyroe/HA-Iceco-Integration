#!/usr/bin/env python3
"""
Test improved discovery and device identification.

This script demonstrates the HA integration setup flow:
1. Discover Iceco devices by service UUID
2. Identify each device by reading its status
"""

import asyncio
import logging

from iceco_protocol import IcecoClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def main():
    print("=" * 60)
    print("ICECO DEVICE DISCOVERY TEST")
    print("=" * 60)
    print("\nStep 1: Discovering Iceco devices by service UUID FFF0...")
    print("-" * 60)

    # Discover devices using service UUID filtering
    devices = await IcecoClient.discover(timeout=10.0)

    if not devices:
        print("\n❌ No Iceco devices found!")
        print("\nTroubleshooting:")
        print("- Ensure refrigerator is powered on")
        print("- Ensure it's not connected to the mobile app")
        print("- Try moving closer to the device")
        return

    print(f"\n✓ Found {len(devices)} Iceco device(s)\n")

    # Identify each device
    print("Step 2: Identifying devices by reading their status...")
    print("-" * 60)

    for i, device in enumerate(devices, 1):
        print(f"\nDevice {i}:")
        print(f"  Name:    {device.name or 'Unknown'}")
        print(f"  Address: {device.address}")

        try:
            info = await IcecoClient.identify_device(device.address, timeout=5.0)

            print(f"  Status:")
            print(f"    Left temp:  {info['left_temp']:+3d}°C")
            print(f"    Right temp: {info['right_temp']:+3d}°C")
            print(f"    Battery:    {info['battery_voltage']:.1f}V")
            print(f"    Power:      {'ON' if info['power_on'] else 'OFF'}")

        except asyncio.TimeoutError:
            print("  ⚠ Could not read status (timeout)")
        except Exception as e:
            print(f"  ❌ Error: {e}")

    print("\n" + "=" * 60)
    print("DISCOVERY TEST COMPLETE")
    print("=" * 60)
    print("\nThis discovery method will be used in the HA integration")
    print("to help users identify and select their refrigerator.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user")
