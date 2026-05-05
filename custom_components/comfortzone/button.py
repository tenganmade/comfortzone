"""Button entities for Comfortzone Heat Pump integration."""
import logging
from typing import Any, Dict, Optional, List

# Import helpers and constants
from homeassistant.helpers.event import async_call_later
from .const import DOMAIN, DELAY_REFRESH_AFTER_SET, CLEAR_TEXT_NAMES

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

# Import helper function and API client
from .api import ComfortzoneApiClient, ComfortzoneApiClientError, ComfortzoneApiCommandError, find_value_from_raw_data

_LOGGER = logging.getLogger(__name__)

# Config uses ClearTextNames for availability checks
BUTTON_ENTITIES_CONFIG: Dict[str, Dict[str, Any]] = {
    "reset_filter_alarm": {
        "property_set": "ResetFilterAlarm",
        "name": "Reset Filter Alarm", "icon": "mdi:filter-remove",
        "api_value": True,
        "availability_property": CLEAR_TEXT_NAMES["FILTER_ALARM"], # "Filter alarm (on/off)"
        "availability_active_value": "1", # String value indicating active state
    },
    "acknowledge_alarm": {
        "property_set": "AcknowledgeAlarm",
        "name": "Acknowledge Alarm", "icon": "mdi:bell-cancel",
        "api_value": True,
        "availability_property": CLEAR_TEXT_NAMES["ALARM_TEXT"], # "AlarmInClearText"
        "availability_active_value": None, # Special case: Active if NOT empty string
    },
}

async def async_setup_entry( hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,) -> None:
    """Set up the Comfortzone button entities."""
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]: _LOGGER.error("Comfortzone Heat Pump data not found for entry %s", entry.entry_id); return
    data = hass.data[DOMAIN][entry.entry_id]; coordinator: DataUpdateCoordinator = data.get("coordinator"); api_client: ComfortzoneApiClient = data.get("client")
    if not coordinator or not api_client: _LOGGER.error("Coordinator or API client not found for entry %s", entry.entry_id); return

    entities = []
    for suffix, config in BUTTON_ENTITIES_CONFIG.items():
        config["entity_suffix"] = suffix
        entities.append(ComfortzoneButtonEntity(coordinator, api_client, entry, suffix, config))
    async_add_entities(entities)


class ComfortzoneButtonEntity(CoordinatorEntity, ButtonEntity):
    """Representation of a Comfortzone Button entity with availability check."""

    def __init__( self, coordinator: DataUpdateCoordinator, api_client: ComfortzoneApiClient, entry: ConfigEntry, entity_suffix: str, config: dict,) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator); self._client = api_client; self._config = config; self.entry = entry; self._entity_suffix = entity_suffix
        self._attr_unique_id = f"{entry.entry_id}_{entity_suffix}"; self._attr_name = config["name"]; self._attr_icon = config.get("icon")
        self._attr_device_info = { "identifiers": {(DOMAIN, entry.entry_id)} }; self._api_value = config["api_value"];
        # These store the config for checking availability
        self._availability_property = config.get("availability_property")
        self._availability_active_value = config.get("availability_active_value")
        # Update initial availability
        self._update_availability()

    @property
    def suggested_object_id(self) -> str | None:
        """Suggest object ID."""
        return f"{DOMAIN}_{self._entity_suffix}"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator to update availability."""
        current_availability = self._attr_available
        self._update_availability()
        if self._attr_available != current_availability:
             if self.hass: self.async_write_ha_state()

    def _update_availability(self) -> None:
        """Update the entity's availability based on coordinator data."""
        new_availability = True # Assume available unless checked otherwise

        if self._availability_property: # Check only if an availability property is configured
            # Check coordinator status first
            if not self.coordinator.last_update_success or not self.coordinator.data or 'Values' not in self.coordinator.data.get("Data", {}):
                 new_availability = False
            else:
                values_list = self.coordinator.data.get("Data", {}).get("Values", [])
                # Find the value of the property that determines availability
                availability_value_str = find_value_from_raw_data(values_list, self._availability_property, "ClearTextName")

                if availability_value_str is None:
                    _LOGGER.debug("Availability property '%s' not found for button '%s'", self._availability_property, self.name)
                    new_availability = False # Property missing, cannot determine state
                else:
                    # --- CORRECTED LINE ---
                    # Special check for AlarmText (available if not empty string)
                    # Compare the name of the property we are checking (_availability_property)
                    if self._availability_property == CLEAR_TEXT_NAMES["ALARM_TEXT"]:
                         new_availability = (availability_value_str != "")
                    # --- END CORRECTION ---
                    # Normal check for other properties (e.g., Filter Alarm == "1")
                    else:
                         new_availability = (availability_value_str == self._availability_active_value)
        else:
             # No availability property defined, depend only on coordinator success
             new_availability = self.coordinator.last_update_success

        # Log only if availability changes
        if hasattr(self, "_attr_available") and self._attr_available != new_availability:
            _LOGGER.debug("Button '%s' availability changed to %s", self.name, new_availability)
        self._attr_available = new_availability


    async def _delayed_refresh(self, now) -> None:
        """Request coordinator refresh after a delay."""
        if self.coordinator and self.hass: _LOGGER.debug("Executing delayed coordinator refresh for %s triggered at %s", self.name or self.entity_id, now); await self.coordinator.async_request_refresh()
        else: _LOGGER.warning("Coordinator or HASS not available for %s delayed refresh.", self.name or self.entity_id)


    async def async_press(self) -> None:
        """Handle the button press."""
        # ... (Method remains the same as previous version - includes delayed refresh) ...
        if not self._attr_available: _LOGGER.warning("Attempted to press unavailable button: %s", self.name); return
        prop_set = self._config["property_set"]; _LOGGER.info("Activating action: %s (Value: %s)", self.name, self._api_value)
        try:
            success = await self._client.async_set_property(prop_set, self._api_value)
            if success:
                _LOGGER.info("Successfully activated action: %s", self.name)
                _LOGGER.debug("Scheduling coordinator refresh in %ss after pressing %s...", DELAY_REFRESH_AFTER_SET, self.name)
                async_call_later(self.hass, DELAY_REFRESH_AFTER_SET, self._delayed_refresh)
            else: _LOGGER.error("Failed to activate action %s via API", self.name)
        except (ComfortzoneApiCommandError, ComfortzoneApiClientError) as e: _LOGGER.error("API error activating action %s: %s", self.name, e)
