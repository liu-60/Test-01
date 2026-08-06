FROM alpine:3.20

ARG SOURCE_REPO=https://github.com/liu-60/Test-01.git
ARG SOURCE_COMMIT=22fc6df5550413e9cb07a20dc47606e8a95d7c71

RUN apk add --no-cache busybox git python3 dash \
    && git clone --depth 1 "$SOURCE_REPO" /tmp/source \
    && cd /tmp/source \
    && git fetch --depth 1 origin "$SOURCE_COMMIT" \
    && git checkout --detach "$SOURCE_COMMIT" \
    && mkdir -p /app \
    && cp -R project/backend /app/backend \
    && rm -rf /tmp/source /var/cache/apk/*

WORKDIR /app
CMD ["/bin/sh"]
