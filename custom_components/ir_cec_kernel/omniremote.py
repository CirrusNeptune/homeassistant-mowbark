import lirc
import logging
import socket
from typing import Iterable

from homeassistant.components.remote import RemoteEntity


class IRBlaster:
    def __init__(self):
        self.client = lirc.Client(
            connection=lirc.LircdConnection(
                address="/lircd/lircd-blaster",
                socket=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM),
                timeout=5.0
            )
        )

    def send_command(self, command):
        self.client.send_once("nakaw", command)


class NakamichiRemote(RemoteEntity):
    _attr_activity_list = ['Power', 'SsePlus', 'Mute']
    _attr_current_activity = '' # Music mode n' whatnot

    def __init__(self):
        self._attr_current_activity = ''
        self.fd = -1
        self.logger = logging.getLogger(self.__class__.__name__)
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
        self.irb.send_command(command)

    async def async_send_command(self, command: Iterable[str], **kwargs):
        self.logger.debug('sending async send command')
