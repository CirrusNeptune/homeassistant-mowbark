import asyncio
import logging
import os
import fcntl
import struct
import select
from datetime import timedelta, datetime
from enum import Enum, Flag

from homeassistant.components.media_player import MediaPlayerEntity, MediaPlayerEntityFeature, MediaPlayerState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform
from homeassistant.helpers.typing import DiscoveryInfoType, ConfigType
from homeassistant.helpers.event import async_track_time_interval

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_DIRBITS = 2

_IOC_NRMASK = ((1 << _IOC_NRBITS) - 1)
_IOC_TYPEMASK = ((1 << _IOC_TYPEBITS) - 1)
_IOC_SIZEMASK = ((1 << _IOC_SIZEBITS) - 1)
_IOC_DIRMASK = ((1 << _IOC_DIRBITS) - 1)

_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = (_IOC_NRSHIFT + _IOC_NRBITS)
_IOC_SIZESHIFT = (_IOC_TYPESHIFT + _IOC_TYPEBITS)
_IOC_DIRSHIFT = (_IOC_SIZESHIFT + _IOC_SIZEBITS)

_IOC_WRITE = 1
_IOC_READ = 2


def _ioc(d, tp, nr, size):
    return (d << _IOC_DIRSHIFT) | (ord(tp) << _IOC_TYPESHIFT) | (nr << _IOC_NRSHIFT) | (size << _IOC_SIZESHIFT)


def _iowr(tp, nr, size):
    return _ioc(_IOC_READ | _IOC_WRITE, tp, nr, size)


def _ior(tp, nr, size):
    return _ioc(_IOC_READ, tp, nr, size)


def _iow(tp, nr, size):
    return _ioc(_IOC_WRITE, tp, nr, size)


CEC_MODE_NO_INITIATOR = (0x0 << 0)
CEC_MODE_INITIATOR = (0x1 << 0)
CEC_MODE_EXCL_INITIATOR = (0x2 << 0)
CEC_MODE_INITIATOR_MSK = 0x0f

CEC_MODE_NO_FOLLOWER = (0x0 << 4)
CEC_MODE_FOLLOWER = (0x1 << 4)
CEC_MODE_EXCL_FOLLOWER = (0x2 << 4)
CEC_MODE_EXCL_FOLLOWER_PASSTHRU = (0x3 << 4)
CEC_MODE_MONITOR = (0xe << 4)
CEC_MODE_MONITOR_ALL = (0xf << 4)
CEC_MODE_FOLLOWER_MSK = 0xf0

CEC_G_MODE = _ior('a', 8, 4)
CEC_S_MODE = _iow('a', 9, 4)
CEC_ADAP_G_PHYS_ADDR = _ior('a', 1, 2)
CEC_ADAP_S_PHYS_ADDR = _iow('a', 2, 2)


def do_ioctl(fd, cmd, buf):
    fcntl.ioctl(fd, cmd, buf)


def cec_g_mode(fd):
    buf = bytearray(4)
    do_ioctl(fd, CEC_G_MODE, buf)
    return struct.unpack("I", buf)[0]


def cec_s_mode(fd, mode):
    buf = struct.pack('I', mode)
    do_ioctl(fd, CEC_S_MODE, buf)


def cec_g_phys_addr(fd):
    buf = bytearray(2)
    do_ioctl(fd, CEC_ADAP_G_PHYS_ADDR, buf)
    return struct.unpack("H", buf)[0]


def cec_s_phys_addr(fd, phys_addr):
    buf = struct.pack('H', phys_addr)
    do_ioctl(fd, CEC_ADAP_S_PHYS_ADDR, buf)


class Cmd(Enum):
    CEC_MSG_IMAGE_VIEW_ON = 0x4
    CEC_MSG_STANDBY = 0x36
    CEC_MSG_ROUTING_CHANGE = 0x80
    CEC_MSG_ROUTING_INFORMATION = 0x81
    CEC_MSG_ACTIVE_SOURCE = 0x82
    CEC_MSG_REPORT_PHYSICAL_ADDR = 0x84
    CEC_MSG_REQUEST_ACTIVE_SOURCE = 0x85
    CEC_MSG_SET_STREAM_PATH = 0x86
    CEC_MSG_DEVICE_VENDOR_ID = 0x87
    CEC_MSG_GIVE_DEVICE_POWER_STATUS = 0x8f
    CEC_MSG_REPORT_POWER_STATUS = 0x90
    CEC_MSG_USER_CONTROL_PRESSED = 0x44
    CEC_MSG_USER_CONTROL_RELEASED = 0x45
    CEC_MSG_SET_SYSTEM_AUDIO_MODE = 0x72


class UiCmd(Enum):
    CEC_OP_UI_CMD_SELECT = 0x0
    CEC_OP_UI_CMD_UP = 0x1
    CEC_OP_UI_CMD_DOWN = 0x2
    CEC_OP_UI_CMD_LEFT = 0x3
    CEC_OP_UI_CMD_RIGHT = 0x4
    CEC_OP_UI_CMD_DEVICE_ROOT_MENU = 0x9
    CEC_OP_UI_CMD_BACK = 0xd
    CEC_OP_UI_CMD_ENTER = 0x2b
    CEC_OP_UI_CMD_VOLUME_UP = 0x41
    CEC_OP_UI_CMD_VOLUME_DOWN = 0x42


UI_COMMAND_TABLE = {
    "select": UiCmd.CEC_OP_UI_CMD_SELECT,
    "up": UiCmd.CEC_OP_UI_CMD_UP,
    "down": UiCmd.CEC_OP_UI_CMD_DOWN,
    "left": UiCmd.CEC_OP_UI_CMD_LEFT,
    "right": UiCmd.CEC_OP_UI_CMD_RIGHT,
    "device-root-menu": UiCmd.CEC_OP_UI_CMD_DEVICE_ROOT_MENU,
    "back": UiCmd.CEC_OP_UI_CMD_BACK,
    "enter": UiCmd.CEC_OP_UI_CMD_ENTER,
}


class PwrState(Enum):
    CEC_OP_POWER_STATUS_ON = 0
    CEC_OP_POWER_STATUS_STANDBY = 1
    CEC_OP_POWER_STATUS_TO_ON = 2
    CEC_OP_POWER_STATUS_TO_STANDBY = 3


class TxStatus(Flag):
    CEC_TX_STATUS_OK = 0x1
    CEC_TX_STATUS_ARB_LOST = 0x02
    CEC_TX_STATUS_NACK = 0x04
    CEC_TX_STATUS_LOW_DRIVE = 0x08
    CEC_TX_STATUS_ERROR = 0x10
    CEC_TX_STATUS_MAX_RETRIES = 0x20


class RxStatus(Flag):
    CEC_RX_STATUS_OK = 0x1
    CEC_RX_STATUS_TIMEOUT = 0x2
    CEC_RX_STATUS_FEATURE_ABORT = 0x4


SERVICE_PRESS_BUTTON = "press_button"
ATTR_BUTTON = "button"

PRESS_BUTTON_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_BUTTON): vol.In(UI_COMMAND_TABLE.keys()),
    }
)


class CecParsedMsg:
    def __init__(self, buf):
        if len(buf) >= 1:
            self.initiator = buf[0] >> 4
            self.destination = buf[0] & 0xf
        else:
            self.initiator = None
            self.destination = None

        if len(buf) >= 2:
            try:
                self.cmd = Cmd(buf[1])
            except ValueError:
                self.cmd = None
                _LOGGER.warning('%s is not a valid command', hex(buf[1]))
        else:
            self.cmd = None

        if len(buf) >= 3:
            self.args = buf[2:]

    def __repr__(self):
        return repr(self.__dict__)

    @staticmethod
    def build(initiator, destination, cmd, *args):
        if initiator not in range(0, 16):
            raise IndexError(f'initiator {initiator} out of range [0,16)')
        if destination not in range(0, 16):
            raise IndexError(f'destination {destination} out of range [0,16)')
        msg_buf = bytearray()
        msg_buf.append(initiator << 4 | destination)
        if hasattr(cmd, 'value'):
            cmd = cmd.value
        msg_buf.append(cmd)
        for arg in args:
            if hasattr(arg, 'value'):
                arg = arg.value
            msg_buf.append(arg)
        return msg_buf


class CecMsg:
    CEC_MSG_STRUCT_SIZE = 56
    CEC_TRANSMIT = _iowr('a', 5, CEC_MSG_STRUCT_SIZE)
    CEC_RECEIVE = _iowr('a', 6, CEC_MSG_STRUCT_SIZE)

    def __init__(self, buf):
        self.tx_ts, \
            self.rx_ts, \
            self.length, \
            self.timeout, \
            self.sequence, \
            self.flags = struct.unpack('QQIIII', buf[:32])
        self.msg = buf[32:32 + self.length]
        self.reply, \
            rx_status, \
            self.tx_status, \
            self.tx_arb_lost_cnt, \
            self.tx_nack_cnt, \
            self.tx_low_drive_cnt, \
            self.tx_error_cnt = struct.unpack('BBBBBBB', buf[48:55])
        self.rx_status = RxStatus(rx_status)

    def __repr__(self):
        return repr(self.__dict__)

    def parse(self):
        return CecParsedMsg(self.msg)

    @staticmethod
    def receive(fd):
        buf = bytearray(CecMsg.CEC_MSG_STRUCT_SIZE)
        try:
            do_ioctl(fd, CecMsg.CEC_RECEIVE, buf)
            msg = CecMsg(buf)
            # if RxStatus.CEC_RX_STATUS_OK not in msg.rx_status:
            #    raise RuntimeError('cec_receive status not ok')
            return msg
        except BlockingIOError:
            return None

    @staticmethod
    def transmit(fd, msg, reply):
        assert len(msg) <= 16
        buf = bytearray(CecMsg.CEC_MSG_STRUCT_SIZE)
        buf[:32] = struct.pack('QQIIII',
                               0,  # self.tx_ts
                               0,  # self.rx_ts
                               len(msg),  # self.length
                               0,  # self.timeout
                               0,  # self.sequence
                               0)  # self.flags
        buf[32:32 + len(msg)] = msg
        buf[48:55] = struct.pack('BBBBBBB',
                                 1 if reply else 0,  # self.reply
                                 0,  # self.rx_status
                                 0,  # self.tx_status
                                 0,  # self.tx_arb_lost_cnt
                                 0,  # self.tx_nack_cnt
                                 0,  # self.tx_low_drive_cnt
                                 0)  # self.tx_error_cnt
        parsed_msg = CecMsg(buf)
        _LOGGER.debug('sending %s', parsed_msg)
        _LOGGER.debug(parsed_msg.parse())
        do_ioctl(fd, CecMsg.CEC_TRANSMIT, buf)
        # tx_status = TxStatus(buf[50])
        # if TxStatus.CEC_TX_STATUS_OK not in tx_status:
        #    raise RuntimeError('cec_transmit status not ok')


class CecEventType(Enum):
    CEC_EVENT_STATE_CHANGE = 1
    CEC_EVENT_LOST_MSGS = 2


class CecEventFlags(Flag):
    CEC_EVENT_FL_INITIAL_STATE = 0x1
    CEC_EVENT_FL_DROPPED_EVENTS = 0x2


class CecEvent:
    CEC_EVENT_STRUCT_SIZE = 80
    CEC_DQEVENT = _iowr('a', 7, CEC_EVENT_STRUCT_SIZE)

    def __init__(self, buf):
        self.ts, \
            event, \
            flags = struct.unpack("QII", buf[:16])
        self.event = CecEventType(event)
        self.flags = CecEventFlags(flags)

        if self.event == CecEventType.CEC_EVENT_STATE_CHANGE:
            self.phys_addr, \
                self.log_addr_mask, \
                self.have_conn_info = struct.unpack("HHH", buf[16:22])
        elif self.event == CecEventType.CEC_EVENT_LOST_MSGS:
            self.lost_msgs = struct.unpack("I", buf[16:20])

    def __repr__(self):
        return repr(self.__dict__)

    @staticmethod
    def deque(fd):
        buf = bytearray(CecEvent.CEC_EVENT_STRUCT_SIZE)
        try:
            do_ioctl(fd, CecEvent.CEC_DQEVENT, buf)
            return CecEvent(buf)
        except BlockingIOError:
            return None


class CecLogAddrs:
    CEC_LOG_ADDRS_STRUCT_SIZE = 92
    CEC_ADAP_G_LOG_ADDRS = _ior('a', 3, CEC_LOG_ADDRS_STRUCT_SIZE)
    CEC_ADAP_S_LOG_ADDRS = _iowr('a', 4, CEC_LOG_ADDRS_STRUCT_SIZE)

    CEC_MAX_LOG_ADDRS = 4

    def __init__(self, buf):
        self.log_addr = buf[:4]
        self.log_addr_mask, \
            self.cec_version, \
            self.num_log_addrs, \
            self.vendor_id, \
            self.flags = struct.unpack("HBBII", buf[4:16])
        self.osd_name = buf[16:31]
        self.primary_device_type = buf[31:35]
        self.log_addr_type = buf[35:39]
        self.all_device_types = buf[39:43]
        self.features = buf[43:91]

    def __repr__(self):
        return repr(self.__dict__)

    @staticmethod
    def get(fd):
        buf = bytearray(CecLogAddrs.CEC_LOG_ADDRS_STRUCT_SIZE)
        do_ioctl(fd, CecLogAddrs.CEC_ADAP_G_LOG_ADDRS, buf)
        return CecLogAddrs(buf)

    def set(self, fd):
        buf = bytearray(CecLogAddrs.CEC_LOG_ADDRS_STRUCT_SIZE)
        buf[:4] = self.log_addr
        buf[4:16] = struct.pack("HBBII",
                                self.log_addr_mask,
                                self.cec_version,
                                self.num_log_addrs,
                                self.vendor_id,
                                self.flags)
        buf[16:31] = self.osd_name
        buf[31:35] = self.primary_device_type
        buf[35:39] = self.log_addr_type
        buf[39:43] = self.all_device_types
        buf[43:91] = self.features
        do_ioctl(fd, CecLogAddrs.CEC_ADAP_S_LOG_ADDRS, buf)


def get_laddr(fd):
    laddrs = CecLogAddrs.get(fd)
    return laddrs.log_addr[0]


def clear_laddrs(fd):
    la_buf = bytearray(CecLogAddrs.CEC_LOG_ADDRS_STRUCT_SIZE)
    do_ioctl(fd, CecLogAddrs.CEC_ADAP_S_LOG_ADDRS, la_buf)


SOUND_BAR_INDEX_MAP = [1, 2, 3]


def phys_addr_to_string(phys_addr: int):
    return f'{hex((phys_addr >> 12) & 0xf)}.{hex((phys_addr >> 8) & 0xf)}.{hex((phys_addr >> 4) & 0xf)}.{hex(phys_addr & 0xf)}'



class HdmiCecKernelEntity(MediaPlayerEntity):
    _attr_has_entity_name = True
    _attr_supported_features = \
        MediaPlayerEntityFeature.TURN_ON | \
        MediaPlayerEntityFeature.TURN_OFF | \
        MediaPlayerEntityFeature.SELECT_SOURCE | \
        MediaPlayerEntityFeature.VOLUME_STEP
    _attr_source_list = ['HDMI 1/ARC', 'HDMI 2', 'HDMI 3', 'HDMI 4', 'HDMI 1.2', 'HDMI 1.3', 'HDMI 1.4']
    _attr_unique_id = 'singleton'

    def __init__(self):
        self._attr_state = MediaPlayerState.OFF
        self.path = None
        self.fd = -1

    def open_fd(self):
        loop = asyncio.get_event_loop()
        if self.fd != -1:
            os.close(self.fd)
            loop.remove_reader(self.fd)
            self.path = None
            self.fd = -1

        for i in range(2):
            try:
                self.path = f'/dev/cec{i}'
                self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
                break
            except OSError:
                self.fd = -1
                pass

        if self.fd != -1:
            _LOGGER.info(f'opened {self.path} -> {self.fd}')

            cec_s_mode(self.fd, CEC_MODE_INITIATOR | CEC_MODE_FOLLOWER)

            laddr = get_laddr(self.fd)
            msg_buf = CecParsedMsg.build(laddr, 0,
                                         Cmd.CEC_MSG_GIVE_DEVICE_POWER_STATUS)
            CecMsg.transmit(self.fd, msg_buf, False)
            msg_buf = CecParsedMsg.build(laddr, 0,
                                         Cmd.CEC_MSG_REQUEST_ACTIVE_SOURCE)
            CecMsg.transmit(self.fd, msg_buf, False)
            msg_buf = CecParsedMsg.build(laddr, 0,
                                         Cmd.CEC_MSG_ROUTING_INFORMATION)
            CecMsg.transmit(self.fd, msg_buf, False)

            loop.add_reader(self.fd, self.read_ready)
            loop._selector._selector.modify(self.fd, select.EPOLLIN | select.EPOLLPRI)
        else:
            loop.call_later(1.0, self.open_fd)

    async def async_added_to_hass(self) -> None:
        self.open_fd()
        self.async_on_remove(
            async_track_time_interval(self.hass, self.request_power_state, timedelta(seconds=30))
        )

    def request_power_state(self, _: datetime | None = None) -> None:
        laddr = get_laddr(self.fd)
        msg_buf = CecParsedMsg.build(laddr, 0,
                                     Cmd.CEC_MSG_GIVE_DEVICE_POWER_STATUS)
        CecMsg.transmit(self.fd, msg_buf, False)

    def update_power_state(self, state: bool):
        if state:
            self._attr_state = MediaPlayerState.ON
            self.schedule_update_ha_state()
            _LOGGER.info('!!! TV ON !!!')
        else:
            self._attr_state = MediaPlayerState.OFF
            self.schedule_update_ha_state()
            _LOGGER.info('!!! TV OFF !!!')

    def update_source(self, source):
        self._attr_source = source
        self._attr_app_id = source
        self._attr_app_name = source
        self.schedule_update_ha_state()

    def process_event(self, event: CecEvent):
        _LOGGER.debug('event: %s', event)
        if event.event == CecEventType.CEC_EVENT_STATE_CHANGE and event.log_addr_mask != 0:
            laddr = get_laddr(self.fd)
            msg_buf = CecParsedMsg.build(laddr, 0,
                                         Cmd.CEC_MSG_GIVE_DEVICE_POWER_STATUS)
            CecMsg.transmit(self.fd, msg_buf, False)

    def process_msg(self, msg: CecMsg):
        _LOGGER.debug(msg)
        parsed = msg.parse()
        _LOGGER.debug(parsed)

        if parsed.initiator == 0:
            if parsed.cmd == Cmd.CEC_MSG_GIVE_DEVICE_POWER_STATUS:
                _LOGGER.debug('reporting power status')
                msg_buf = CecParsedMsg.build(parsed.destination, parsed.initiator,
                                             Cmd.CEC_MSG_REPORT_POWER_STATUS, PwrState.CEC_OP_POWER_STATUS_ON)
                CecMsg.transmit(self.fd, msg_buf, False)
            elif parsed.cmd == Cmd.CEC_MSG_REPORT_POWER_STATUS:
                pwr_state = PwrState(parsed.args[0])
                power_state = True if pwr_state == PwrState.CEC_OP_POWER_STATUS_ON else False
                self.update_power_state(power_state)
            elif parsed.cmd == Cmd.CEC_MSG_ACTIVE_SOURCE:
                self.update_source(None)
                _LOGGER.info('!!! SWITCH TO APPS !!!')
            elif parsed.cmd == Cmd.CEC_MSG_STANDBY:
                self.update_power_state(False)
        if parsed.initiator in (0, 5):
            if parsed.cmd == Cmd.CEC_MSG_ROUTING_CHANGE:
                sound_bar_index = parsed.args[2] & 0xf
                if sound_bar_index:
                    resolved_index = SOUND_BAR_INDEX_MAP.index(sound_bar_index)
                    source = self._attr_source_list[resolved_index + 4]
                else:
                    source = self._attr_source_list[(parsed.args[2] >> 4) - 1]
                if self._attr_source_list.index(source) != 0:
                    self.update_source(source)
                    _LOGGER.info(f'!!! SWITCH TO ANOTHER INPUT (%s.%s) !!!', parsed.args[2] >> 4, sound_bar_index)
            elif parsed.cmd == Cmd.CEC_MSG_SET_STREAM_PATH:
                sound_bar_index = parsed.args[0] & 0xf
                if sound_bar_index:
                    resolved_index = SOUND_BAR_INDEX_MAP.index(sound_bar_index)
                    source = self._attr_source_list[resolved_index + 4]
                else:
                    source = self._attr_source_list[(parsed.args[0] >> 4) - 1]
                self.update_source(source)
                _LOGGER.info(f'!!! SWITCH TO ME (%s.%s) !!!', parsed.args[0] >> 4, sound_bar_index)
        if parsed.initiator == 5:
            if parsed.cmd == Cmd.CEC_MSG_ROUTING_INFORMATION:
                sound_bar_index = parsed.args[0] & 0xf
                if sound_bar_index:
                    resolved_index = SOUND_BAR_INDEX_MAP.index(sound_bar_index)
                    source = self._attr_source_list[resolved_index + 4]
                    self.update_source(source)
                    _LOGGER.info(f'!!! SWITCH TO SOUND BAR INPUT (%s.%s) !!!', parsed.args[0] >> 4, sound_bar_index)

    def read_ready(self):
        try:
            event = CecEvent.deque(self.fd)
            while event is not None:
                self.process_event(event)
                event = CecEvent.deque(self.fd)

            msg = CecMsg.receive(self.fd)
            while msg is not None:
                self.process_msg(msg)
                msg = CecMsg.receive(self.fd)
        except OSError as e:
            self.open_fd()
            raise e

    def turn_on(self) -> None:
        laddr = get_laddr(self.fd)
        msg_buf = CecParsedMsg.build(laddr, 0,
                                     Cmd.CEC_MSG_IMAGE_VIEW_ON)
        CecMsg.transmit(self.fd, msg_buf, False)
        self.update_power_state(True)

    def turn_off(self) -> None:
        laddr = get_laddr(self.fd)
        msg_buf = CecParsedMsg.build(laddr, 15,
                                     Cmd.CEC_MSG_STANDBY)
        CecMsg.transmit(self.fd, msg_buf, False)
        self.update_power_state(False)

    def select_source(self, source: str) -> None:
        index = self._attr_source_list.index(source)

        # Perform this intricate sequence with a blocking file descriptor
        tmp_fd = os.open(self.path, os.O_RDWR)
        cec_s_mode(tmp_fd, CEC_MODE_INITIATOR)

        try:
            old_phys_addr = cec_g_phys_addr(tmp_fd)
            laddrs = CecLogAddrs.get(tmp_fd)

            try:
                clear_laddrs(tmp_fd)
                _LOGGER.debug(f'clear log_addr')
                if index >= 4:
                    sound_bar_index = SOUND_BAR_INDEX_MAP[index - 4]
                    phys_addr = (1 << 12) | (sound_bar_index << 8)
                else:
                    phys_addr = (index + 1) << 12
                cec_s_phys_addr(tmp_fd, phys_addr)
                _LOGGER.debug(f'phys_addr < {phys_addr_to_string(phys_addr)}')
                laddrs.set(tmp_fd)
                _LOGGER.debug(f'log_addr < {laddrs.log_addr[0]}')

                laddr = get_laddr(tmp_fd)
                _LOGGER.debug(f'log_addr > {laddr}')

                msg_buf = CecParsedMsg.build(laddr, 15,
                                             Cmd.CEC_MSG_ACTIVE_SOURCE, phys_addr >> 8, phys_addr & 0xff)
                CecMsg.transmit(tmp_fd, msg_buf, False)
                _LOGGER.debug(f'active_source < {phys_addr_to_string(phys_addr)}')

                self.update_source(self._attr_source_list[index])
            finally:
                clear_laddrs(tmp_fd)
                _LOGGER.debug(f'clear log_addr')
                cec_s_phys_addr(tmp_fd, old_phys_addr)
                _LOGGER.debug(f'phys_addr < {phys_addr_to_string(old_phys_addr)}')
                laddrs.set(tmp_fd)
                _LOGGER.debug(f'log_addr < {laddrs.log_addr[0]}')
        finally:
            os.close(tmp_fd)

    def send_ui_command(self, ui_command: UiCmd) -> None:
        laddr = get_laddr(self.fd)
        msg_buf = CecParsedMsg.build(laddr, 0,
                                     Cmd.CEC_MSG_USER_CONTROL_PRESSED,
                                     ui_command)
        CecMsg.transmit(self.fd, msg_buf, False)
        msg_buf = CecParsedMsg.build(laddr, 0,
                                     Cmd.CEC_MSG_USER_CONTROL_RELEASED)
        CecMsg.transmit(self.fd, msg_buf, False)

    def volume_up(self) -> None:
        self.send_ui_command(UiCmd.CEC_OP_UI_CMD_VOLUME_UP)

    def volume_down(self) -> None:
        self.send_ui_command(UiCmd.CEC_OP_UI_CMD_VOLUME_DOWN)

    async def async_press_button(self, button):
        command = UI_COMMAND_TABLE[button]
        _LOGGER.info("pressed button %s -> %s", button, command)
        self.send_ui_command(command)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    async_add_entities([HdmiCecKernelEntity()])

    platform = async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_PRESS_BUTTON, PRESS_BUTTON_SCHEMA, "async_press_button"
    )


