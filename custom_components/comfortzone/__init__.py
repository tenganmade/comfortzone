"""The Comfortzone Heat Pump integration."""
import logging
import asyncio
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ComfortzoneApiClient, ComfortzoneApiClientError, ComfortzoneApiAuthError, ComfortzoneApiCommunicationError
from .const import DOMAIN, CONF_DEVICE_ID

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=1)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Comfortzone Heat Pump from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    api_client = ComfortzoneApiClient(
        api_key=entry.data[CONF_API_KEY],
        device_id=entry.data[CONF_DEVICE_ID],
        session=session,
    )

    async def async_update_data():
        """Fetch data from API endpoint."""
        try:
            data = await api_client.async_get_data()
            if data is None:
                _LOGGER.info("API reported busy, using previous data.")
                if coordinator.data:
                    return coordinator.data
                else:
                    _LOGGER.warning("API reported busy, but no previous data available.")
                    raise UpdateFailed("API reported busy, initial data fetch failed.")
            return data
        except ComfortzoneApiAuthError as err:
            _LOGGER.error("Authentication error during update: %s", err)
            raise ConfigEntryAuthFailed(f"API key or Device ID is invalid: {err}") from err
        except (ComfortzoneApiClientError, ComfortzoneApiCommunicationError) as err:
            _LOGGER.warning("API Client Error during update: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_coordinator_{entry.entry_id}",
        update_method=async_update_data,
        update_interval=UPDATE_INTERVAL,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "client": api_client,
        "coordinator": coordinator
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
