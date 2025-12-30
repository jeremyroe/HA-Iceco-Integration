"""Binary sensor platform for Iceco refrigerator."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_DEVIATION,
    ATTR_LAST_UPDATE,
    ATTR_SET_TEMPERATURE,
    ATTR_THRESHOLD,
    ATTR_TIMEOUT_MINUTES,
    CONF_DEVICE_ADDRESS,
    CONF_POWER_LOSS_TIMEOUT,
    CONF_TEMP_DEVIATION_THRESHOLD,
    DEFAULT_POWER_LOSS_TIMEOUT,
    DEFAULT_TEMP_DEVIATION_THRESHOLD,
    DOMAIN,
    ENTITY_POWER_LOSS_ALARM,
    ENTITY_TEMP_ALARM_LEFT,
    ENTITY_TEMP_ALARM_RIGHT,
)
from .coordinator import IcecoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Iceco binary sensor entities from a config entry."""
    coordinator: IcecoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            IcecoPowerLossAlarm(coordinator, entry),
            IcecoTempAlarm(coordinator, entry, "left"),
            IcecoTempAlarm(coordinator, entry, "right"),
        ]
    )


class IcecoPowerLossAlarm(
    CoordinatorEntity[IcecoDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor for power loss / offline alarm."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: IcecoDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ADDRESS]}_{ENTITY_POWER_LOSS_ALARM}"
        self._attr_name = "Power Loss Alarm"
        self._entry = entry

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_DEVICE_ADDRESS])},
            name="Iceco Refrigerator",
            manufacturer="Iceco",
            model="Dual Zone Refrigerator",
        )

    @property
    def is_on(self) -> bool:
        """Return True if power loss detected."""
        return self.coordinator.data.power_loss_alarm

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            ATTR_TIMEOUT_MINUTES: self._entry.options.get(
                CONF_POWER_LOSS_TIMEOUT, DEFAULT_POWER_LOSS_TIMEOUT
            )
        }

        if self.coordinator.data.last_update:
            attrs[ATTR_LAST_UPDATE] = self.coordinator.data.last_update.isoformat()

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Power loss alarm is always available to report connection issues
        return True


class IcecoTempAlarm(CoordinatorEntity[IcecoDataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor for temperature deviation alarm."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: IcecoDataUpdateCoordinator,
        entry: ConfigEntry,
        zone: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)

        self._zone = zone
        self._entry = entry

        entity_id = ENTITY_TEMP_ALARM_LEFT if zone == "left" else ENTITY_TEMP_ALARM_RIGHT
        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ADDRESS]}_{entity_id}"
        self._attr_name = f"{zone.capitalize()} Zone Temperature Alarm"

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_DEVICE_ADDRESS])},
            name="Iceco Refrigerator",
            manufacturer="Iceco",
            model="Dual Zone Refrigerator",
        )

    @property
    def is_on(self) -> bool:
        """Return True if temperature deviation alarm triggered."""
        if self._zone == "left":
            return self.coordinator.data.left_temp_alarm
        return self.coordinator.data.right_temp_alarm

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data.status:
            return {}

        # Get current temp and setpoint
        if self._zone == "left":
            actual = self.coordinator.data.status.left_temp
            setpoint = self.coordinator.data.left_setpoint
        else:
            actual = self.coordinator.data.status.right_temp
            setpoint = self.coordinator.data.right_setpoint

        attrs = {
            ATTR_CURRENT_TEMPERATURE: actual,
            ATTR_THRESHOLD: self._entry.options.get(
                CONF_TEMP_DEVIATION_THRESHOLD, DEFAULT_TEMP_DEVIATION_THRESHOLD
            ),
        }

        if setpoint is not None:
            attrs[ATTR_SET_TEMPERATURE] = setpoint
            attrs[ATTR_DEVIATION] = actual - setpoint

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data.connection_state == "connected"
        )
