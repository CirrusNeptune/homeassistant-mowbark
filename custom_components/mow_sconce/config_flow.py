"""Config flow for mow_sconce."""

from __future__ import annotations

from typing import Any, cast

from .mow_sconce import (
    ATTR_ID,
    ATTR_IPADDR,
)
from .mow_sconce import MowSconceDiscovery
import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_IGNORE,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_DEVICE, CONF_HOST
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import DiscoveryInfoType

from . import async_mow_sconce_for_host
from .const import (
    DISCOVER_SCAN_TIMEOUT,
    DOMAIN,
    MOW_SCONCE_DISCOVERY_SIGNAL,
)
from .discovery import (
    async_discover_device,
    async_discover_devices,
    async_name_from_discovery,
    async_populate_data_from_discovery,
    async_update_entry_from_discovery,
)


class MowSconceConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for mow_sconce Integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: dict[str, MowSconceDiscovery] = {}
        self._discovered_device: MowSconceDiscovery | None = None

    async def async_step_integration_discovery(
        self, discovery_info: DiscoveryInfoType
    ) -> ConfigFlowResult:
        """Handle integration discovery."""
        self._discovered_device = cast(MowSconceDiscovery, discovery_info)
        return await self._async_handle_discovery()

    async def _async_set_discovered_mac(
        self, device: MowSconceDiscovery
    ) -> None:
        """Set the discovered mac."""
        mac_address = device[ATTR_ID]
        assert mac_address is not None
        mac = dr.format_mac(mac_address)
        await self.async_set_unique_id(mac)
        for entry in self._async_current_entries(include_ignore=True):
            if not (
                entry.data.get(CONF_HOST) == device[ATTR_IPADDR]
                or entry.unique_id == mac
            ):
                continue
            if entry.source == SOURCE_IGNORE:
                raise AbortFlow("already_configured")
            if (
                async_update_entry_from_discovery(
                    self.hass, entry, device
                )
                and entry.state
                not in (
                    ConfigEntryState.SETUP_IN_PROGRESS,
                    ConfigEntryState.NOT_LOADED,
                )
            ) or entry.state == ConfigEntryState.SETUP_RETRY:
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
            else:
                async_dispatcher_send(
                    self.hass,
                    MOW_SCONCE_DISCOVERY_SIGNAL.format(entry_id=entry.entry_id),
                )
            raise AbortFlow("already_configured")

    async def _async_handle_discovery(self) -> ConfigFlowResult:
        """Handle any discovery."""
        device = self._discovered_device
        assert device is not None
        await self._async_set_discovered_mac(device)
        host = device[ATTR_IPADDR]
        self.context[CONF_HOST] = host
        for progress in self._async_in_progress():
            if progress.get("context", {}).get(CONF_HOST) == host:
                return self.async_abort(reason="already_in_progress")
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        assert self._discovered_device is not None
        device = self._discovered_device
        mac_address = device[ATTR_ID]
        assert mac_address is not None
        if user_input is not None:
            return self._async_create_entry_from_device(self._discovered_device)

        self._set_confirm_only()
        placeholders = {
            "id": mac_address,
            "ipaddr": device[ATTR_IPADDR],
        }
        self.context["title_placeholders"] = placeholders
        return self.async_show_form(
            step_id="discovery_confirm", description_placeholders=placeholders
        )

    @callback
    def _async_create_entry_from_device(
        self, device: MowSconceDiscovery
    ) -> ConfigFlowResult:
        """Create a config entry from a device."""
        self._async_abort_entries_match({CONF_HOST: device[ATTR_IPADDR]})
        name = async_name_from_discovery(device)
        data: dict[str, Any] = {CONF_HOST: device[ATTR_IPADDR]}
        async_populate_data_from_discovery(data, data, device)
        return self.async_create_entry(
            title=name,
            data=data,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            if not (host := user_input[CONF_HOST]):
                return await self.async_step_pick_device()
            device = await self._async_try_connect(host, None)
            if (mac_address := device[ATTR_ID]) is not None:
                await self.async_set_unique_id(
                    dr.format_mac(mac_address), raise_on_progress=False
                )
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
            return self._async_create_entry_from_device(device)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_HOST, default=""): str}),
            errors=errors,
        )

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the step to pick discovered device."""
        if user_input is not None:
            mac = user_input[CONF_DEVICE]
            await self.async_set_unique_id(mac, raise_on_progress=False)
            device = self._discovered_devices[mac]
            return self._async_create_entry_from_device(device)

        current_unique_ids = self._async_current_ids()
        current_hosts = {
            entry.data[CONF_HOST]
            for entry in self._async_current_entries(include_ignore=False)
        }
        discovered_devices = await async_discover_devices(
            self.hass, DISCOVER_SCAN_TIMEOUT
        )
        self._discovered_devices = {}
        for device in discovered_devices:
            mac_address = device[ATTR_ID]
            assert mac_address is not None
            self._discovered_devices[dr.format_mac(mac_address)] = device
        devices_name = {
            mac: f"{async_name_from_discovery(device)} ({device[ATTR_IPADDR]})"
            for mac, device in self._discovered_devices.items()
            if mac not in current_unique_ids
            and device[ATTR_IPADDR] not in current_hosts
        }
        # Check if there is at least one device
        if not devices_name:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE): vol.In(devices_name)}),
        )

    async def _async_try_connect(
        self, host: str, discovery: MowSconceDiscovery | None
    ) -> MowSconceDiscovery:
        """Try to connect."""
        self._async_abort_entries_match({CONF_HOST: host})
        if device := await async_discover_device(self.hass, host):
            return device
        sconce = async_mow_sconce_for_host(host, discovery=device)
        sconce.discovery = discovery
        try:
            await sconce.async_setup(lambda: None)
        finally:
            await sconce.async_stop()
        return MowSconceDiscovery(
            ipaddr=host,
            id=discovery[ATTR_ID] if discovery else None,
        )
