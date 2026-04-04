"""Switch platform for Iceco refrigerator."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_ADDRESS,
    DOMAIN,
    ENTITY_CONNECTION,
    ENTITY_ECO_MODE,
    ENTITY_LOCK,
    ENTITY_POWER_SWITCH,
)
from .coordinator import IcecoDataUpdateCoordinator
from .helpers import build_device_info

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
            IcecoConnectionSwitch(coordinator, entry),
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

        self._attr_device_info = build_device_info(entry.data[CONF_DEVICE_ADDRESS])

    @property
    def is_on(self) -> bool | None:
        """Return True if power is on."""
        if not self.coordinator.data.status:
            return None

        return self.coordinator.data.status.power_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the power on."""
        if not self.is_on:
            # If disconnected (e.g. after a power-off), reconnect first.
            # Note: on some firmware versions, reconnecting BLE itself powers the fridge on.
            # Refresh state after reconnect before deciding whether to toggle.
            if self.coordinator.data.connection_state != "connected":
                await self.coordinator.async_manual_reconnect()
                await self.coordinator.async_request_refresh()
            if not self.is_on:
                await self.coordinator.async_toggle_power()
                await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the power off."""
        if self.is_on:
            # Toggle first, then disconnect. The fridge firmware uses an active BLE
            # connection as a keep-alive — without disconnecting, the fridge restarts.
            await self.coordinator.async_toggle_power()
            await self.coordinator.async_manual_disconnect()

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

        self._attr_device_info = build_device_info(entry.data[CONF_DEVICE_ADDRESS])

    @property
    def is_on(self) -> bool | None:
        """Return True if ECO mode is on, None if unknown."""
        return self.coordinator.data.eco_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn ECO mode on."""
        await self.coordinator.async_set_eco_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn ECO mode off (MAX mode)."""
        await self.coordinator.async_set_eco_mode(False)

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

        self._attr_device_info = build_device_info(entry.data[CONF_DEVICE_ADDRESS])

    @property
    def is_on(self) -> bool | None:
        """Return True if control panel is locked."""
        return self.coordinator.data.locked

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Lock the control panel."""
        await self.coordinator.async_set_lock(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unlock the control panel."""
        await self.coordinator.async_set_lock(False)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data.connection_state == "connected"
        )


class IcecoConnectionSwitch(CoordinatorEntity[IcecoDataUpdateCoordinator], SwitchEntity):
    """Switch entity for BLE connection control."""

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(
        self,
        coordinator: IcecoDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ADDRESS]}_{ENTITY_CONNECTION}"
        self._attr_name = "BLE Connection"

        self._attr_device_info = build_device_info(entry.data[CONF_DEVICE_ADDRESS])

    @property
    def is_on(self) -> bool:
        """Return True if connected."""
        return self.coordinator.data.connection_state == "connected"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Connect to refrigerator."""
        if self.coordinator.data.connection_state != "connected":
            await self.coordinator.async_manual_reconnect()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disconnect from refrigerator (allows mobile app access)."""
        if self.coordinator.data.connection_state == "connected":
            await self.coordinator.async_manual_disconnect()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # This switch should always be available to allow reconnection
        return True
