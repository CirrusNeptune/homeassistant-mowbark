"""The Flux LED/MagicLight integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, Final

from .mow_sconce import MowSconce, MowSconceDiscovery, ATTR_ID, ATTR_IPADDR

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    config_validation as cv,
)
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.event import (
    async_track_time_interval,
)
from homeassistant.helpers.typing import ConfigType

from .const import (
    DISCOVER_SCAN_TIMEOUT,
    DOMAIN,
    MOW_SCONCE_DISCOVERY,
    MOW_SCONCE_DISCOVERY_SIGNAL,
    SIGNAL_STATE_UPDATED,
)
from .discovery import (
    async_build_cached_discovery,
    async_clear_discovery_cache,
    async_discover_device,
    async_discover_devices,
    async_get_discovery,
    async_trigger_discovery,
    async_update_entry_from_discovery,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [
    Platform.LIGHT,
    Platform.NUMBER,
]
DISCOVERY_INTERVAL: Final = timedelta(minutes=15)
REQUEST_REFRESH_DELAY: Final = 1.5

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@callback
def async_mow_sconce_for_host(
    host: str, discovery: MowSconceDiscovery | None
) -> MowSconce:
    """Create a MowSconce from a host."""
    return MowSconce(host, discovery=discovery)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the mow_sconce component."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[MOW_SCONCE_DISCOVERY] = []

    @callback
    def _async_start_background_discovery(*_: Any) -> None:
        """Run discovery in the background."""
        hass.async_create_background_task(
            _async_discovery(), "mow_sconce-discovery", eager_start=True
        )

    async def _async_discovery(*_: Any) -> None:
        async_trigger_discovery(
            hass, await async_discover_devices(hass, DISCOVER_SCAN_TIMEOUT)
        )

    _async_start_background_discovery()
    async_track_time_interval(
        hass,
        _async_start_background_discovery,
        DISCOVERY_INTERVAL,
        cancel_on_shutdown=True,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up mow_sconce from a config entry."""
    host = entry.data[CONF_HOST]
    discovery_cached = True
    if discovery := async_get_discovery(hass, host):
        discovery_cached = False
    else:
        discovery = async_build_cached_discovery(entry)
    device: MowSconce = async_mow_sconce_for_host(host, discovery=discovery)
    signal = SIGNAL_STATE_UPDATED.format(device.ipaddr)
    device.discovery = discovery

    @callback
    def _async_state_changed(*_: Any) -> None:
        _LOGGER.debug("%s: Device state updated:", device.ipaddr)
        async_dispatcher_send(hass, signal)

    await device.async_setup(_async_state_changed)

    # UDP probe after successful connect only
    if discovery_cached:
        if directed_discovery := await async_discover_device(hass, host):
            device.discovery = discovery = directed_discovery
            discovery_cached = False

    if not discovery_cached:
        # Only update the entry once we have verified the unique id
        # is either missing or we have verified it matches
        async_update_entry_from_discovery(
            hass, entry, discovery
        )

    hass.data[DOMAIN][entry.entry_id] = device
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_handle_discovered_device() -> None:
        """Handle device discovery."""
        pass

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            MOW_SCONCE_DISCOVERY_SIGNAL.format(entry_id=entry.entry_id),
            _async_handle_discovered_device,
        )
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    device: MowSconce = hass.data[DOMAIN][entry.entry_id]
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Make sure we probe the device again in case something has changed externally
        async_clear_discovery_cache(hass, entry.data[CONF_HOST])
        del hass.data[DOMAIN][entry.entry_id]
        await device.async_stop()
    return unload_ok
