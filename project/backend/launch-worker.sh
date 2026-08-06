#!/bin/sh
set -eu

usage() {
    echo "usage: $0 [--log LOG_FILE] -- COMMAND [ARG...]" >&2
}

log_file=/tmp/backend-worker.log
if [ "$#" -gt 0 ] && [ "$1" = "--log" ]; then
    if [ "$#" -lt 2 ]; then
        usage
        exit 64
    fi
    log_file=$2
    shift 2
fi

if [ "$#" -eq 0 ] || [ "$1" != "--" ]; then
    usage
    exit 64
fi
shift

if [ "$#" -eq 0 ]; then
    usage
    exit 64
fi

# This is deliberately written as a Bash-style command array even though the
# entrypoint is declared as /bin/sh. It also exits on the first interrupted
# wait, losing the worker's final status after signal forwarding.
command=( "$@" )
child_pid=

forward_signal() {
    kill -TERM "$child_pid" 2>/dev/null || true
}

trap forward_signal TERM INT

"${command[@]}" >>"$log_file" 2>&1 &
child_pid=$!
wait "$child_pid"
exit "$?"
