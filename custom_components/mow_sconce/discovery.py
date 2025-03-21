"""The Flux LED/MagicLight integration discovery."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import logging
from typing import Any, Final

from .mow_sconce import MowSconceDiscovery, MowSconceScanner, ATTR_ID, ATTR_IPADDR

from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, discovery_flow
from homeassistant.util.async_ import create_eager_task
from homeassistant.util.network import is_ip_address

from .const import (
    DIRECTED_DISCOVERY_TIMEOUT,
    DOMAIN,
    MOW_SCONCE_DISCOVERY,
)

_LOGGER = logging.getLogger(__name__)


CONF_TO_DISCOVERY: Final = {
    CONF_HOST: ATTR_IPADDR,
}


@callback
def async_build_cached_discovery(entry: ConfigEntry) -> MowSconceDiscovery:
    """When discovery is unavailable, load it from the config entry."""
    data = entry.data
    return MowSconceDiscovery(
        ipaddr=data[CONF_HOST],
        id=entry.unique_id,
    )


@callback
def async_name_from_discovery(
    device: MowSconceDiscovery
) -> str:
    """Convert a mow_sconce discovery to a human readable name."""
    if (mac_address := device[ATTR_ID]) is None:
        return device[ATTR_IPADDR]
    short_mac = mac_address[-6:]
    return f"Mow Sconce {short_mac}"


@callback
def async_populate_data_from_discovery(
    current_data: Mapping[str, Any],
    data_updates: dict[str, Any],
    device: MowSconceDiscovery,
) -> None:
    """Copy discovery data into config entry data."""
    for conf_key, discovery_key in CONF_TO_DISCOVERY.items():
        if (
            device.get(discovery_key) is not None
            and conf_key
            not in data_updates  # Prefer the model num from TCP instead of UDP
            and current_data.get(conf_key) != device[discovery_key]  # type: ignore[literal-required]
        ):
            data_updates[conf_key] = device[discovery_key]  # type: ignore[literal-required]


@callback
def async_update_entry_from_discovery(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    device: MowSconceDiscovery,
) -> bool:
    """Update a config entry from a mow_sconce discovery."""
    data_updates: dict[str, Any] = {}
    mac_address = device[ATTR_ID]
    assert mac_address is not None
    updates: dict[str, Any] = {}
    formatted_mac = dr.format_mac(mac_address)
    if not entry.unique_id:
        updates["unique_id"] = formatted_mac
    async_populate_data_from_discovery(entry.data, data_updates, device)
    if is_ip_address(entry.title):
        updates["title"] = async_name_from_discovery(device)
    title_matches_name = entry.title == entry.data.get(CONF_NAME)
    if data_updates or title_matches_name:
        updates["data"] = {**entry.data, **data_updates}
        if title_matches_name:
            del updates["data"][CONF_NAME]
    # If the title has changed and the config entry is loaded, a listener is
    # in place, and we should not reload
    if updates and not ("title" in updates and entry.state is ConfigEntryState.LOADED):
        return hass.config_entries.async_update_entry(entry, **updates)
    return False


@callback
def async_get_discovery(hass: HomeAssistant, host: str) -> MowSconceDiscovery | None:
    """Check if a device was already discovered via a broadcast discovery."""
    discoveries: list[MowSconceDiscovery] = hass.data[DOMAIN][MOW_SCONCE_DISCOVERY]
    for discovery in discoveries:
        if discovery[ATTR_IPADDR] == host:
            return discovery
    return None


@callback
def async_clear_discovery_cache(hass: HomeAssistant, host: str) -> None:
    """Clear the host from the discovery cache."""
    domain_data = hass.data[DOMAIN]
    discoveries: list[MowSconceDiscovery] = domain_data[MOW_SCONCE_DISCOVERY]
    domain_data[MOW_SCONCE_DISCOVERY] = [
        discovery for discovery in discoveries if discovery[ATTR_IPADDR] != host
    ]


async def async_discover_devices(
    hass: HomeAssistant, timeout: int, address: str | None = None
) -> list[MowSconceDiscovery]:
    """Discover mow_sconce devices."""
    if address:
        targets = [address]
    else:
        targets = [
            str(address)
            for address in await network.async_get_ipv4_broadcast_addresses(hass)
        ]

    scanner = MowSconceScanner()
    for idx, discovered in enumerate(
        await asyncio.gather(
            *[
                create_eager_task(scanner.async_scan(timeout=timeout, address=address))
                for address in targets
            ],
            return_exceptions=True,
        )
    ):
        if isinstance(discovered, Exception):
            _LOGGER.debug("Scanning %s failed with error: %s", targets[idx], discovered)
            continue

    if not address:
        return scanner.get_found_sconces()

    return [
        device for device in scanner.get_found_sconces() if device[ATTR_IPADDR] == address
    ]


async def async_discover_device(
    hass: HomeAssistant, host: str
) -> MowSconceDiscovery | None:
    """Direct discovery at a single ip instead of broadcast."""
    # If we are missing the unique_id we should be able to fetch it
    # from the device by doing a directed discovery at the host only
    for device in await async_discover_devices(hass, DIRECTED_DISCOVERY_TIMEOUT, host):
        if device[ATTR_IPADDR] == host:
            return device
    return None


@callback
def async_trigger_discovery(
    hass: HomeAssistant,
    discovered_devices: list[MowSconceDiscovery],
) -> None:
    """Trigger config flows for discovered devices."""
    for device in discovered_devices:
        discovery_flow.async_create_flow(
            hass,
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={**device},
        )
