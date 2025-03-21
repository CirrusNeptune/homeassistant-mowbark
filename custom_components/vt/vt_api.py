import fcntl
import struct

VT_ACTIVATE = 0x5606
VT_WAITEVENT = 0x560E
VT_GETSTATE = 0x5603
VT_EVENT_SWITCH = 0x0001


class VtStat:
    def __init__(self, v_active, v_signal, v_state):
        self.v_active = v_active
        self.v_signal = v_signal
        self.v_state = v_state

    @staticmethod
    def from_buf(buf):
        return VtStat(*struct.unpack('HHH', buf[:6]))


def get_state(fd):
    buf = bytearray(6)
    fcntl.ioctl(fd, VT_GETSTATE, buf)
    return VtStat.from_buf(buf)


class VtEvent:
    def __init__(self, event, oldev, newev):
        self.event = event
        self.oldev = oldev
        self.newev = newev

    def to_bytes(self):
        return struct.pack('IIIIIII', self.event, self.oldev, self.newev, 0, 0, 0, 0)

    @staticmethod
    def from_buf(buf):
        return VtEvent(*struct.unpack('III', buf[:12]))


def wait_event(fd, event):
    buf = bytearray(VtEvent(event, 0, 0).to_bytes())
    fcntl.ioctl(fd, VT_WAITEVENT, buf)
    return VtEvent.from_buf(buf)


def activate(fd, idx):
    fcntl.ioctl(fd, VT_ACTIVATE, idx)

