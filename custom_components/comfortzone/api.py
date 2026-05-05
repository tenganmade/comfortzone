"""API Client for Comfortzone Heat Pump."""
import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp
import async_timeout

# Use single reading endpoint defined in const
from .const import API_ENDPOINT, API_ENDPOINT_SET

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30 # Timeout for commands (kept at 30s)
DEFAULT_POLL_TIMEOUT = 20 # Timeout for status polling
DEFAULT_HEADERS = {"Content-Type": "application/json"}

# Helper Function (remains the same)
def find_value_from_raw_data(
    values_list: Optional[List[Dict[str, Any]]],
    identifier: str,
    key_to_match: str = "ClearTextName"
) -> Optional[str]:
    """Finds the 'Value' string from the RawData list based on matching another key."""
    if not values_list: return None
    for item in values_list:
        if isinstance(item, dict) and item.get(key_to_match) == identifier:
            return item.get("Value")
    _LOGGER.debug("Identifier '%s' not found in raw data list using key '%s'", identifier, key_to_match)
    return None

# Exception classes remain the same
class ComfortzoneApiClientError(Exception): pass
class ComfortzoneApiCommunicationError(ComfortzoneApiClientError): pass
class ComfortzoneApiAuthError(ComfortzoneApiClientError): pass
class ComfortzoneApiCommandError(ComfortzoneApiClientError): pass

class ComfortzoneApiClient:
    """API Client to interact with the Loggamera platform for Comfortzone."""

    def __init__( self, api_key: str, device_id: int, session: aiohttp.ClientSession,) -> None:
        """Initialize the API client."""
        self._api_key = api_key; self._device_id = device_id; self._session = session
        self._write_lock = asyncio.Lock()
        self._last_write_time = 0.0

    # --- UPDATED async_get_data with HTML check ---
    async def async_get_data(self) -> Dict[str, Any]:
        """Fetch data from the RawData endpoint."""
        payload = {"ApiKey": self._api_key, "DeviceId": self._device_id}
        url = API_ENDPOINT
        _LOGGER.debug("[GetData] Requesting data from %s", url)
        try:
            async with async_timeout.timeout(DEFAULT_POLL_TIMEOUT):
                response = await self._session.post( url, headers=DEFAULT_HEADERS, json=payload,)

            _LOGGER.debug("[GetData] API Response Status: %s, Content-Type: %s", response.status, response.content_type)
            response_text = await response.text(); # Get text early for logging

            # Check HTTP status first
            if not (200 <= response.status < 300):
                _LOGGER.warning("[GetData] API request failed with HTTP status %s. Response: %s", response.status, response_text[:500]) # Log beginning of response
                response.raise_for_status() # Let HA handle ClientResponseError

            if response.content_type == 'text/html':
                # --- NEW: Check for "Busy" response within HTML ---
                if '"Result":"busy"' in response_text:
                    _LOGGER.warning("[GetData] API returned 'Busy' status (potentially wrapped in HTML). Skipping update.")
                    return None # Indicate non-critical failure, keep old data
                # --- End New Check ---
                else: # Other HTML content
                    _LOGGER.warning("[GetData] API returned HTML instead of JSON (API maintenance or error page?). Response text (first 500 chars): %s", response_text[:500])
                    raise ComfortzoneApiCommunicationError("API returned HTML instead of JSON (likely maintenance).")

            # Try parsing JSON (allow any type now for robustness, but check HTML first)
            try:
                json_data = await response.json(content_type=None);
                _LOGGER.debug("[GetData] API Response JSON: %s", json_data)
            except (aiohttp.ContentTypeError, ValueError) as json_err: # Catch JSON specific parse errors
                 _LOGGER.error("[GetData] Failed to decode JSON response. Status: %s, Content-Type: %s, Response: %s", response.status, response.content_type, response_text[:500])
                 raise ComfortzoneApiCommunicationError(f"Failed to decode API JSON response: {json_err}") from json_err

            # Check for API-level error in JSON response
            if isinstance(json_data, dict) and json_data.get("Error"):
                 error_msg = json_data["Error"]
                 if "authentication" in error_msg.lower(): raise ComfortzoneApiAuthError(f"Authentication failed: {error_msg}")
                 raise ComfortzoneApiCommunicationError(f"API returned an error message: {error_msg}")

            # Check expected data structure
            if not isinstance(json_data.get("Data"), dict) or not isinstance(json_data["Data"].get("Values"), list):
                 raise ComfortzoneApiCommunicationError(f"Unexpected JSON format: Missing Data.Values list. Response: {response_text}")

            # Success
            return json_data

        except asyncio.TimeoutError as e:
            _LOGGER.warning("[GetData] Timeout error fetching data: %s", e) # Warning level might be better for transient timeouts
            raise ComfortzoneApiCommunicationError("Timeout contacting API for status") from e
        except (aiohttp.ClientError, aiohttp.ClientResponseError) as e:
            _LOGGER.warning("[GetData] Communication error fetching data: %s", e) # Warning level better for transient network issues
            raise ComfortzoneApiCommunicationError(f"Error communicating with API for status: {e}") from e
        except ComfortzoneApiAuthError:
            raise # Re-raise critical auth errors
        except ComfortzoneApiCommunicationError:
            raise # Re-raise our specific identified errors
        except Exception as e:
            _LOGGER.exception("[GetData] Unexpected error processing data fetch: %s", e) # Use exception for full traceback
            raise ComfortzoneApiClientError(f"An unexpected error occurred fetching status: {e}") from e

    # --- MODIFIED: async_set_property with Queuing and Broader Retry Logic ---
    async def async_set_property(self, property_name: str, value: Any) -> bool:
        """Send command, retry ONCE after 60s delay on timeout, comms error, or 5xx error. Queued to prevent API overload."""
        import time
        async with self._write_lock:
            now = time.time()
            elapsed = now - self._last_write_time
            if elapsed < 5.0:
                _LOGGER.debug("Queuing API write for '%s'. Waiting %.1fs...", property_name, 5.0 - elapsed)
                await asyncio.sleep(5.0 - elapsed)
            
            payload = { "ApiKey": self._api_key, "DeviceId": self._device_id, "PropertyName": property_name, "Value": value }
            timeout_value = DEFAULT_TIMEOUT # Use defined timeout (e.g., 30s)
            retry_delay = 60 # Seconds to wait before retrying
            max_attempts = 2
            attempt = 1

            try:
                while attempt <= max_attempts:
                    log_prefix = f"[SetProperty Attempt {attempt}/{max_attempts}]"
                    _LOGGER.debug("%s Sending request to set '%s' to '%s'", log_prefix, property_name, value)
                    if attempt == 1:
                        _LOGGER.debug("%s API Request Payload: %s", log_prefix, payload)

                    response = None
                    should_retry = False

                    try:
                        async with async_timeout.timeout(timeout_value):
                            response = await self._session.post( API_ENDPOINT_SET, headers=DEFAULT_HEADERS, json=payload)

                        _LOGGER.debug("%s API Response Status: %s", log_prefix, response.status)
                        response_text = await response.text(); _LOGGER.debug("%s API Response Text: %s", log_prefix, response_text)

                        # --- Check HTTP Status Code ---
                        if 200 <= response.status < 300:
                            # --- Success Case (2xx) ---
                            try: # Try parsing JSON and checking internal result/error
                                json_response = await response.json(); _LOGGER.debug("%s API Response JSON: %s", log_prefix, json_response)
                                if isinstance(json_response, dict) and json_response.get("Error"):
                                     error_msg = json_response["Error"]; _LOGGER.error("%s Failed: API returned top-level error: %s", log_prefix, error_msg); return False # No retry on explicit API error
                                data_dict = json_response.get("Data")
                                if isinstance(data_dict, dict):
                                    result = data_dict.get("Result")
                                    if result is False: _LOGGER.error("%s Failed: API returned Data.Result = false.", log_prefix); return False # No retry on explicit Result:false
                                    elif result is True: _LOGGER.info("%s Succeeded for '%s' (API returned Data.Result: true)", log_prefix, property_name); return True
                                # If no explicit failure, assume success on 2xx
                                _LOGGER.info("%s Set '%s' (API OK, Result/Data missing/not bool, assuming success)", log_prefix, property_name); return True
                            except (aiohttp.ContentTypeError, ValueError): # Includes JSONDecodeError
                                # Treat non-JSON 2xx response as success
                                _LOGGER.info("%s Succeeded for '%s' (API returned 2xx status, non-JSON/empty response, assuming OK)", log_prefix, property_name); return True
                            # If we reach here after try/except for JSON, it implies success

                        elif 400 <= response.status < 500:
                             # --- Client Error (4xx) ---
                             _LOGGER.error("%s Failed: API returned client error HTTP %s. Check PropertyName/Value.", log_prefix, response.status)
                             return False # DO NOT RETRY client errors

                        elif 500 <= response.status < 600:
                             # --- Server Error (5xx) ---
                             _LOGGER.warning("%s Failed: API returned server error HTTP %s.", log_prefix, response.status)
                             should_retry = True # Retry server errors
                        else:
                             # --- Other unexpected status ---
                             _LOGGER.error("%s Failed: API returned unexpected HTTP %s.", log_prefix, response.status)
                             return False # Do not retry unknown statuses


                    except asyncio.TimeoutError:
                        _LOGGER.warning("%s Timeout error (after %ss) setting property '%s'.", log_prefix, timeout_value, property_name)
                        should_retry = True # Retry timeouts

                    except aiohttp.ClientError as exception: # Includes ClientConnectorError, ServerDisconnectedError etc.
                        _LOGGER.warning("%s Communication error setting property '%s': %s", log_prefix, property_name, exception)
                        should_retry = True # Retry communication errors

                    except Exception as exception: # Catch other unexpected errors during processing
                        _LOGGER.exception("%s Unexpected error setting property '%s': %s", log_prefix, property_name, exception)
                        return False # Fail on other errors, no retry


                    # --- Handle Retry Logic ---
                    if should_retry and attempt < max_attempts:
                         _LOGGER.info("Waiting %ss before retry...", retry_delay)
                         await asyncio.sleep(retry_delay)
                         attempt += 1 # Increment attempt counter and loop again
                         # Continue to next iteration of the while loop
                    elif should_retry and attempt >= max_attempts:
                         _LOGGER.error("%s Failed on final attempt after %s error. Giving up.", log_prefix, "Timeout/Comms/Server")
                         return False # Final attempt failed
                    elif not should_retry:
                         # This path is taken if a non-retryable error occurred (4xx, Result:false, explicit Error)
                         # Or if the request was successful (2xx) - which already returned True above.
                         # If somehow we get here without returning True/False, default to False.
                         _LOGGER.debug("%s Exiting retry loop without success.", log_prefix)
                         return False

                # If loop finishes without returning (e.g., max_attempts <= 0), return False
                return False
            finally:
                self._last_write_time = time.time()
    # --- End MODIFIED async_set_property ---
