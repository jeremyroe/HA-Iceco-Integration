"""Switch platform for Iceco refrigerator."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_ADDRESS,
    DOMAIN,
    ENTITY_ECO_MODE,
    ENTITY_LOCK,
    ENTITY_POWER_SWITCH,
)
from .coordinator import IcecoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Iceco switch entities from a config entry."""
    coordinator: IcecoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            IcecoPowerSwitch(coordinator, entry),
            IcecoEcoModeSwitch(coordinator, entry),
            IcecoLockSwitch(coordinator, entry),
        ]
    )


class IcecoPowerSwitch(CoordinatorEntity[IcecoDataUpdateCoordinator], SwitchEntity):
    """Switch entity for refrigerator power."""

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(
        self,
        coordinator: IcecoDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ADDRESS]}_{ENTITY_POWER_SWITCH}"
        self._attr_name = "Power"

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_DEVICE_ADDRESS])},
            name="Iceco Refrigerator",
            manufacturer="Iceco",
            model="Dual Zone Refrigerator",
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if power is on."""
        if not self.coordinator.data.status:
            return None

        return self.coordinator.data.status.power_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the power on."""
        if not self.is_on:
            await self.coordinator.async_toggle_power()
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the power off."""
        if self.is_on:
            await self.coordinator.async_toggle_power()
            await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data.connection_state == "connected"
        )


class IcecoEcoModeSwitch(CoordinatorEntity[IcecoDataUpdateCoordinator], SwitchEntity):
    """Switch entity for ECO/MAX mode."""

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: IcecoDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ADDRESS]}_{ENTITY_ECO_MODE}"
        self._attr_name = "ECO Mode"
        self._state = False  # Optimistic state tracking

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_DEVICE_ADDRESS])},
            name="Iceco Refrigerator",
            manufacturer="Iceco",
            model="Dual Zone Refrigerator",
        )

    @property
    def is_on(self) -> bool:
        """Return True if ECO mode is on."""
        # Protocol doesn't report ECO mode status, use optimistic state
        return self._state

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn ECO mode on."""
        if not self._state:
            await self.coordinator.async_toggle_eco_mode()
            self._state = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn ECO mode off (MAX mode)."""
        if self._state:
            await self.coordinator.async_toggle_eco_mode()
            self._state = False
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data.connection_state == "connected"
        )


class IcecoLockSwitch(CoordinatorEntity[IcecoDataUpdateCoordinator], SwitchEntity):
    """Switch entity for control panel lock."""

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: IcecoDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ADDRESS]}_{ENTITY_LOCK}"
        self._attr_name = "Control Panel Lock"
        self._state = False  # Optimistic state tracking

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_DEVICE_ADDRESS])},
            name="Iceco Refrigerator",
            manufacturer="Iceco",
            model="Dual Zone Refrigerator",
        )

    @property
    def is_on(self) -> bool:
        """Return True if lock is on."""
        # Protocol doesn't report lock status, use optimistic state
        return self._state

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Lock the control panel."""
        if not self._state:
            await self.coordinator.async_toggle_lock()
            self._state = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unlock the control panel."""
        if self._state:
            await self.coordinator.async_toggle_lock()
            self._state = False
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data.connection_state == "connected"
        )
