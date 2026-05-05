"""Config flow for Comfortzone Heat Pump."""
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    ComfortzoneApiClient,
    ComfortzoneApiClientError,
    ComfortzoneApiAuthError,
    ComfortzoneApiCommunicationError,
)
from .const import DOMAIN, CONF_DEVICE_ID, CONF_MODEL

_LOGGER = logging.getLogger(__name__)

MODELS = ["RX95", "Other"]

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_DEVICE_ID): int,
        vol.Required(CONF_MODEL, default="RX95"): vol.In(MODELS),
    }
)

class ComfortzoneConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Comfortzone Heat Pump."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id_str = str(user_input[CONF_DEVICE_ID])
            await self.async_set_unique_id(device_id_str)
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            api_client = ComfortzoneApiClient(
                api_key=user_input[CONF_API_KEY],
                device_id=user_input[CONF_DEVICE_ID],
                session=session,
            )

            try:
                _LOGGER.debug("Attempting to validate API credentials...")
                await api_client.async_get_data()
                _LOGGER.debug("API credentials validated successfully.")
            except ComfortzoneApiAuthError as e:
                _LOGGER.warning("Authentication failed: %s", e)
                errors["base"] = "invalid_auth"
            except ComfortzoneApiCommunicationError as e:
                _LOGGER.error("Communication error during validation: %s", e)
                errors["base"] = "cannot_connect"
            except ComfortzoneApiClientError as e:
                _LOGGER.error("Unknown API client error during validation: %s", e)
                errors["base"] = "unknown"
            except Exception as e:
                _LOGGER.exception("Unexpected error during validation: %s", e)
                errors["base"] = "unknown"

            if not errors:
                return self.async_create_entry(
                    title=f"Comfortzone Heat Pump ({device_id_str})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Manage the options."""
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry, data={**self.config_entry.data, **user_input}
            )
            return self.async_create_entry(title="", data={})

        current_model = self.config_entry.data.get(CONF_MODEL, "RX95")
        options_schema = vol.Schema(
            {
                vol.Required(CONF_MODEL, default=current_model): vol.In(MODELS),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )
