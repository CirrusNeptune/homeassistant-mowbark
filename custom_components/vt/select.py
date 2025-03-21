import asyncio
import os
import sys
import pathlib
import logging
from typing import Optional

from . import vt_api

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import DiscoveryInfoType, ConfigType

_LOGGER = logging.getLogger(__name__)


class VtEventProtocol(asyncio.protocols.SubprocessProtocol):
    def __init__(self, vt_entity):
        self._vt_entity = vt_entity
        self._transport: Optional[asyncio.transports.SubprocessTransport] = None
        self._token = bytearray(0)

    def connection_made(self, transport: asyncio.transports.SubprocessTransport):
        _LOGGER.debug('connection_made')
        self._transport = transport

    def pipe_data_received(self, fd, data):
        _LOGGER.debug(f'pipe_data_received({fd}, {data})')
        if fd != 1:
            return

        latest_complete_token = None
        for byte in data:
            if byte == ord(b'\n'):
                latest_complete_token = self._token
                self._token = bytearray(0)
            else:
                self._token.append(byte)
        if latest_complete_token:
            self._vt_entity.on_vt_switch(int(latest_complete_token))

    def _maybe_close_transport(self):
        if self._transport:
            self._transport.close()
            self._transport = None

    def connection_lost(self, exc: Exception | None) -> None:
        _LOGGER.debug('connection_lost')
        self._maybe_close_transport()

    def pipe_connection_lost(self, fd, exc):
        _LOGGER.debug(f'pipe_connection_lost({fd})')
        self._maybe_close_transport()

    def process_exited(self):
        _LOGGER.debug('process_exited')
        self._maybe_close_transport()


VT_NUMBERS_TO_NAMES = {
    1: 'Kodi',
    2: 'Steam',
    3: 'KWin'
}
VT_NAMES_TO_NUMBERS = {VT_NUMBERS_TO_NAMES[k]: k for k in VT_NUMBERS_TO_NAMES}


class VtEntity(SelectEntity):
    _attr_unique_id = 'singleton'
    _attr_has_entity_name = True

    def __init__(self):
        self.fd: int = -1
        self.event_transport: Optional[asyncio.transports.SubprocessTransport] = None
        self._attr_options = []
        self._attr_current_option = None

    def update_state(self):
        if self.fd == -1:
            return
        state = vt_api.get_state(self.fd)
        new_options = []
        current_option = None
        for i in range(1, 16):
            if state.v_state & (1 << i):
                if i in VT_NUMBERS_TO_NAMES:
                    option = VT_NUMBERS_TO_NAMES[i]
                else:
                    option = f'{i}'
                new_options.append(option)
                if i == state.v_active:
                    current_option = option
        self._attr_options = new_options
        self._attr_current_option = current_option
        self.schedule_update_ha_state()

    async def async_select_option(self, option: str) -> None:
        if self.fd == -1:
            return
        if option in VT_NAMES_TO_NUMBERS:
            number = VT_NAMES_TO_NUMBERS[option]
        else:
            number = int(option)
        vt_api.activate(self.fd, number)

    def on_vt_switch(self, new_vt) -> None:
        _LOGGER.debug(f'on_vt_switch({new_vt})')
        self.update_state()

    async def async_added_to_hass(self) -> None:
        self.fd = os.open('/dev/tty0', os.O_WRONLY)
        self.update_state()
        proc_script_path = pathlib.Path(pathlib.Path(__file__).parent, 'vt_event_proc.py')
        self.event_transport, _ = await asyncio.get_event_loop().subprocess_exec(
            lambda: VtEventProtocol(self),
            sys.executable, str(proc_script_path),
            stdin=None, stdout=asyncio.subprocess.PIPE,
            stderr=None)

    async def async_will_remove_from_hass(self) -> None:
        if self.event_transport:
            self.event_transport.close()
            self.event_transport = None
        if self.fd != -1:
            os.close(self.fd)
            self.fd = -1


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    async_add_entities([VtEntity()])

