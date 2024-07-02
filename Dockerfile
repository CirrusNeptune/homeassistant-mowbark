FROM ghcr.io/home-assistant/home-assistant:latest

RUN set -x \
&& cd / \
&& apk add --no-cache --virtual .build-deps make gcc musl-dev linux-headers \
&& git clone -b v2.14.0.0 https://github.com/skarnet/skalibs.git \
&& cd skalibs \
&& ./configure \
&& make install \
&& cd / \
&& git clone -b v2.9.4.0 https://github.com/skarnet/execline.git \
&& cd execline \
&& ./configure \
&& make install \
&& cd / \
&& git clone -b prctl https://github.com/CirrusNeptune/s6-overlay-helpers.git \
&& cd s6-overlay-helpers \
&& ./configure \
&& make \
&& tools/install.sh -D -m 755 s6-overlay-suexec /package/admin/s6-overlay-helpers-0.1.0.2/command/s6-overlay-suexec \
&& cd / \
&& apk del .build-deps \
&& rm -rf skalibs \
&& rm -rf execline \
&& rm -rf s6-overlay-helpers \
&& rm -rf /usr/src/*

RUN pip3 install lirc
RUN git clone -b ver4 https://github.com/CirrusNeptune/flux_led.git && pip install ./flux_led

