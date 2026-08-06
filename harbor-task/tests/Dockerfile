FROM alpine:3.20@sha256:c64c687cbea9300178b30c95835354e34c4e4febc4badfe27102879de0483b5e

RUN apk add --no-cache python3 dash

COPY test.sh /tests/test.sh
COPY test_behavior.py /tests/test_behavior.py

RUN chmod 0755 /tests/test.sh
