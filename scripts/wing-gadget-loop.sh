#!/bin/sh
set -eu

PLAYBACK="${WING_PLAYBACK:-wing_stereo3}"
WAIT_SECONDS="${GADGET_WAIT_SECONDS:-90}"

log() {
    printf 'wing-gadget-loop: %s\n' "$*" >&2
}

detect_capture() {
    if [ -n "${G_AUDIO_CAPTURE:-}" ]; then
        printf '%s\n' "$G_AUDIO_CAPTURE"
        return
    fi
    for card in UAC2Gadget UAC2_Gadget g_audio; do
        device="plughw:CARD=${card},DEV=0"
        if arecord -D "$device" --dump-hw-params >/dev/null 2>&1; then
            printf '%s\n' "$device"
            return
        fi
    done
    printf '%s\n' "plughw:CARD=UAC2Gadget,DEV=0"
}

CAPTURE="$(detect_capture)"

capture_ready() {
    arecord -D "$CAPTURE" --dump-hw-params >/dev/null 2>&1
}

playback_ready() {
    aplay -D "$PLAYBACK" --dump-hw-params >/dev/null 2>&1
}

log "capture device: $CAPTURE"
log "playback PCM: $PLAYBACK"
log "waiting for both devices (timeout ${WAIT_SECONDS}s)..."

elapsed=0
while [ "$elapsed" -lt "$WAIT_SECONDS" ]; do
    if capture_ready && playback_ready; then
        break
    fi
    if [ "$elapsed" -eq 0 ] || [ $((elapsed % 10)) -eq 0 ]; then
        if capture_ready; then
            capture_state=ok
        else
            capture_state=waiting
        fi
        if playback_ready; then
            playback_state=ok
        else
            playback_state=waiting
        fi
        log "status capture=${capture_state} playback=${playback_state} (${elapsed}s)"
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

if ! capture_ready; then
    log "capture device not ready: $CAPTURE"
    arecord -l >&2 || true
    exit 1
fi

if ! playback_ready; then
    log "playback PCM not ready: $PLAYBACK"
    log "try: aplay -D $PLAYBACK --dump-hw-params"
    aplay -L >&2 || true
    exit 1
fi

log "starting alsaloop ($CAPTURE -> $PLAYBACK)"
log "alsaloop runs silently while looping; stop with Ctrl+C or systemctl stop"

if [ "${GADGET_LOOP_VERBOSE:-0}" = "1" ]; then
    set -- alsaloop -v -C "$CAPTURE" -P "$PLAYBACK" -f S16_LE -t 5000 -b
else
    set -- alsaloop -C "$CAPTURE" -P "$PLAYBACK" -f S16_LE -t 5000 -b
fi
exec "$@"
