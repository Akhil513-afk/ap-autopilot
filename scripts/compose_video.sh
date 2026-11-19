#!/usr/bin/env bash
# Put the silent demo and your webcam recording side by side, with your voice, as a 1920x1080 MP4.
#
#   scripts/compose_video.sh <webcam.mov|mp4> [skip_seconds] [voice.m4a]
#
#   webcam.mov    your face-cam recording (its audio is used as the voice-over unless voice.m4a is given)
#   skip_seconds  seconds to cut from the START of the webcam clip so it lines up with the demo (default 0)
#                 e.g. you hit record, then started the demo 2.4 s later -> 2.4
#   voice.m4a     optional separate voice recording (same skip is applied)
#
# Output: demo/final-demo.mp4  (demo 1440x810 on the left, webcam 480x810 on the right)
set -euo pipefail
cd "$(dirname "$0")/.."

CAM="${1:?usage: scripts/compose_video.sh <webcam file> [skip_seconds] [voice file]}"
SKIP="${2:-0}"
VOICE="${3:-}"
DEMO="demo/ap-autopilot-demo.mp4"
OUT="demo/final-demo.mp4"

FF="$(command -v ffmpeg || true)"
[ -z "$FF" ] && FF="/opt/anaconda3/lib/python3.13/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v9.0"
[ -x "$FF" ] || { echo "ffmpeg not found - install it (brew install ffmpeg) or edit FF in this script"; exit 1; }
[ -f "$DEMO" ] || { echo "missing $DEMO - run scripts/record_demo.py first"; exit 1; }

# "ffmpeg -i" with no output exits non-zero by design; we only want the Duration line it prints.
DUR="$({ "$FF" -i "$DEMO" 2>&1 || true; } | sed -n 's/.*Duration: \([0-9:.]*\).*/\1/p' | awk -F: '{print $1*3600+$2*60+$3}')"

FILTER="[0:v]scale=1440:810,setsar=1[d];\
[1:v]scale=-2:810,crop=480:810,setsar=1[c];\
color=c=0x0b1220:s=1920x1080:r=30:d=${DUR}[bg];\
[bg][d]overlay=0:135:shortest=1[t];\
[t][c]overlay=1440:135,format=yuv420p[v]"

if [ -n "$VOICE" ]; then
  "$FF" -y -loglevel error -i "$DEMO" -ss "$SKIP" -i "$CAM" -ss "$SKIP" -i "$VOICE" \
    -filter_complex "$FILTER" -map "[v]" -map 2:a -t "$DUR" \
    -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 160k -movflags +faststart "$OUT"
else
  "$FF" -y -loglevel error -i "$DEMO" -ss "$SKIP" -i "$CAM" \
    -filter_complex "$FILTER" -map "[v]" -map 1:a -t "$DUR" \
    -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 160k -movflags +faststart "$OUT"
fi
echo "wrote $OUT (${DUR}s)"
