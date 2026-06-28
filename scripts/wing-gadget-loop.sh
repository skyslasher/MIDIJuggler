#!/bin/sh
set -eu

PLAYBACK="${WING_PLAYBACK:-wing_stereo3}"
WAIT_SECONDS="${GADGET_WAIT_SECONDS:-90}"

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
    aplay -L 2>/dev/null | grep -x "$PLAYBACK" >/dev/null
}

elapsed=0
while [ "$elapsed" -lt "$WAIT_SECONDS" ]; do
    if capture_ready && playback_ready; then
        break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

if ! capture_ready; then
    echo "wing-gadget-loop: capture device not ready: $CAPTURE" >&2
    arecord -l >&2 || true
    exit 1
fi

if ! playback_ready; then
    echo "wing-gadget-loop: playback PCM not found: $PLAYBACK" >&2
    aplay -L >&2 || true
    exit 1
fi

echo "wing-gadget-loop: looping $CAPTURE -> $PLAYBACK" >&2
exec alsaloop -C "$CAPTURE" -P "$PLAYBACK" -f S16_LE -t 5000 -b
