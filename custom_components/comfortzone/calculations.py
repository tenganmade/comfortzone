"""Pure calculation helpers for the Comfortzone integration.

This module is intentionally free of Home Assistant imports so the helpers
can be unit-tested in isolation. Everything here operates on the raw list
of value dictionaries that the Loggamera RawData endpoint returns:

    [
        {"ClearTextName": "Indoor temp (TE3)", "Value": "21.7", ...},
        {"ClearTextName": "Compressor active", "Value": "1", ...},
        ...
    ]

Functions in this module never raise on missing or malformed data — they
return ``None`` (for numbers) or ``False`` (for booleans) and let the
caller decide whether to mark an entity as unavailable.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from .const import (
    CIRCULATION_PUMP_MAX_W,
    CLEAR_TEXT_NAMES,
    DEFAULT_GENERIC_FACTOR,
    FAN_MAX_W,
    MODEL_COP_CURVES,
)

DEFAULT_MODEL = "RX95"


# --- RawData primitives ----------------------------------------------------


def find_value_from_raw_data(
    values_list: Optional[Iterable[Any]],
    identifier: str,
    key_to_match: str = "ClearTextName",
) -> Optional[str]:
    """Return the ``Value`` string for the entry matching ``identifier``."""
    if not values_list:
        return None
    for item in values_list:
        if isinstance(item, dict) and item.get(key_to_match) == identifier:
            return item.get("Value")
    return None


def read_float(values_list: Optional[Iterable[Any]], clear_text_name: str) -> Optional[float]:
    """Read a numeric value from RawData.Values, ``None`` if missing/invalid."""
    raw = find_value_from_raw_data(values_list, clear_text_name)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# --- Heat-pump electrical estimation --------------------------------------


def compressor_factor_from_flow(
    flow_temp_c: Optional[float], model: str = DEFAULT_MODEL
) -> float:
    """Interpolate the thermal-to-electrical factor for a specific model.

    Each model's curve is defined in ``const.MODEL_COP_CURVES`` and anchored
    at two EN255 spec points from the manufacturer's datasheet. The factor
    is linearly interpolated between the anchors and clamped outside the
    measured range so values stay in physically reasonable territory.

    For models without a known spec curve (currently anything other than
    RX95, including the ``Other`` selection) the function returns a
    generic fallback factor — the user can refine this with an explicit
    override factor via the options flow.
    """
    curve = MODEL_COP_CURVES.get(model)
    if curve is None:
        return DEFAULT_GENERIC_FACTOR
    if flow_temp_c is None:
        return curve["factor_high"]
    if flow_temp_c <= curve["flow_low_c"]:
        return curve["factor_low"]
    if flow_temp_c >= curve["flow_high_c"]:
        return curve["factor_high"]
    span = curve["flow_high_c"] - curve["flow_low_c"]
    pos = (flow_temp_c - curve["flow_low_c"]) / span
    return curve["factor_low"] + pos * (curve["factor_high"] - curve["factor_low"])


def compute_compressor_electrical_w(
    values: Optional[Iterable[Any]],
    override_factor: float,
    model: str = DEFAULT_MODEL,
) -> Optional[float]:
    """Estimate compressor electrical input in W from reported thermal output.

    A non-zero ``override_factor`` bypasses the model's spec curve and uses
    that constant factor — useful when the user has empirical measurements
    or wants to be conservative (e.g. 0.4 for a hand-tuned safety margin).
    """
    thermal = read_float(values, CLEAR_TEXT_NAMES["COMPRESSOR_POWER"])
    if thermal is None:
        return None
    if override_factor and override_factor > 0:
        return thermal * override_factor
    flow_c = read_float(values, CLEAR_TEXT_NAMES["FLOW_TEMP"])
    return thermal * compressor_factor_from_flow(flow_c, model)


def compute_circulation_pump_w(values: Optional[Iterable[Any]]) -> float:
    """Estimate circulation pump electrical draw in W from reported speed (%)."""
    pct = read_float(values, CLEAR_TEXT_NAMES["CIRC_PUMP_SPEED"]) or 0.0
    return (pct / 100.0) * CIRCULATION_PUMP_MAX_W


def compute_fan_w(values: Optional[Iterable[Any]]) -> float:
    """Estimate fan electrical draw in W from reported speed (%)."""
    pct = read_float(values, CLEAR_TEXT_NAMES["FAN_SPEED_CURRENT"]) or 0.0
    return (pct / 100.0) * FAN_MAX_W


def compute_addition_w(values: Optional[Iterable[Any]]) -> float:
    """Read the resistive addition heater power in W (already electrical)."""
    return read_float(values, CLEAR_TEXT_NAMES["ADDITION_POWER"]) or 0.0


# --- Operating-mode predicates --------------------------------------------


def is_truthy(value: Optional[str]) -> bool:
    """Liberal truthiness check for API string values.

    The Loggamera API normally reports booleans as ``"0"`` / ``"1"`` but it
    has been observed to occasionally return ``"1.0"``, ``"0.0"`` or even
    free-form strings. This helper accepts any of those forms by coercing
    to ``float`` first and falling back to common keyword strings.
    """
    if value is None:
        return False
    try:
        return float(value) != 0.0
    except (TypeError, ValueError):
        return str(value).strip().lower() in ("true", "yes", "on")


def compressor_active(values: Optional[Iterable[Any]]) -> bool:
    """True when the heat pump's compressor is reported as running."""
    return is_truthy(find_value_from_raw_data(values, CLEAR_TEXT_NAMES["COMPRESSOR_ACTIVE"]))


def heating_valve_open(values: Optional[Iterable[Any]]) -> bool:
    """True when the exchange valve is routed to space heating."""
    return is_truthy(
        find_value_from_raw_data(values, CLEAR_TEXT_NAMES["EXCHANGE_VALVE_HEATING"])
    )


def hw_valve_open(values: Optional[Iterable[Any]]) -> bool:
    """True when the exchange valve is routed to hot water production."""
    return is_truthy(
        find_value_from_raw_data(values, CLEAR_TEXT_NAMES["EXCHANGE_VALVE_HW"])
    )


def is_heating(values: Optional[Iterable[Any]]) -> bool:
    """True when the pump is dedicated to space heating right now."""
    return compressor_active(values) and heating_valve_open(values)


def is_hot_water(values: Optional[Iterable[Any]]) -> bool:
    """True when the pump is dedicated to hot water production right now."""
    return compressor_active(values) and hw_valve_open(values)


def is_defrosting(values: Optional[Iterable[Any]]) -> bool:
    """Heuristic: compressor running but neither valve open ⇒ defrost cycle."""
    return (
        compressor_active(values)
        and not heating_valve_open(values)
        and not hw_valve_open(values)
    )
