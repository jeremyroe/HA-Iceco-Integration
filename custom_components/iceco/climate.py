"""Climate platform for Iceco refrigerator."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    PRESET_NONE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_SET_TEMPERATURE,
    CONF_DEVICE_ADDRESS,
    DOMAIN,
    ENTITY_CLIMATE_LEFT,
    ENTITY_CLIMATE_RIGHT,
    MAX_TEMP,
    MIN_TEMP,
    TEMP_STEP,
)
from .coordinator import IcecoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
_LOGGER.warning("ICECO CLIMATE MODULE LOADED - THIS SHOULD APPEAR IN LOGS")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Iceco climate entities from a config entry."""
    coordinator: IcecoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            IcecoClimate(coordinator, entry, "left"),
            IcecoClimate(coordinator, entry, "right"),
        ]
    )


class IcecoClimate(CoordinatorEntity[IcecoDataUpdateCoordinator], ClimateEntity):
    """Climate entity for Iceco temperature zone."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_hvac_modes = [HVACMode.COOL]  # Only cooling mode, power controlled by switch
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    _attr_preset_modes = ["Refrigeration", "Freezing"]
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = TEMP_STEP
    _enable_turn_on_off_backwards_compatibility = False  # Disable HVAC mode control

    def __init__(
        self,
        coordinator: IcecoDataUpdateCoordinator,
        entry: ConfigEntry,
        zone: str,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)

        self._zone = zone
        self._attr_unique_id = (
            f"{entry.data[CONF_DEVICE_ADDRESS]}_{ENTITY_CLIMATE_LEFT if zone == 'left' else ENTITY_CLIMATE_RIGHT}"
        )
        self._attr_name = f"{zone.capitalize()} Zone"

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_DEVICE_ADDRESS])},
            name="Iceco Refrigerator",
            manufacturer="Iceco",
            model="Dual Zone Refrigerator",
        )

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        # SECONDARY notification contains current temps
        if self._zone == "left":
            current = self.coordinator.data.left_current_temp
        else:
            current = self.coordinator.data.right_current_temp

        return float(current) if current is not None else None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        # SECONDARY also contains setpoints - when at target, they match current
        # We track user changes locally in the coordinator
        if self._zone == "left":
            # Use the value we set locally, falls back to reported value
            return float(self.coordinator.data.left_setpoint) if self.coordinator.data.left_setpoint is not None else None
        else:
            return float(self.coordinator.data.right_setpoint) if self.coordinator.data.right_setpoint is not None else None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        # Zone is always in cooling mode (power controlled by main switch)
        return HVACMode.COOL

    @property
    def hvac_action(self) -> str | None:
        """Return current HVAC action - hide the mode indicator."""
        # Don't show hvac action to keep UI clean
        return None

    @property
    def preset_mode(self) -> str:
        """Return current preset mode based on temperature."""
        # Determine mode based on current or target temperature
        temp = self.target_temperature or self.current_temperature

        # Since we're using Fahrenheit, freezing is < 32°F
        if temp is not None and temp < 32:
            return "Freezing"
        return "Refrigeration"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {}

        if self._zone == "left":
            setpoint = self.coordinator.data.left_setpoint
        else:
            setpoint = self.coordinator.data.right_setpoint

        if setpoint is not None:
            attrs[ATTR_SET_TEMPERATURE] = setpoint

        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        _LOGGER.warning("ASYNC_SET_TEMPERATURE CALLED - kwargs=%s", kwargs)
        temperature = kwargs.get(ATTR_TEMPERATURE)

        if temperature is None:
            _LOGGER.warning("async_set_temperature called with no temperature value")
            return

        temp_int = int(temperature)
        _LOGGER.info(
            "Setting %s zone temperature to %d°F (from %.1f°F input)",
            self._zone,
            temp_int,
            temperature,
        )

        try:
            if self._zone == "left":
                await self.coordinator.async_set_left_temperature(temp_int)
            else:
                await self.coordinator.async_set_right_temperature(temp_int)

            # Request immediate update
            await self.coordinator.async_request_refresh()
            _LOGGER.info("Temperature set command completed for %s zone", self._zone)

        except Exception as err:
            _LOGGER.error("Failed to set temperature for %s zone: %s", self._zone, err)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode - only COOL supported."""
        # HVAC mode is always COOL, power controlled by main power switch
        pass

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode by adjusting temperature range."""
        # Preset mode is informational based on temperature
        # Users set temperature directly, mode follows automatically
        if preset_mode == "Freezing":
            # Suggest typical freezer temp if switching to freezing
            await self.async_set_temperature(temperature=0)
        elif preset_mode == "Refrigeration":
            # Suggest typical refrigerator temp if switching to refrigeration
            await self.async_set_temperature(temperature=38)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data.connection_state == "connected"
        )
