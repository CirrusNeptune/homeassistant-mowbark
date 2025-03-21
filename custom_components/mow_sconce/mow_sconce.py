import asyncio
import contextlib
import socket
import logging
from asyncio import AbstractEventLoop
import time
from construct import this, Struct, Int8ul, Int16ul, Const, Array
from typing import TypedDict, Optional, Final, List, Tuple, Callable, Union, Dict

ATTR_IPADDR: Final = "ipaddr"
ATTR_ID: Final = "id"

_LOGGER = logging.getLogger(__name__)


class MowSconceDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        on_response: Callable[[bytes, Tuple[str, int]], None],
    ) -> None:
        """Init the discovery protocol."""
        self.transport = None
        self.on_response = on_response

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        """Trigger on_response."""
        self.on_response(data, addr)

    def error_received(self, ex: Optional[Exception]) -> None:
        """Handle error."""
        _LOGGER.debug("MowSconceDatagramProtocol error: %s", ex)

    def connection_lost(self, ex: Optional[Exception]) -> None:
        """The connection is lost."""


class MowSconceDiscovery(TypedDict):
    """A mow_sconce led device."""

    ipaddr: str
    id: str  # aka mac


class MowSconce:
    CMD_PORT: int = 6721

    def __init__(self, ipaddr: str, discovery: Optional[MowSconceDiscovery] = None):
        """Init and setup the sconce."""
        self._destination: (str, int) = (ipaddr, MowSconce.CMD_PORT)
        self._discovery = discovery
        self._updated_callback: Optional[Callable[[], None]] = None
        self.loop = asyncio.get_running_loop()
        self.transport: Optional[asyncio.transports.DatagramTransport] = None

    @property
    def ipaddr(self) -> str:
        return self._destination[0]

    @property
    def discovery(self) -> Optional[MowSconceDiscovery]:
        """Return the discovery data."""
        return self._discovery

    @discovery.setter
    def discovery(self, value: MowSconceDiscovery) -> None:
        """Set the discovery data."""
        self._discovery = value

    async def async_setup(self, updated_callback: Callable[[], None]) -> None:
        """Setup the connection and fetch initial state."""
        self._updated_callback = updated_callback
        try:
            await self._async_setup()
        except Exception:  # pylint: disable=broad-except
            self._async_stop()
            raise

    async def _async_setup(self):
        """Setup command endpoint with mow sconce."""
        def _on_response(data: bytes, addr: Tuple[str, int]) -> None:
            _LOGGER.debug("cmd response: %s <= %s", addr, data)
            if self._updated_callback:
                self._updated_callback()

        self.transport, _ = await self.loop.create_datagram_endpoint(
            lambda: MowSconceDatagramProtocol(_on_response),
            family=socket.AF_INET,
            remote_addr=self._destination,
        )

    async def async_stop(self):
        self._async_stop()

    def _async_stop(self):
        if self.transport:
            self.transport.close()
            self.transport = None

    def _send_cmd(self, cmd):
        if self.transport:
            _LOGGER.debug("cmd: %s => %s", self._destination, cmd)
            self.transport.sendto(cmd)
        else:
            _LOGGER.warning("transport not available to send cmd")

    SetColorList = Struct("cmd" / Const(b'\x00'),
                          "num_colors" / Int8ul,
                          "colors" / Array(this.num_colors, Array(4, Int8ul)))

    def set_color_list(self, colors: List[Tuple[int, int, int, int]]):
        self._send_cmd(self.SetColorList.build({"num_colors": len(colors), "colors": colors}))

    ShiftColor = Struct("cmd" / Const(b'\x01'),
                        "color" / Array(4, Int8ul))

    def shift_color(self, color: Tuple[int, int, int, int]):
        self._send_cmd(self.ShiftColor.build({"color": color}))

    SetPrimaryColor = Struct("cmd" / Const(b'\x02'),
                             "color" / Array(4, Int8ul))

    def set_primary_color(self, color: Tuple[int, int, int, int]):
        self._send_cmd(self.SetPrimaryColor.build({"color": color}))

    SetEffect = Struct("cmd" / Const(b'\x03'),
                       "effect" / Int8ul)

    def set_effect(self, effect: int):
        self._send_cmd(self.SetEffect.build({"effect": effect}))

    SetEffectSpeed = Struct("cmd" / Const(b'\x04'),
                            "effect_speed" / Int16ul)

    def set_effect_speed(self, effect_speed: int):
        self._send_cmd(self.SetEffectSpeed.build({"effect_speed": effect_speed}))

    SetBrightness = Struct("cmd" / Const(b'\x05'),
                            "brightness" / Int8ul)

    def set_brightness(self, brightness: int):
        self._send_cmd(self.SetBrightness.build({"brightness": brightness}))


class MowSconceScanner:
    DISCOVERY_PORT: int = 6722
    BROADCAST_ADDRESS = "<broadcast>"
    BROADCAST_FREQUENCY = 6

    def __init__(self):
        self.loop: AbstractEventLoop = asyncio.get_running_loop()
        self._discoveries: Dict[str, MowSconceDiscovery] = {}

    @property
    def found_sconces(self) -> List[MowSconceDiscovery]:
        """Return only complete bulb discoveries."""
        return list(self._discoveries.values())

    @staticmethod
    def _send_message(
        sender: Union[socket.socket, asyncio.DatagramTransport],
        destination: Tuple[str, int],
        message: bytes,
    ) -> None:
        _LOGGER.debug("udp: %s => %s", destination, message)
        sender.sendto(message, destination)

    def get_found_sconces(self) -> List[MowSconceDiscovery]:
        return self.found_sconces

    def _destination_from_address(self, address: Optional[str]) -> Tuple[str, int]:
        if address is None:
            address = self.BROADCAST_ADDRESS
        return address, self.DISCOVERY_PORT

    @staticmethod
    def get_discovery_message() -> bytes:
        return b'mow sconce discover'

    @staticmethod
    def get_discovery_reply_message() -> str:
        return 'mow sconce reply: '

    async def _async_run_scan(
        self,
        transport: asyncio.DatagramTransport,
        destination: Tuple[str, int],
        timeout: int,
        found_all_future: "asyncio.Future[bool]",
    ) -> None:
        """Send the scans."""
        discovery_message = self.get_discovery_message()
        self._send_message(transport, destination, discovery_message)
        quit_time = time.monotonic() + timeout
        time_out = timeout / self.BROADCAST_FREQUENCY
        while True:
            try:
                async with asyncio.timeout(time_out):
                    await asyncio.shield(found_all_future)
            except asyncio.TimeoutError:
                pass
            else:
                return  # found_all
            time_out = min(
                quit_time - time.monotonic(), timeout / self.BROADCAST_FREQUENCY
            )
            if time_out <= 0:
                return
            # No response, send broadcast again in cast it got lost
            self._send_message(transport, destination, discovery_message)

    @staticmethod
    def _process_response(
        data: Optional[bytes],
        from_address: Tuple[str, int],
        address: Optional[str],
        response_list: Dict[str, MowSconceDiscovery],
    ) -> bool:
        """Process a response.

        Returns True if processing should stop
        """
        if data is None:
            return False
        decoded_data = data.decode("ascii")
        MowSconceScanner._process_data(from_address, decoded_data, response_list)
        if address is None or address not in response_list:
            return False
        return True

    @staticmethod
    def _process_data(
        from_address: Tuple[str, int],
        decoded_data: str,
        response_list: Dict[str, MowSconceDiscovery],
    ) -> None:
        """Process data."""
        reply_start = MowSconceScanner.get_discovery_reply_message()
        if decoded_data.startswith(reply_start):
            from_ipaddr = from_address[0]
            from_mac = decoded_data[len(reply_start):]
            response_list.setdefault(
                from_ipaddr,
                MowSconceDiscovery(
                    ipaddr=from_ipaddr,
                    id=from_mac,
                ),
            )

    async def async_scan(
        self, timeout: int = 10, address: Optional[str] = None
    ) -> List[MowSconceDiscovery]:
        """Discover mow sconce."""
        destination = self._destination_from_address(address)
        found_all_future: "asyncio.Future[bool]" = self.loop.create_future()

        def _on_response(data: bytes, addr: Tuple[str, int]) -> None:
            _LOGGER.debug("discover: %s <= %s", addr, data)
            if self._process_response(data, addr, address, self._discoveries):
                with contextlib.suppress(asyncio.InvalidStateError):
                    found_all_future.set_result(True)

        transport, _ = await self.loop.create_datagram_endpoint(
            lambda: MowSconceDatagramProtocol(_on_response),
            family=socket.AF_INET,
            allow_broadcast=True,
        )
        try:
            await self._async_run_scan(
                transport, destination, timeout, found_all_future
            )
        finally:
            transport.close()

        return self.found_sconces
