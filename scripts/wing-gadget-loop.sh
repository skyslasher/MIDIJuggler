#!/bin/sh
set -eu

# Use wing_stereo3 for playback (same path as speaker-test). Do not use alsoloop
# on dshare PCMs (double-open). Do not probe with --dump-hw-params.
PLAYBACK="${WING_PLAYBACK:-wing_stereo3}"
# Leave empty for the gadget native rate (matches: arecord -d 2 -f S16_LE /dev/null).
RATE="${GADGET_LOOP_RATE:-}"
WAIT_SECONDS="${GADGET_WAIT_SECONDS:-90}"

log() {
    printf 'wing-gadget-loop: %s\n' "$*" >&2
}

log "starting"

detect_capture() {
    if [ -n "${G_AUDIO_CAPTURE:-}" ]; then
        printf '%s\n' "$G_AUDIO_CAPTURE"
        return
    fi
    for card in UAC2Gadget UAC2_Gadget g_audio; do
        if arecord -l 2>/dev/null | grep -q "$card"; then
            printf '%s\n' "plughw:CARD=${card},DEV=0"
            return
        fi
    done
    printf '%s\n' "plughw:CARD=UAC2Gadget,DEV=0"
}

capture_listed() {
    case "$CAPTURE" in
        *CARD=UAC2Gadget,*)
            arecord -l 2>/dev/null | grep -q UAC2Gadget
            ;;
        *CARD=UAC2_Gadget,*)
            arecord -l 2>/dev/null | grep -q UAC2_Gadget
            ;;
        *CARD=g_audio,*)
            arecord -l 2>/dev/null | grep -q g_audio
            ;;
        *)
            false
            ;;
    esac
}

playback_ready() {
    aplay -L 2>/dev/null | grep -x "$PLAYBACK" >/dev/null
}

CAPTURE="$(detect_capture)"

if [ -n "$RATE" ]; then
    rate_msg="${RATE}Hz"
else
    rate_msg="native"
fi

log "capture device: $CAPTURE"
log "playback PCM: $PLAYBACK"
log "sample rate: $rate_msg"
log "waiting for listed devices (timeout ${WAIT_SECONDS}s)..."

elapsed=0
while [ "$elapsed" -lt "$WAIT_SECONDS" ]; do
    if capture_listed && playback_ready; then
        break
    fi
    if [ "$elapsed" -eq 0 ] || [ $((elapsed % 10)) -eq 0 ]; then
        if capture_listed; then
            capture_state=listed
        else
            capture_state=missing
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

if ! capture_listed; then
    log "gadget capture card not found in arecord -l for: $CAPTURE"
    arecord -l >&2 || true
    exit 1
fi

if ! playback_ready; then
    log "playback PCM not listed by aplay -L: $PLAYBACK"
    log "install configs/alsa/50-wing-usb-routing.conf into /etc/alsa/conf.d/"
    aplay -L >&2 || true
    exit 1
fi

if [ "${GADGET_PROBE_CAPTURE:-0}" = "1" ]; then
    log "probing capture (optional; set GADGET_PROBE_CAPTURE=0 to skip)"
    if ! arecord -D "$CAPTURE" -d 2 -f S16_LE /dev/null; then
        log "capture probe failed; stop other gadget users and retry:"
        log "  sudo systemctl stop wing-gadget-loop.service"
        log "  arecord -D $CAPTURE -d 2 -f S16_LE /dev/null"
        exit 1
    fi
fi

log "starting arecord | aplay ($CAPTURE -> $PLAYBACK @ $rate_msg)"
log "the USB host must send audio to the Pi gadget input"
log "pipeline runs until stopped (Ctrl+C or systemctl stop)"

if [ "${GADGET_LOOP_VERBOSE:-0}" = "1" ]; then
    ARECORD_VERBOSE=-v
    APLAY_VERBOSE=-v
else
    ARECORD_VERBOSE=
    APLAY_VERBOSE=
fi

if [ -n "$RATE" ]; then
    # shellcheck disable=SC2086
    arecord $ARECORD_VERBOSE -D "$CAPTURE" -f S16_LE -c 2 -r "$RATE" -t 0 - | \
        aplay $APLAY_VERBOSE -D "$PLAYBACK" -f S16_LE -c 2 -r "$RATE" -t 0 -
else
    # shellcheck disable=SC2086
    arecord $ARECORD_VERBOSE -D "$CAPTURE" -f S16_LE -c 2 -t 0 - | \
        aplay $APLAY_VERBOSE -D "$PLAYBACK" -f S16_LE -c 2 -t 0 -
fi
