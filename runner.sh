#!/bin/bash

cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

log() { echo "[runner] $*"; }

# fail fast with a clear message instead of a restart loop
if [ ! -f src/setting/.env ]; then
    log "Missing src/setting/.env - copy src/setting/sample.env and fill it in."
    exit 1
fi
if [ ! -x ./.venv/bin/python3 ]; then
    log "Missing .venv - run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

export PYTHONPATH="$(pwd)"
source ./.venv/bin/activate

# Seconds the python processes get to shut down after the first signal
# before they are killed. Override with: GRACE_SECONDS=30 ./runner.sh
GRACE_SECONDS="${GRACE_SECONDS:-15}"

PIDS=()
SIGNAL_COUNT=0
FIRST_SIGNAL="INT"
SHUTTING_DOWN=0
ESCALATED=0
TRIGGERED=0
TRIGGER_CODE=0
FIRST_NONZERO=0

is_running() { kill -0 "$1" 2>/dev/null; }

signal_children() {
    local sig="$1" pid
    for pid in "${PIDS[@]}"; do
        if is_running "$pid"; then
            kill -s "$sig" "$pid" 2>/dev/null
        fi
    done
}

# First signal: ask the children to stop and start the grace timer.
# Second signal (or grace period over): kill them.
on_signal() {
    SIGNAL_COUNT=$((SIGNAL_COUNT + 1))
    if [ "$SIGNAL_COUNT" -eq 1 ]; then
        FIRST_SIGNAL="$1"
        SHUTTING_DOWN=1
        if [ "$1" = "TERM" ]; then
            log "Termination requested - asking python processes to stop."
            signal_children TERM
        else
            log "Interrupted (Ctrl+C) - waiting for python processes to stop."
            log "Ctrl+C again kills them immediately."
        fi
    else
        log "Second signal - killing python processes now."
        signal_children KILL
        ESCALATED=1
    fi
}
trap 'on_signal INT' INT
trap 'on_signal TERM' TERM

log "Starting python processes."
python3 src/main.py &
PIDS+=($!)
python3 send_db.py &
PIDS+=($!)

waited=0
while :; do
    running=0
    dead=()
    for pid in "${PIDS[@]}"; do
        if is_running "$pid"; then
            running=$((running + 1))
        else
            dead+=("$pid")
        fi
    done

    if [ "$running" -eq 0 ]; then
        break
    fi

    if [ "$SHUTTING_DOWN" -eq 0 ] && [ "${#dead[@]}" -gt 0 ]; then
        for pid in "${dead[@]}"; do
            wait "$pid" 2>/dev/null
            code=$?
            if [ "$code" -ne 0 ] && [ "$TRIGGERED" -eq 0 ]; then
                TRIGGER_CODE="$code"
            fi
        done
        TRIGGERED=1
        SHUTTING_DOWN=1
        log "A python process exited - stopping the others."
        signal_children INT
    fi

    if [ "$SHUTTING_DOWN" -eq 1 ] && [ "$ESCALATED" -eq 0 ]; then
        waited=$((waited + 1))
        if [ "$waited" -ge "$GRACE_SECONDS" ]; then
            log "Grace period of ${GRACE_SECONDS}s over - killing python processes."
            signal_children KILL
            ESCALATED=1
        fi
    fi

    sleep 1
done

for pid in "${PIDS[@]}"; do
    wait "$pid" 2>/dev/null
    code=$?
    if [ "$code" -ne 0 ] && [ "$FIRST_NONZERO" -eq 0 ]; then
        FIRST_NONZERO="$code"
    fi
done

if [ "$SIGNAL_COUNT" -gt 0 ]; then
    if [ "$FIRST_SIGNAL" = "TERM" ]; then
        exit 143
    fi
    exit 130
fi

if [ "$TRIGGERED" -eq 1 ]; then
    FINAL="$TRIGGER_CODE"
else
    FINAL="$FIRST_NONZERO"
fi
if [ "$FINAL" -eq 0 ]; then
    FINAL=1
fi
exit "$FINAL"
