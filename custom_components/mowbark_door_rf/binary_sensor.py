from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription, \
    BinarySensorDeviceClass
import asyncio
import logging
import time

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import DiscoveryInfoType, ConfigType

_LOGGER = logging.getLogger(__name__)


class MowBarkDoorRfProtocol(asyncio.Protocol):
    def __init__(self, entity):
        self.entity = entity

    def connection_made(self, transport):
        _LOGGER.info('RF server connected')

    def data_received(self, data):
        if len(data) == 0:
            _LOGGER.info('RF server received empty payload')
            return
        self.entity.on_cmd_received(data[-1])

    def connection_lost(self, exc):
        _LOGGER.info('RF server closed the connection')


class MowBarkDoorRfEntity(BinarySensorEntity):
    _attr_unique_id = 'singleton'
    entity_description = BinarySensorEntityDescription(key='door', device_class=BinarySensorDeviceClass.DOOR)

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.start_button_time: float | None = None
        self.long_press_triggered: bool = False
        self.button_timer_handle: asyncio.TimerHandle | None = None
        super().__init__()

    async def async_added_to_hass(self) -> None:
        transport, _ = await self.hass.loop.create_connection(
            lambda: MowBarkDoorRfProtocol(self),
            self.host, self.port
        )
        self.async_on_remove(lambda: transport.close())

    def set_open_state(self, state):
        if self._attr_is_on != state:
            self._attr_is_on = state
            self.async_write_ha_state()
            _LOGGER.info("Door opened" if state else "Door closed")

    def on_button_signal(self):
        if self.start_button_time is None:
            self.start_button_time = time.monotonic()
        elif not self.long_press_triggered and time.monotonic() - self.start_button_time > 0.5:
            self.long_press_triggered = True
            self.hass.bus.fire("mowbark_button_long_pressed", {})
            _LOGGER.info(f'Button long pressed')

        def on_button_timer_expired():
            if not self.long_press_triggered:
                self.hass.bus.fire("mowbark_button_pressed", {})
                _LOGGER.info(f'Button pressed')
            else:
                _LOGGER.info(f'Long press reset')
            self.button_timer_handle = None
            self.start_button_time = None
            self.long_press_triggered = False

        if self.button_timer_handle is not None:
            self.button_timer_handle.cancel()
        self.button_timer_handle = self.hass.loop.call_later(0.1, on_button_timer_expired)


    def on_cmd_received(self, cmd):
        if cmd == 10:
            self.set_open_state(True)
        elif cmd == 14:
            self.set_open_state(False)
        elif cmd == 1:
            self.on_button_signal()
        else:
            _LOGGER.info(f'Unknown command {cmd:x}')


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    async_add_entities([MowBarkDoorRfEntity('host.docker.internal', 8124)])

