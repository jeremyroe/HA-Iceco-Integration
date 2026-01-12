"""Iceco Refrigerator integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_DEVICE_ADDRESS, DOMAIN
from .coordinator import IcecoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
_LOGGER.warning("ICECO __INIT__ MODULE LOADED")

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Iceco from a config entry."""
    _LOGGER.warning("ICECO ASYNC_SETUP_ENTRY CALLED - STARTING INTEGRATION SETUP")

    # Get device address from config
    address = entry.data[CONF_DEVICE_ADDRESS]

    # Get BLE device from Home Assistant's bluetooth integration
    ble_device = bluetooth.async_ble_device_from_address(
        hass, address, connectable=True
    )

    if not ble_device:
        raise ConfigEntryNotReady(
            f"Could not find Iceco refrigerator with address {address}"
        )

    # Create coordinator
    coordinator = IcecoDataUpdateCoordinator(hass, ble_device, entry.entry_id)

    # Perform initial connection and data fetch
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error("Failed to setup Iceco integration: %s", err)
        raise ConfigEntryNotReady(f"Failed to connect to refrigerator: {err}")

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward entry setup to platforms
    _LOGGER.warning("ICECO FORWARDING TO PLATFORMS: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.warning("ICECO PLATFORM SETUP COMPLETE")

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.warning("ICECO INTEGRATION SETUP COMPLETE")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Iceco integration")

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Cleanup coordinator
        coordinator: IcecoDataUpdateCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    _LOGGER.debug("Reloading Iceco integration due to options change")
    await hass.config_entries.async_reload(entry.entry_id)
