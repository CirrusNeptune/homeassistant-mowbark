import lirc
import logging
import socket
from typing import Iterable

from homeassistant.components.remote import RemoteEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform
from homeassistant.helpers.typing import DiscoveryInfoType


import voluptuous as vol
import homeassistant.helpers.config_validation as cv

SERVICE_PRESS_BUTTON = "press_button"
ATTR_BUTTON = "button"

PRESS_BUTTON_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_BUTTON): vol.In(
            [
                'Power',
                'Mute',
                'TV',
                'HDMI2',
                'HDMI3',
                'HDMI4',
                'Opt',
                'Coax',
                'Bt',
                'Aux',
                'USB',
                'Music',
                'Movie',
                'Game',
                'Night',
                'NoDSP',
                'AllChStereo',
                'Surround',
                'Setup',
                'InfoStop',
                'Return',
                'SsePlus',
                'SseMinus',
                'Left',
                'Right',
                'Enter',
                'BassPlus',
                'BassMinus',
                'VolPlus',
                'VolMinus',
                'CenterPlus',
                'CenterMinus',
                'TreblePlus',
                'TrebleMinus',
                'SurroundSidePlus',
                'SurroundSideMinus',
                'SurroundBackPlus',
                'SurroundBackMinus',
                'SystemMemory1',
                'SystemMemory2',
                'SystemMemory3',
                'BtPlayPause',
                'BtStop',
                'BtPrevTrack',
                'BtNextTrack'
            ]
        ),
    }
)


class IRBlaster:
    def __init__(self):
        try:
            self.connect_client()
        except:
            pass

    def connect_client(self):
        self.client = lirc.Client(
            connection=lirc.LircdConnection(
                address="/lircd/lircd-nakaw",
                socket=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM),
                timeout=5.0
            )
        )

    def send_command(self, command):
        def inner_func():
            self.client.send_once("nakaw", command)
        try:
            inner_func()
        except Exception:
            self.connect_client()
            inner_func()


_LOGGER = logging.getLogger(__name__)

class NakamichiRemote(RemoteEntity):
    _attr_activity_list = ['Power', 'SsePlus', 'Mute']
    _attr_current_activity = ''
    _attr_unique_id = 'singleton'

    def __init__(self):
        self._attr_current_activity = ''
        self.fd = -1
        self.logger = _LOGGER
        self.irb = IRBlaster()

    # load config file or hardcode

    def turn_on(self, activity: str = None, **kwargs):
        self.logger.debug('sending on')
        self.send_command('Power')

    async def async_turn_on(self, activity: str = None, **kwargs):
        self.logger.debug('sending async on')
        self.turn_on()

    def turn_off(self, activity: str = None, **kwargs):
        self.logger.debug('sending off')

    async def async_turn_off(self, activity: str = None, **kwargs):
        self.logger.debug('sending async off')

    async def async_toggle(self, activity: str = None, **kwargs):
        self.logger.debug('sending async toggle')

    def send_command(self, command: Iterable[str], **kwargs):
        self.logger.debug(f'sending send command {command}')
        for com in command:
            self.irb.send_command(com)
            break

    async def async_send_command(self, command: Iterable[str], **kwargs):
        self.logger.debug('sending async send command')
        for com in command:
            self.irb.send_command(com)
            break

    async def async_press_button(self, button):
        await self.async_send_command([button])

async def async_setup_platform(
        hass: HomeAssistant,
        config: ConfigType,
        async_add_entities: AddEntitiesCallback,
        discovery_info: DiscoveryInfoType | None = None,
) -> None:
    async_add_entities([NakamichiRemote()])

    platform = async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_PRESS_BUTTON, PRESS_BUTTON_SCHEMA, "async_press_button"
    )
