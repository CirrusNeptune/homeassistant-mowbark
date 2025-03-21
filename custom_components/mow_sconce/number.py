from homeassistant import config_entries
from .mow_sconce import MowSconce
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sconce."""
    device: MowSconce = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MowSconceEffectSpeed(device, entry.unique_id or entry.entry_id)])


class MowSconceEffectSpeed(NumberEntity):
    _attr_native_min_value = 0
    _attr_native_max_value = 65535
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        device: MowSconce,
        base_unique_id: str,
    ) -> None:
        """Initialize the light."""
        self._device: MowSconce = device
        self._attr_unique_id = f"{base_unique_id}_effect_speed"
        self._attr_native_value = 32768

    async def async_set_native_value(self, value: float) -> None:
        int_value = min(65535, max(0, int(value)))
        self._attr_native_value = float(int_value)
        self._device.set_effect_speed(int_value)
        self.async_schedule_update_ha_state()
