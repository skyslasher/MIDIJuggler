#!/bin/sh
set -eu

PLAYBACK="${WING_PLAYBACK:-wing_stereo3}"
CAPTURE="${G_AUDIO_CAPTURE:-plughw:CARD=g_audio,DEV=0}"
WAIT_SECONDS="${GADGET_WAIT_SECONDS:-90}"

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
