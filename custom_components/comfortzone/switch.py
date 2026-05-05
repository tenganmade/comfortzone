"""Switch entities for Comfortzone Heat Pump integration."""
import logging
from typing import Any, Dict, Optional, List

# Import helpers and constants
from homeassistant.helpers.event import async_call_later
from .const import DOMAIN, DELAY_REFRESH_AFTER_SET, CLEAR_TEXT_NAMES

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

# Import helper function and API client
from .api import ComfortzoneApiClient, ComfortzoneApiClientError, ComfortzoneApiCommandError, find_value_from_raw_data

_LOGGER = logging.getLogger(__name__)

# Config uses ClearTextName and defines API/Read values
SWITCH_ENTITIES_CONFIG: Dict[str, Dict[str, Any]] = {
    "hot_water_extra": {
        "property_set": "SetHotWaterExtraEnabled",
        "property_read": CLEAR_TEXT_NAMES["HW_EXTRA_MODE"],
        "name": "Hot Water Extra", "icon": "mdi:water-plus",
        "api_on": 1, # Value to SEND for ON
        "api_off": 0, # Value to SEND for OFF
        "read_on_value": "1" # String value expected from API READ for ON state
    },
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Comfortzone switch entities."""
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]: _LOGGER.error("Comfortzone Heat Pump data not found for entry %s", entry.entry_id); return
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DataUpdateCoordinator = data.get("coordinator")
    api_client: ComfortzoneApiClient = data.get("client")
    if not coordinator or not api_client: _LOGGER.error("Coordinator or API client not found for entry %s", entry.entry_id); return

    entities = []
    for suffix, config in SWITCH_ENTITIES_CONFIG.items():
        config["entity_suffix"] = suffix
        entities.append(ComfortzoneSwitchEntity(coordinator, api_client, entry, suffix, config))

    async_add_entities(entities)


class ComfortzoneSwitchEntity(CoordinatorEntity, SwitchEntity):
    """Representation of a Comfortzone Switch entity."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api_client: ComfortzoneApiClient,
        entry: ConfigEntry,
        entity_suffix: str,
        config: dict,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._client = api_client
        self._config = config
        self.entry = entry
        self._entity_suffix = entity_suffix

        self._attr_unique_id = f"{entry.entry_id}_{entity_suffix}"
        self._attr_name = config["name"]
        self._attr_icon = config.get("icon")
        self._attr_device_info = { "identifiers": {(DOMAIN, entry.entry_id)} }
        self._api_on_value = config["api_on"]
        self._api_off_value = config["api_off"]
        self._read_on_value = config["read_on_value"]
        self._attr_is_on = None
        self._attr_available = self.coordinator.last_update_success

        if self.coordinator.data:
            self._update_state_from_coordinator()

    @property
    def suggested_object_id(self) -> str | None:
        """Suggest object ID."""
        return f"{DOMAIN}_{self._entity_suffix}"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        current_availability = self._attr_available
        current_is_on = self._attr_is_on
        self._update_state_from_coordinator()
        if self._attr_is_on != current_is_on or self._attr_available != current_availability:
            if self.hass: self.async_write_ha_state()

    def _update_state_from_coordinator(self) -> None:
        """Update the entity state from coordinator data."""
        new_state = self._attr_is_on
        new_availability = True

        # Data structure is now direct response from RawData
        if not self.coordinator.last_update_success or not self.coordinator.data or 'Values' not in self.coordinator.data.get("Data", {}):
            new_availability = False
        else:
            values_list = self.coordinator.data.get("Data", {}).get("Values", [])
            prop_read = self._config["property_read"]
            value_str = find_value_from_raw_data(values_list, prop_read, "ClearTextName")

            if value_str is not None:
                 new_state = (value_str == self._read_on_value)
                 _LOGGER.debug("Switch %s read value '%s', compared to '%s', is_on=%s", self.name, value_str, self._read_on_value, new_state)
            else:
                 _LOGGER.debug("Read property %s not found for switch %s", prop_read, self.name)
                 new_availability = False

        self._attr_available = new_availability
        self._attr_is_on = new_state if new_availability else None

    async def _delayed_refresh(self, now) -> None:
        """Request coordinator refresh after a delay."""
        if self.coordinator and self.hass: _LOGGER.debug("Executing delayed coordinator refresh for %s triggered at %s", self.name or self.entity_id, now); await self.coordinator.async_request_refresh()
        else: _LOGGER.warning("Coordinator or HASS not available for %s delayed refresh.", self.name or self.entity_id)


    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self._async_set_state(self._api_on_value, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self._async_set_state(self._api_off_value, False)

    async def _async_set_state(self, api_value: Any, expected_state: bool) -> None:
        """Send the command to set the state."""
        prop_set = self._config["property_set"]
        _LOGGER.info("Setting %s to: %s (API value: %s)", self.name, "ON" if expected_state else "OFF", api_value)
        try:
            success = await self._client.async_set_property(prop_set, api_value)
            if success:
                _LOGGER.info("Successfully requested %s change to %s", self.name, "ON" if expected_state else "OFF")
                self._attr_is_on = expected_state
                self.async_write_ha_state()
                # Schedule refresh using constant
                _LOGGER.debug("Scheduling coordinator refresh in %ss after setting %s...", DELAY_REFRESH_AFTER_SET, self.name)
                async_call_later(self.hass, DELAY_REFRESH_AFTER_SET, self._delayed_refresh)
            else:
                 _LOGGER.error("Failed to set %s via API", self.name)
        except (ComfortzoneApiCommandError, ComfortzoneApiClientError) as e:
            _LOGGER.error("API error setting %s: %s", self.name, e)
