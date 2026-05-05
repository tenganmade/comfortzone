"""Number entities for Comfortzone Heat Pump integration."""
import logging
from typing import Optional

# Import helpers and constants
from homeassistant.helpers.event import async_call_later
from .const import DOMAIN, DELAY_REFRESH_AFTER_SET, CLEAR_TEXT_NAMES

# Import base classes - RestoreNumber is NOT needed anymore
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

# Import helper function and API client
from .api import ComfortzoneApiClient, ComfortzoneApiClientError, ComfortzoneApiCommandError, find_value_from_raw_data

_LOGGER = logging.getLogger(__name__)

# Config uses ClearTextNames and reads state from API
NUMBER_ENTITIES_CONFIG = [
    {
        "entity_suffix": "hot_water_temp_setpoint",
        "property_set": "SetHotWaterTemp",
        "property_read": CLEAR_TEXT_NAMES["TARGET_HW_TEMP"], # Reads API value
        "name": "Hot Water Target Temperature", "icon": "mdi:water-boiler", "unit": UnitOfTemperature.CELSIUS,
        "min": 30.0, "max": 65.0, "step": 1.0, "mode": NumberMode.BOX,
    }, {
        "entity_suffix": "holiday_reduction_days",
        "property_set": "SetHolidayReductionDays",
        "property_read": CLEAR_TEXT_NAMES["HOLIDAY_DAYS"],
        "name": "Holiday Reduction Days", "icon": "mdi:calendar-arrow-right", "unit": UnitOfTime.DAYS,
        "min": 0, "max": 9, "step": 1, "mode": NumberMode.BOX,
    }, {
        "entity_suffix": "heat_curve",
        "property_set": "SetHeatCurve",
        "property_read": CLEAR_TEXT_NAMES["HEATING_CURVE"], # Reads API value
        "name": "Heat Curve", "icon": "mdi:chart-line", "unit": None,
        "min": 0.0, "max": 6.0, "step": 0.1, "mode": NumberMode.SLIDER,
    },
]

async def async_setup_entry( hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,) -> None:
    """Set up the Comfortzone number entities."""
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]: _LOGGER.error("Comfortzone Heat Pump data not found for entry %s", entry.entry_id); return
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DataUpdateCoordinator = data.get("coordinator")
    api_client: ComfortzoneApiClient = data.get("client")
    if not coordinator or not api_client: _LOGGER.error("Coordinator or API client not found for entry %s", entry.entry_id); return

    entities = []
    for config in NUMBER_ENTITIES_CONFIG:
        if "entity_suffix" in config and "property_set" in config:
             entities.append(ComfortzoneNumberEntity(coordinator, api_client, entry, config))
        else: _LOGGER.error("Invalid number entity config found: %s", config)
    async_add_entities(entities)


# Removed RestoreNumber mixin
class ComfortzoneNumberEntity(CoordinatorEntity, NumberEntity):
    """Representation of a Comfortzone Number entity."""
    _attr_native_value: float | None = None

    def __init__( self, coordinator: DataUpdateCoordinator, api_client: ComfortzoneApiClient, entry: ConfigEntry, config: dict,) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._client = api_client
        self._config = config
        # self._needs_restore = config["restore"] # Removed restore flag
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{config['entity_suffix']}"
        self._attr_name = config["name"]
        self._attr_icon = config.get("icon")
        self._attr_native_unit_of_measurement = config.get("unit")
        self._attr_native_min_value = config["min"]
        self._attr_native_max_value = config["max"]
        self._attr_native_step = config["step"]
        self._attr_mode = config["mode"]
        self._attr_device_info = { "identifiers": {(DOMAIN, entry.entry_id)} }
        self._attr_native_value = None
        self._attr_available = self.coordinator.last_update_success

        if self.coordinator.data: self._update_state_from_coordinator()

    @property
    def suggested_object_id(self) -> str | None:
        """Suggest object ID."""
        suffix = self._config.get("entity_suffix"); return f"{DOMAIN}_{suffix}" if suffix else None

    # async_added_to_hass removed (no restore needed)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Always update state from coordinator now (unless property_read is somehow None)
        if self._config.get("property_read") is not None:
             current_value = self._attr_native_value
             current_availability = self._attr_available
             self._update_state_from_coordinator()
             if self._attr_native_value != current_value or self._attr_available != current_availability:
                  if self.hass: self.async_write_ha_state()

    def _update_state_from_coordinator(self) -> None:
        """Update the entity state from coordinator data."""
        prop_read = self._config.get("property_read")
        if prop_read is None: return # Should not happen for configured entities

        new_value = self._attr_native_value
        new_availability = True

        # Data structure is now direct response from RawData
        if not self.coordinator.last_update_success or not self.coordinator.data or 'Values' not in self.coordinator.data.get("Data", {}):
            new_availability = False
        else:
            values_list = self.coordinator.data.get("Data", {}).get("Values", [])
            value_str = find_value_from_raw_data(values_list, prop_read, "ClearTextName")

            if value_str is not None:
                try:
                    if self.native_unit_of_measurement == UnitOfTime.DAYS: value_num = int(value_str)
                    else: value_num = float(value_str)
                    new_value = max(self.native_min_value, min(self.native_max_value, value_num))
                except (TypeError, ValueError): _LOGGER.warning("Could not parse number value for %s from '%s'", self.name, value_str); new_availability = False
            else: _LOGGER.debug("Read property '%s' not found for %s", prop_read, self.name); new_availability = False

        self._attr_available = new_availability
        self._attr_native_value = new_value if new_availability else None

    async def _delayed_refresh(self, now) -> None:
        """Request coordinator refresh after a delay."""
        if self.coordinator and self.hass: _LOGGER.debug("Executing delayed coordinator refresh for %s triggered at %s", self.name or self.entity_id, now); await self.coordinator.async_request_refresh()
        else: _LOGGER.warning("Coordinator or HASS not available for %s delayed refresh.", self.name or self.entity_id)

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        prop_set = self._config["property_set"]
        try:
            clamped_value = max(self.native_min_value, min(self.native_max_value, value))
            value_to_send = int(clamped_value) if self.native_step == 1.0 else clamped_value

            _LOGGER.debug("[%s] Calling async_set_property: PropertyName=%s, Value=%s (Type: %s)", self.name, prop_set, value_to_send, type(value_to_send))
            success = await self._client.async_set_property(prop_set, value_to_send)

            if success:
                _LOGGER.info("Successfully requested %s change to %s", self.name, value_to_send)
                # Optimistic update to show user feedback
                self._attr_native_value = clamped_value
                self.async_write_ha_state()

                # Schedule refresh (now always happens as property_read exists)
                _LOGGER.debug("Scheduling coordinator refresh in %ss after setting %s...", DELAY_REFRESH_AFTER_SET, self.name)
                async_call_later(self.hass, DELAY_REFRESH_AFTER_SET, self._delayed_refresh)
            else:
                 _LOGGER.error("Failed to set %s via API (API method returned False)", self.name)
        except (ComfortzoneApiCommandError, ComfortzoneApiClientError) as e: _LOGGER.error("API error setting %s: %s", self.name, e)
        except ValueError: _LOGGER.error("Invalid value %s provided for %s", value, self.name)
