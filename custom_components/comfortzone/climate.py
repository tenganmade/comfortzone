"""Climate platform for Comfortzone Heat Pump."""
import logging
from typing import Any, Dict, Optional, List

from homeassistant.helpers.event import async_call_later
from .const import DOMAIN, TEMP_VALUE_FOR_OFF, DELAY_REFRESH_AFTER_SET, CLEAR_TEXT_NAMES

from homeassistant.components.climate import ( ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode )
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import ( CoordinatorEntity, DataUpdateCoordinator )

# Import helper function and API client
from .api import ComfortzoneApiClient, ComfortzoneApiClientError, ComfortzoneApiCommandError, find_value_from_raw_data

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry( hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,) -> None:
    """Set up the Comfortzone climate entity."""
    # ... (Setup remains the same) ...
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]: _LOGGER.error("Comfortzone Heat Pump data not found for entry %s", entry.entry_id); return
    data = hass.data[DOMAIN][entry.entry_id]; coordinator: DataUpdateCoordinator = data.get("coordinator"); api_client: ComfortzoneApiClient = data.get("client")
    if not coordinator or not api_client: _LOGGER.error("Coordinator or API client not found for entry %s", entry.entry_id); return
    async_add_entities([ComfortzoneRX95ClimateEntity(coordinator, entry, api_client)])

class ComfortzoneRX95ClimateEntity(CoordinatorEntity, ClimateEntity):
    """Representation of a Comfortzone Heat Pump Heat Pump."""
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_name = "Comfortzone Climate"
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_min_temp = 10.0
    _attr_max_temp = 25.0
    _attr_target_temperature_step = 0.5

    def __init__( self, coordinator: DataUpdateCoordinator, entry: ConfigEntry, api_client: ComfortzoneApiClient,) -> None:
        """Initialize the climate entity."""
        # ... (__init__ remains the same) ...
        super().__init__(coordinator); self.entry = entry; self._client = api_client; self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_hvac_mode = HVACMode.HEAT; self._attr_current_temperature = None; self._attr_target_temperature = None; self._attr_hvac_action = None; self._attr_extra_state_attributes = {}

    @property
    def suggested_object_id(self) -> str | None:
         """Suggest object ID based on unique ID."""
         # ... (remains the same) ...
         if self._attr_unique_id and self._attr_unique_id.startswith(self.entry.entry_id): suffix = self._attr_unique_id.split('_', 1)[1]; return f"{DOMAIN}_{suffix}"
         return None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        # ... (remains the same) ...
        await super().async_added_to_hass(); _LOGGER.debug("Climate entity %s added to HASS.", self.entity_id or self.unique_id)

    # --- UPDATED: _handle_coordinator_update uses new HVACAction logic ---
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        current_availability = self._attr_available
        current_mode = self._attr_hvac_mode
        current_action = self._attr_hvac_action
        current_target = self._attr_target_temperature
        current_temp = self._attr_current_temperature
        current_extra_attrs = self._attr_extra_state_attributes

        new_mode = current_mode
        new_action = current_action
        new_target: float | None = current_target
        new_temp: float | None = current_temp
        new_extra_attrs = current_extra_attrs.copy()
        new_availability = True

        # Data structure is now direct response from RawData
        if not self.coordinator.last_update_success or not self.coordinator.data or 'Values' not in self.coordinator.data.get("Data", {}):
             new_availability = False
             _LOGGER.debug("[Climate Update] Coordinator update failed or data missing 'Data.Values', marking unavailable.")
        else:
            data_dict = self.coordinator.data.get("Data", {}) # Get the inner Data dict
            values_list = data_dict.get("Values", []) # Get the Values list
            timestamp = data_dict.get("LogDateTimeUtc") # Get timestamp

            _LOGGER.debug("[Climate Update] Processing RawData Values list (%d items)", len(values_list))

            try:
                # Find needed values using helper
                indoor_temp_str = find_value_from_raw_data(values_list, CLEAR_TEXT_NAMES["INDOOR_TEMP"])
                target_temp_str = find_value_from_raw_data(values_list, CLEAR_TEXT_NAMES["TARGET_INDOOR_TEMP"])
                compressor_active_str = find_value_from_raw_data(values_list, CLEAR_TEXT_NAMES["COMPRESSOR_ACTIVE"])
                heating_valve_str = find_value_from_raw_data(values_list, CLEAR_TEXT_NAMES["EXCHANGE_VALVE_HEATING"])
                hw_valve_str = find_value_from_raw_data(values_list, CLEAR_TEXT_NAMES["EXCHANGE_VALVE_HW"])

                # Parse Temperatures Safely (remains same logic)
                try:
                    if indoor_temp_str is not None: new_temp = float(indoor_temp_str)
                    else: _LOGGER.debug("[Climate Update] Indoor temp value not found."); new_availability = False
                except (ValueError, TypeError): _LOGGER.warning("[Climate Update] Could not parse IndoorTemperature: '%s'", indoor_temp_str); new_availability = False

                target_temp_api: Optional[float] = None
                try:
                    if target_temp_str is not None:
                        target_temp_api = float(target_temp_str); new_target = max(self.min_temp, min(self.max_temp, target_temp_api))
                    else: _LOGGER.warning("[Climate Update] Target indoor temp value not found."); new_availability = False
                except (ValueError, TypeError): _LOGGER.warning("[Climate Update] Could not parse SetIndoorTemp: '%s'", target_temp_str); new_availability = False

                # Determine Mode & Action (only if available and target parsed)
                if new_availability and target_temp_api is not None:
                    # Determine Mode based on target temp
                    if target_temp_api <= TEMP_VALUE_FOR_OFF: new_mode = HVACMode.OFF
                    elif HVACMode.HEAT in self._attr_hvac_modes: new_mode = HVACMode.HEAT
                    else: new_mode = None; _LOGGER.error("[Climate Update] Could not determine HVAC mode!")

                    # Determine Action based on new logic
                    if new_mode == HVACMode.OFF:
                        new_action = HVACAction.OFF
                    elif compressor_active_str == "1":
                        if heating_valve_str == "1":
                            new_action = HVACAction.HEATING
                        elif hw_valve_str == "1":
                            _LOGGER.debug("Compressor active and HW valve on -> Action: IDLE (Hot Water)")
                            new_action = HVACAction.IDLE # Making hot water, climate is idle
                        else:
                            _LOGGER.debug("Compressor active but no specific valve -> Action: IDLE (Other)")
                            new_action = HVACAction.IDLE # Some other compressor activity
                    else: # Compressor is off ("0" or None)
                         new_action = HVACAction.IDLE # If mode is HEAT but compressor off

                else: # Reset mode/action if unavailable
                     new_mode = None; new_action = None

                # Update extra attributes
                new_extra_attrs["raw_compressor_active"] = compressor_active_str
                new_extra_attrs["raw_heating_valve"] = heating_valve_str
                new_extra_attrs["raw_hw_valve"] = hw_valve_str
                # ... (add back other attributes as needed, using find_value_from_raw_data) ...
                new_extra_attrs["outdoor_temp"] = find_value_from_raw_data(values_list, CLEAR_TEXT_NAMES["OUTDOOR_TEMP"])
                new_extra_attrs["hot_water_temp"] = find_value_from_raw_data(values_list, CLEAR_TEXT_NAMES["HOT_WATER_TEMP"])
                new_extra_attrs["last_api_update"] = timestamp

            except Exception as e:
                _LOGGER.exception("[Climate Update] Unexpected error processing RawData update: %s", e)
                new_availability = False

        # --- Final State Assignment & Write Check ---
        # ... (logic remains same as previous version) ...
        write_state = False
        if current_availability != new_availability: write_state = True; _LOGGER.info("Climate '%s' availability changed to %s", self.entity_id or self.unique_id, new_availability)
        if new_availability:
             if (new_mode != current_mode or new_action != current_action or new_target != current_target or new_temp != current_temp or new_extra_attrs != current_extra_attrs): write_state = True
             self._attr_hvac_mode = new_mode; self._attr_hvac_action = new_action; self._attr_target_temperature = new_target; self._attr_current_temperature = new_temp
             self._attr_extra_state_attributes = new_extra_attrs; self._attr_available = True
        else:
            if (current_availability != new_availability or self._attr_hvac_mode is not None or self._attr_hvac_action is not None or self._attr_target_temperature is not None or self._attr_current_temperature is not None or self._attr_extra_state_attributes): write_state = True
            self._attr_hvac_mode = None; self._attr_hvac_action = None; self._attr_target_temperature = None; self._attr_current_temperature = None; self._attr_extra_state_attributes = {}; self._attr_available = False
        if write_state and self.hass: _LOGGER.debug("[Climate Update] Writing state: Mode=%s, Action=%s, Temp=%s, Target=%s, Avail=%s", self._attr_hvac_mode, self._attr_hvac_action, self._attr_current_temperature, self._attr_target_temperature, self._attr_available); self.async_write_ha_state()
        elif not write_state: _LOGGER.debug("[Climate Update] No significant state change detected, skipping write.")

    async def _delayed_refresh(self, now) -> None:
        """Request coordinator refresh after a delay."""
        # ... (method remains the same) ...
        if self.coordinator and self.hass: _LOGGER.debug("Executing delayed coordinator refresh for %s triggered at %s", self.name or self.entity_id, now); await self.coordinator.async_request_refresh()
        else: _LOGGER.warning("Coordinator or HASS not available for %s delayed refresh.", self.name or self.entity_id)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Enable (HEAT) or Disable (OFF) heating by setting target temperature."""
        # ... (method remains the same - uses SetIndoorTemp, schedules delayed refresh) ...
        if hvac_mode not in self._attr_hvac_modes: _LOGGER.warning("Attempted to set unsupported HVAC mode: %s", hvac_mode); return
        property_name_for_temp = "SetIndoorTemp"; target_temp_value = None; target_mode_for_log = ""
        if hvac_mode == HVACMode.OFF: target_temp_value = TEMP_VALUE_FOR_OFF; target_mode_for_log = "OFF"; _LOGGER.info("Setting HVAC mode to OFF by setting %s to %.1f", property_name_for_temp, target_temp_value)
        elif hvac_mode == HVACMode.HEAT: target_mode_for_log = "HEAT"; current_target = self._attr_target_temperature or TEMP_VALUE_FOR_OFF; _LOGGER.info("Setting HVAC mode to HEAT (enabling automatic heating). Current target temperature (%.1f) will remain. Adjust manually if needed.", current_target); self._attr_hvac_mode = HVACMode.HEAT; self.async_write_ha_state(); _LOGGER.debug("Scheduling coordinator refresh in %ss after setting mode to HEAT...", DELAY_REFRESH_AFTER_SET); async_call_later(self.hass, DELAY_REFRESH_AFTER_SET, self._delayed_refresh); return
        else: _LOGGER.error("Cannot set unknown HVAC mode '%s'", hvac_mode); return
        if target_temp_value is not None:
            try:
                success = await self._client.async_set_property(property_name_for_temp, target_temp_value)
                if success: _LOGGER.info("Successfully requested mode change to %s via temperature set.", target_mode_for_log); self._attr_hvac_mode = hvac_mode; self._attr_target_temperature = target_temp_value; self.async_write_ha_state(); _LOGGER.debug("Scheduling coordinator refresh in %ss after setting mode to OFF...", DELAY_REFRESH_AFTER_SET); async_call_later(self.hass, DELAY_REFRESH_AFTER_SET, self._delayed_refresh)
                else: _LOGGER.error("Failed to set HVAC mode to %s via API", target_mode_for_log)
            except (ComfortzoneApiCommandError, ComfortzoneApiClientError) as e: _LOGGER.error("API error setting HVAC mode to %s: %s", target_mode_for_log, e)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        # ... (method remains the same - uses SetIndoorTemp, schedules delayed refresh) ...
        temperature = kwargs.get(ATTR_TEMPERATURE);
        if temperature is None: return
        try:
            target_temp = float(temperature); clamped_temp = max(self.min_temp, min(self.max_temp, target_temp))
            _LOGGER.info("Attempting to set target temperature to: %.1f (Input: %.1f)", clamped_temp, target_temp)
            property_name_for_temp = "SetIndoorTemp"; new_mode = HVACMode.OFF if clamped_temp <= TEMP_VALUE_FOR_OFF else HVACMode.HEAT
            if self._attr_hvac_mode != new_mode: _LOGGER.info("Setting temperature implies mode change to %s.", new_mode.name)
            success = await self._client.async_set_property(property_name_for_temp, clamped_temp)
            if success: _LOGGER.info("Successfully requested target temperature change to %.1f", clamped_temp); self._attr_target_temperature = clamped_temp; self._attr_hvac_mode = new_mode; self.async_write_ha_state(); _LOGGER.debug("Scheduling coordinator refresh in %ss after setting temperature...", DELAY_REFRESH_AFTER_SET); async_call_later(self.hass, DELAY_REFRESH_AFTER_SET, self._delayed_refresh)
            else: _LOGGER.error("Failed to set target temperature via API")
        except (ComfortzoneApiCommandError, ComfortzoneApiClientError) as e: _LOGGER.error("API error setting target temperature to %.1f: %s", clamped_temp, e)
        except ValueError: _LOGGER.error("Invalid temperature value provided: %s", temperature)
