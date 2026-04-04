"""Shared helpers for Iceco integration entities."""
from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def build_device_info(address: str) -> DeviceInfo:
    """Return DeviceInfo for an Iceco device identified by BLE address."""
    return DeviceInfo(
        identifiers={(DOMAIN, address)},
        name="Iceco Refrigerator",
        manufacturer="Iceco",
        model="Dual Zone Refrigerator",
    )
