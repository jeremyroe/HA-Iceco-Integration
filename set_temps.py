#!/usr/bin/env python3
"""Quick script to set specific temperatures."""

import asyncio
from iceco_protocol import IcecoClient

FRIDGE_ADDRESS = "00384EDB-14E6-AEB7-5EE2-55246830D7CE"


async def main():
    print("Connecting to refrigerator...")

    async with IcecoClient(FRIDGE_ADDRESS) as client:
        print("Connected!")

        # Wait a moment for initial connection
        await asyncio.sleep(1)

        # Set left to +4°C (39F)
        print("Setting left zone to +4°C (39F)...")
        await client.set_left_temperature(4)
        await asyncio.sleep(2)

        # Set right to -18°C (0F)
        print("Setting right zone to -18°C (0F)...")
        await client.set_right_temperature(-18)
        await asyncio.sleep(2)

        print("\n✓ Temperatures set back to original:")
        print("  Left:  +4°C (39F) - Refrigerator mode")
        print("  Right: -18°C (0F) - Freezer mode")


if __name__ == "__main__":
    asyncio.run(main())
