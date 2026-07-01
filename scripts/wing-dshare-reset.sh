#!/bin/sh
set -eu

# Reset stale Wing USB dshare state when wing_stereo* fails with
# "destination channel specified in bindings is already used".
#
# Usage:
#   sudo ./scripts/wing-dshare-reset.sh
#   sudo ./scripts/wing-dshare-reset.sh --test

WING_IPC_KEYS="${WING_IPC_KEYS:-5678293 426110}"
TEST_PCM="${WING_TEST_PCM:-wing_stereo1}"
TEST_WAV="${WING_TEST_WAV:-/etc/midijuggler/click1.wav}"

log() {
    printf 'wing-dshare-reset: %s\n' "$*" >&2
}

stop_services() {
    if command -v systemctl >/dev/null 2>&1; then
        systemctl stop midijuggler shairport-sync wing-gadget-loop 2>/dev/null || true
    fi
}

kill_audio_clients() {
    pkill -x alsaloop 2>/dev/null || true
    pkill -f 'arecord.*aplay' 2>/dev/null || true
    pkill -x speaker-test 2>/dev/null || true
}

clear_alsa_ipc() {
    for key in $WING_IPC_KEYS; do
        if ipcrm -M "$key" 2>/dev/null; then
            log "removed shared memory segment for ipc_key $key"
        fi
    done
}

list_wing_pcms() {
    if command -v aplay >/dev/null 2>&1; then
        aplay -L 2>/dev/null | grep -E '^wing_stereo[123]$' || true
    fi
}

test_playback() {
    if ! command -v aplay >/dev/null 2>&1; then
        log "aplay not found; skipping playback test"
        return 0
    fi
    if [ ! -f "$TEST_WAV" ]; then
        log "test WAV missing: $TEST_WAV"
        return 1
    fi
    log "testing $TEST_PCM with $TEST_WAV"
    aplay -D "$TEST_PCM" "$TEST_WAV"
}

RUN_TEST=0
for arg in "$@"; do
    case "$arg" in
        --test) RUN_TEST=1 ;;
        -h|--help)
            echo "Usage: sudo $0 [--test]"
            exit 0
            ;;
        *)
            log "unknown argument: $arg"
            exit 2
            ;;
    esac
done

log "stopping MIDIJuggler, Shairport-Sync and wing-gadget-loop"
stop_services
sleep 1
kill_audio_clients
sleep 1
clear_alsa_ipc

log "available Wing PCMs:"
list_wing_pcms

if [ "$RUN_TEST" -eq 1 ]; then
    test_playback
fi

log "done. Restart services when ready:"
log "  sudo systemctl start wing-gadget-loop shairport-sync midijuggler"
