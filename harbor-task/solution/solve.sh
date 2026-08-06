#!/bin/sh
set -u

app_root=${TASK_APP_ROOT:-/app/backend}
launcher=$app_root/launch-worker.sh

cat >"$launcher" <<'EOF'
#!/bin/sh
set -u

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

child_pid=
signal_seen=

forward_signal() {
    sig=$1
    if [ -z "$signal_seen" ]; then
        signal_seen=$sig
    fi
    if [ -n "$child_pid" ]; then
        kill -"$signal_seen" "$child_pid" 2>/dev/null || true
    fi
}

trap 'forward_signal TERM' TERM
trap 'forward_signal INT' INT

"$@" >>"$log_file" 2>&1 &
child_pid=$!

# A signal can arrive between starting the child and assigning $!. If that
# happened, deliver the pending signal now.
if [ -n "$signal_seen" ]; then
    kill -"$signal_seen" "$child_pid" 2>/dev/null || true
fi

# A trapped signal can interrupt wait(1) before the child has been reaped.
# Retry while the child still has a waitable process entry so that its final
# status, rather than the shell's 128+signal status, is returned.
while :; do
    wait "$child_pid"
    status=$?
    if [ -n "$signal_seen" ] && [ "$status" -gt 128 ]; then
        if kill -0 "$child_pid" 2>/dev/null; then
            continue
        fi
    fi
    exit "$status"
done
EOF

chmod 0755 "$launcher"
