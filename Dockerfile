FROM ghcr.io/home-assistant/home-assistant:latest
RUN pip3 install lirc
RUN git clone -b ver4 https://github.com/CirrusNeptune/flux_led.git & pip install ./flux_led

