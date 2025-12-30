#!/usr/bin/env python3
"""
Hardware testing script for Iceco protocol library.

This script guides you through testing each aspect of the protocol
against the actual refrigerator hardware.
"""

import asyncio
import logging

from iceco_protocol import IcecoClient, IcecoStatus


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def test_discovery():
    """Step 1: Discover the refrigerator."""
    print("\n" + "="*60)
    print("TEST 1: Device Discovery")
    print("="*60)
    print("Scanning for BLE devices...")

    devices = await IcecoClient.discover(timeout=10.0)

    if devices:
        print(f"\nFound {len(devices)} devices:")
        for i, device in enumerate(devices, 1):
            print(f"\n{i}. Name: {device.name or 'Unknown'}")
            print(f"   Address: {device.address}")
        return devices
    else:
        print("\nNo devices found!")
        print("Make sure:")
        print("- Refrigerator is powered on")
        print("- Bluetooth is enabled on this system")
        print("- You're within range")
        return []


async def test_connection(mac_address: str):
    """Step 2: Test connection and status reading."""
    print("\n" + "="*60)
    print("TEST 2: Connection and Status Reading")
    print("="*60)
    print(f"Connecting to {mac_address}...")

    status_count = [0]  # Using list to modify in callback

    async def status_callback(status: IcecoStatus):
        status_count[0] += 1
        print(f"\n--- Status Update #{status_count[0]} ---")
        print(f"Left zone:  {status.left_temp:+03d}°C")
        print(f"Right zone: {status.right_temp:+03d}°C")
        print(f"Battery:    {status.battery_voltage:.1f}V (protection level {status.battery_protection_level})")
        print(f"Power:      {'ON' if status.power_on else 'OFF'}")

    try:
        async with IcecoClient(mac_address, status_callback=status_callback) as client:
            print("✓ Connected successfully!")

            # Wait for initial status
            print("\nWaiting for status notifications (10 seconds)...")
            await asyncio.sleep(10)

            if status_count[0] > 0:
                print(f"\n✓ Received {status_count[0]} status update(s)")
                return True
            else:
                print("\n✗ No status updates received")
                return False

    except Exception as e:
        print(f"\n✗ Connection failed: {e}")
        return False


async def test_commands(mac_address: str):
    """Step 3: Test sending commands."""
    print("\n" + "="*60)
    print("TEST 3: Command Testing")
    print("="*60)
    print("This will send test commands to the refrigerator.")
    print("Watch the refrigerator display for changes.\n")

    async def status_callback(status: IcecoStatus):
        print(f"Status: L={status.left_temp:+03d}°C R={status.right_temp:+03d}°C "
              f"Batt={status.battery_voltage:.1f}V Power={'ON' if status.power_on else 'OFF'}")

    try:
        async with IcecoClient(mac_address, status_callback=status_callback) as client:
            print("Connected. Monitoring status...\n")
            await asyncio.sleep(2)

            # Test temperature commands
            print("\n[TEST] Setting left zone to +5°C (refrigeration mode)...")
            await client.set_left_temperature(5)
            await asyncio.sleep(3)

            print("\n[TEST] Setting right zone to +3°C (refrigeration mode)...")
            await client.set_right_temperature(3)
            await asyncio.sleep(3)

            print("\n[TEST] Setting left zone to -18°C (freezing mode)...")
            await client.set_left_temperature(-18)
            await asyncio.sleep(3)

            # Toggle tests (be careful with these!)
            print("\n[TEST] Toggling ECO mode...")
            await client.toggle_eco_mode()
            await asyncio.sleep(3)

            print("\n[TEST] Toggling lock...")
            await client.toggle_lock()
            await asyncio.sleep(3)

            print("\n[TEST] Toggling lock again (unlock)...")
            await client.toggle_lock()
            await asyncio.sleep(3)

            print("\n✓ All command tests completed")
            print("Check the refrigerator to verify commands were received")

    except Exception as e:
        print(f"\n✗ Command test failed: {e}")
        raise


async def main():
    """Main test routine."""
    print("\n" + "="*60)
    print("ICECO REFRIGERATOR HARDWARE TEST")
    print("="*60)
    print("\nThis script will test the protocol library against your")
    print("Iceco refrigerator hardware.\n")

    # Step 1: Discovery
    devices = await test_discovery()
    if not devices:
        return

    # Get MAC address
    print("\n" + "="*60)
    print("Enter the MAC address of your refrigerator:")
    print("(Format: XX:XX:XX:XX:XX:XX)")
    print("="*60)
    mac_address = input("MAC Address: ").strip()

    if not mac_address:
        print("No MAC address provided. Exiting.")
        return

    # Step 2: Connection test
    if not await test_connection(mac_address):
        print("\nConnection test failed. Fix connection issues before proceeding.")
        return

    # Step 3: Command test
    print("\n" + "="*60)
    print("Ready to test commands.")
    print("WARNING: This will change refrigerator settings!")
    print("="*60)
    response = input("Proceed with command tests? (yes/no): ").strip().lower()

    if response == 'yes':
        await test_commands(mac_address)
    else:
        print("Command tests skipped.")

    print("\n" + "="*60)
    print("TESTING COMPLETE")
    print("="*60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        logging.exception("Exception details:")
