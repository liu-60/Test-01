FROM alpine:3.20@sha256:c64c687cbea9300178b30c95835354e34c4e4febc4badfe27102879de0483b5e

ARG SOURCE_REPO=https://github.com/liu-60/Test-01.git
ARG SOURCE_COMMIT=002e3231dff17f609093837a2f0d407d1a86ffc6

RUN sed -i 's#https://dl-cdn.alpinelinux.org/alpine#https://mirrors.aliyun.com/alpine#g' /etc/apk/repositories \
    && apk add --no-cache busybox git python3 dash \
    && git clone --depth 1 "$SOURCE_REPO" /tmp/source \
    && cd /tmp/source \
    && git fetch --depth 1 origin "$SOURCE_COMMIT" \
    && git checkout --detach "$SOURCE_COMMIT" \
    && mkdir -p /app \
    && cp -R project/backend /app/backend \
    && rm -rf /tmp/source /var/cache/apk/*

WORKDIR /app
CMD ["/bin/sh"]
