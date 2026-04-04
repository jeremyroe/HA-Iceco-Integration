"""Sensor platform for Iceco refrigerator."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_BATTERY_PROTECTION_LEVEL,
    CONF_DEVICE_ADDRESS,
    DOMAIN,
    ENTITY_BATTERY_VOLTAGE,
)
from .coordinator import IcecoDataUpdateCoordinator
from .helpers import build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Iceco sensor entities from a config entry."""
    coordinator: IcecoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([IcecoBatterySensor(coordinator, entry)])


class IcecoBatterySensor(CoordinatorEntity[IcecoDataUpdateCoordinator], SensorEntity):
    """Battery voltage sensor for Iceco refrigerator."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

    def __init__(
        self,
        coordinator: IcecoDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ADDRESS]}_{ENTITY_BATTERY_VOLTAGE}"
        self._attr_name = "Battery Voltage"

        self._attr_device_info = build_device_info(entry.data[CONF_DEVICE_ADDRESS])

    @property
    def native_value(self) -> float | None:
        """Return the battery voltage."""
        if not self.coordinator.data.status:
            return None

        return self.coordinator.data.status.battery_voltage

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data.status:
            return {}

        return {
            ATTR_BATTERY_PROTECTION_LEVEL: self.coordinator.data.status.battery_protection_level
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data.connection_state == "connected"
        )
