"""Config flow for Switch as X integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.const import CONF_DEVICE_ID
from homeassistant.helpers import selector
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaConfigFlowHandler,
    SchemaFlowFormStep,
)

from homeassistant.components.light.const import DOMAIN as LIGHT_DOMAIN
from .const import DOMAIN, CONF_LIGHT_ID, CONF_SCENES, CONF_SCENES_X2

from pywizlight.scenes import SCENES

CONFIG_FLOW = {
    "user": SchemaFlowFormStep(
        vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(manufacturer="Zooz", model="ZEN32")
                ),
                vol.Required(CONF_LIGHT_ID): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=LIGHT_DOMAIN)
                ),
            }
        )
    )
}

OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(
        vol.Schema(
            {
                vol.Optional(k): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=list(SCENES.values()))
                ) for k in CONF_SCENES
            } | {
                vol.Optional(k): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=list(SCENES.values()))
                ) for k in CONF_SCENES_X2
            }
        )
    ),
}


class MowbarkSceneControllerFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Handle a config flow for Mowbark Scene Controller."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW
    options_flow_reloads = True

    VERSION = 1
    MINOR_VERSION = 0

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        registry = dr.async_get(self.hass)
        device_entry = registry.async_get(options[CONF_DEVICE_ID])
        return device_entry.name_by_user or device_entry.name or device_entry.id
