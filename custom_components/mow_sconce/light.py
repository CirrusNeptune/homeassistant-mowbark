"""Support for Magic Home lights."""

from __future__ import annotations

import logging
from typing import Any, Optional, cast

from .mow_sconce import MowSconce

from homeassistant import config_entries
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGBW_COLOR,
    LightEntity,
    LightEntityFeature, ColorMode,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
)


_LOGGER = logging.getLogger(__name__)

MODE_ATTRS = {
    ATTR_EFFECT,
    ATTR_RGBW_COLOR,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sconce."""
    device: MowSconce = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MowSconceLight(device, entry.unique_id or entry.entry_id)])


class MowSconceLight(LightEntity):
    _attr_name = None
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = ['Static', 'Rainbow']
    _attr_supported_color_modes = {ColorMode.RGBW}
    _attr_color_mode = ColorMode.RGBW

    def __init__(
        self,
        device: MowSconce,
        base_unique_id: str,
    ) -> None:
        """Initialize the light."""
        self._device: MowSconce = device
        self._attr_unique_id = base_unique_id
        self._is_on = False
        self._brightness = 0
        self._rgbw: tuple[int, int, int, int] = (0, 0, 0, 255)
        self._effect: Optional[str] = None

    @property
    def is_on(self) -> bool:
        """Return true if device is on."""
        return self._is_on

    @property
    def brightness(self) -> int:
        """Return the brightness of this light between 0..255."""
        return self._brightness

    @property
    def rgbw_color(self) -> tuple[int, int, int, int]:
        """Return the rgbw color value."""
        return self._rgbw

    @property
    def effect(self) -> str | None:
        """Return the current effect."""
        return self._effect

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._is_on = True

        if brightness := kwargs.get(ATTR_BRIGHTNESS):
            self._brightness = brightness
        if rgbw := kwargs.get(ATTR_RGBW_COLOR):
            self._rgbw = rgbw
        if effect := kwargs.get(ATTR_EFFECT):
            self._effect = effect

        self._device.set_primary_color(self._rgbw)
        self._device.set_brightness(self._brightness)

        effect_index = 0
        if effect := self._effect:
            effect_index = self._attr_effect_list.index(effect)
        self._device.set_effect(effect_index)

        self.async_schedule_update_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._is_on = False
        self._device.set_brightness(0)
        self.async_schedule_update_ha_state()
