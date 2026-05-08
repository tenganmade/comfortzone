"""Constants for the Comfortzone Heat Pump integration."""

DOMAIN = "comfortzone"

API_ENDPOINT = "https://platform.loggamera.se/Api/v1/RawData"
API_ENDPOINT_SET = "https://platform.loggamera.se/Api/v1/SetProperty"

CONF_API_KEY = "api_key"
CONF_DEVICE_ID = "device_id"
CONF_MODEL = "model"

# Optional configuration for cost / energy sensors
CONF_PRICE_ENTITY = "price_entity"
CONF_PRICE_IN_ORE = "price_in_ore"
CONF_COMPRESSOR_ELECTRICAL_FACTOR = "compressor_electrical_factor"

# Tunable alarm thresholds (defaults match the values used in 2.5.x)
CONF_SHORT_CYCLE_THRESHOLD = "short_cycle_threshold"
CONF_ADDITION_POWER_THRESHOLD_W = "addition_power_threshold_w"
CONF_ADDITION_DURATION_THRESHOLD_S = "addition_duration_threshold_s"
CONF_FILTER_WARNING_DAYS = "filter_warning_days"
CONF_LOW_HW_THRESHOLD_C = "low_hw_threshold_c"
CONF_LOW_HW_HYSTERESIS_C = "low_hw_hysteresis_c"

DEFAULT_SHORT_CYCLE_THRESHOLD = 6
DEFAULT_ADDITION_POWER_THRESHOLD_W = 500
DEFAULT_ADDITION_DURATION_THRESHOLD_S = 600  # 10 minutes
DEFAULT_FILTER_WARNING_DAYS = 7
DEFAULT_LOW_HW_THRESHOLD_C = 40.0
DEFAULT_LOW_HW_HYSTERESIS_C = 3.0

# Defaults for derived calculations.
# DEFAULT_COMPRESSOR_FACTOR is the override value used when the user disables
# the spec-based interpolation. 0 means "use the model's spec curve" (default).
# When non-zero it acts as a constant thermal-to-electrical conversion factor
# that bypasses the curve entirely.
DEFAULT_COMPRESSOR_FACTOR = 0.0

# Per-model thermal-to-electrical conversion curves. Each entry defines two
# anchor points (flow temperature → factor) taken from the manufacturer's
# EN255 datasheet. The factor is the inverse of the COP at that operating
# point: factor = electrical_input_kW / thermal_output_kW. Values between
# the anchor points are linearly interpolated; outside the range they are
# clamped to the nearest anchor.
#
# RX95 (Comfortzone exhaust-air heat pump):
#   20(12)/35°C: 3.4 kW thermal / 0.8 kW electrical -> factor 0.235 (COP 4.25)
#   20(12)/50°C: 3.5 kW thermal / 1.1 kW electrical -> factor 0.314 (COP 3.18)
MODEL_COP_CURVES: dict[str, dict[str, float]] = {
    "RX95": {
        "flow_low_c": 35.0,
        "factor_low": 0.235,
        "flow_high_c": 50.0,
        "factor_high": 0.314,
    },
}

# Fallback factor used for models that don't have a known spec curve
# (currently anything selected as "Other" in the config flow). Roughly
# matches a working COP of ~3.3 — conservative enough to over-estimate
# electrical input rather than under-estimate it. Users can replace this
# with a measured value via the compressor_electrical_factor option.
DEFAULT_GENERIC_FACTOR = 0.30
# Maximum nameplate ratings used to convert reported speeds (%) to watts.
CIRCULATION_PUMP_MAX_W = 75
FAN_MAX_W = 83
# Constant standby draw of the controller, fan PCB, sensors etc.
STANDBY_W = 15
# Minimum estimated electrical input (W) below which COP becomes too noisy
# to report meaningfully. Keeps the instant COP sensor sane near idle.
MIN_ELECTRICAL_FOR_COP_W = 100

# Target temp value used to signify "OFF" mode for the climate entity
TEMP_VALUE_FOR_OFF = 10.0

# Delay in seconds before the *first* coordinator refresh after a successful
# 'set' command. A shorter value gives the user near-instant feedback that the
# write actually took effect on the device. The OptimisticConfirmedMixin keeps
# the entity showing the user-written value until the API confirms it, so a
# short delay won't cause UI flicker even if the API hasn't propagated the
# change yet at the first poll.
DELAY_REFRESH_AFTER_SET = 5
# Schedule a follow-up refresh this many seconds after a write to catch
# slower API propagations.
DELAY_REFRESH_FOLLOWUP = 15

# ClearTextNames needed for parsing RawData
CLEAR_TEXT_NAMES = {
    # Climate / Core Temps
    "INDOOR_TEMP": "Indoor temp (TE3)",
    "OUTDOOR_TEMP": "Outdoor temp (TE0)",
    "TARGET_INDOOR_TEMP": "Indoor temp set temp",
    "HOT_WATER_TEMP": "Hot water temp (TE24)",
    "TARGET_HW_TEMP": "Hot water set temp",
    "FLOW_TEMP": "Flow line temp (TE1)",
    "RETURN_TEMP": "Return temp (TE2)",
    # Setpoints / Settings
    "HEATING_CURVE": "Heating curve",
    "HOLIDAY_DAYS": "Holiday time (days)",
    "HW_EXTRA_MODE": "Extra hot water mode",
    # States / Alarms / Valves
    "COMPRESSOR_ACTIVE": "Compressor active",
    "EXCHANGE_VALVE_HEATING": "Exchange valve heating (on/off)",
    "EXCHANGE_VALVE_HW": "Exchange valve hot water (on/off)",
    "FILTER_ALARM": "Filter alarm (on/off)",
    "ALARM_TEXT": "AlarmInClearText",
    "FAN_STATE": "Fan state",
    "ROOM_THERMOSTAT_SWITCH": "Room thermostat switch (IN7)",
    # Power / frequency / fan
    "EXHAUST_AIR_TEMP": "Exhaust air temp (TE7)",
    "COMPRESSOR_POWER": "Compressor effect",
    "ADDITION_POWER": "Addition effect",
    "COMPRESSOR_FREQ": "Compressor frequency",
    "HW_PRIORITY": "Hot water priority",
    "CIRC_PUMP_SPEED": "Circulation pump speed",
    "FAN_SPEED_CURRENT": "Fan speed (current)",
    "TOTAL_POWER": "Total output power",
    # Diagnostics / config readback
    "DEFROST_INTERVAL": "Defrost interval",
    "DEFROST_BLOCK_TIME": "Defroster block time",
    "COMPRESSOR_FREQ_MAX": "Compressor freq. max",
    "COOLING_INSTALLED": "Cooling installed",
    "COOLING_ENABLED": "Cooling enabled",
    "DUAL_HEATING_CURVES": "Dual heating curves",
    "HEATER_ELEMENT_ALLOWED": "Heater element allowed",
    # Refrigerant circuit diagnostics
    "HOT_GAS_TEMP": "Hot gas temp (TE4)",
    "CONDENSER_OUT_TEMP": "Condenser out (TE5)",
    "EVAPORATOR_IN_TEMP": "Evaporator in (TE6)",
    # Reduced fan schedule (read-only diagnostic)
    "REDUCED_FAN_WEEKDAYS": "Reduced fan Weekdays (on/off)",
    "REDUCED_FAN_WEEKDAYS_START_H": "Reduced fan Weekdays start hour",
    "REDUCED_FAN_WEEKDAYS_START_M": "Reduced fan Weekdays start minute",
    "REDUCED_FAN_WEEKDAYS_STOP_H": "Reduced fan Weekdays stop hour",
    "REDUCED_FAN_WEEKDAYS_STOP_M": "Reduced fan Weekdays stop minute",
    "REDUCED_FAN_WEEKENDS": "Reduced fan Weekends (on/off)",
    "REDUCED_FAN_WEEKENDS_START_H": "Reduced fan Weekends start hour",
    "REDUCED_FAN_WEEKENDS_START_M": "Reduced fan Weekends start minute",
    "REDUCED_FAN_WEEKENDS_STOP_H": "Reduced fan Weekends stop hour",
    "REDUCED_FAN_WEEKENDS_STOP_M": "Reduced fan Weekends stop minute",
}

# Maps binary_sensor suffix -> ClearTextName
BINARY_SENSOR_MAP = {
    "filter_alarm": CLEAR_TEXT_NAMES["FILTER_ALARM"],
    "main_alarm": CLEAR_TEXT_NAMES["ALARM_TEXT"],
    "compressor_active": CLEAR_TEXT_NAMES["COMPRESSOR_ACTIVE"],
    "room_thermostat": CLEAR_TEXT_NAMES["ROOM_THERMOSTAT_SWITCH"],
    "heating_valve": CLEAR_TEXT_NAMES["EXCHANGE_VALVE_HEATING"],
    "hot_water_valve": CLEAR_TEXT_NAMES["EXCHANGE_VALVE_HW"],
    "cooling_installed": CLEAR_TEXT_NAMES["COOLING_INSTALLED"],
    "cooling_enabled": CLEAR_TEXT_NAMES["COOLING_ENABLED"],
    "dual_heating_curves": CLEAR_TEXT_NAMES["DUAL_HEATING_CURVES"],
}
