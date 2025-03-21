import os
import vt_api

fd = os.open('/dev/tty0', os.O_WRONLY)
try:
    state = vt_api.get_state(fd)
    print(f'{state.v_active}', flush=True)

    while True:
        event = vt_api.wait_event(fd, vt_api.VT_EVENT_SWITCH)
        print(f'{event.newev}', flush=True)
finally:
    os.close(fd)
