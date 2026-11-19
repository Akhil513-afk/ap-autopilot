"""Align the synced screen recording to the narration, scene by scene, and overlay the narrator's camera.

    .venv/bin/python scripts/sync_video.py /path/to/narration.mp4 [out.mp4]

For every scene, the recorded span [mark_i, mark_i+1) is retimed to the narration span
[target_i, target_i+1): slowed by at most MAX_SLOW and then held on its last frame, or sped up if the
recording ran long. The narrator's video (with its audio) sits bottom-left with a border, like a
picture-in-picture webcam.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
FFMPEG = shutil.which("ffmpeg") or "/opt/anaconda3/lib/python3.13/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v9.0"
MAX_SLOW = 1.3
OUT_W, OUT_H, FPS = 1920, 1080, 30
# Circular camera bubble, bottom-right.
CAM_D, RING, MARGIN = 232, 5, 28          # diameter (px), ring width, distance from the frame edge
RING_RGB = (34, 197, 94)                  # green ring
# Square crop of the portrait camera around the face: (crop size as a fraction of width, top offset fraction of height)
FACE_TOP = 0.07


def main():
    narration = Path(sys.argv[1]).expanduser()
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEMO / "final-demo.mp4"
    tl = json.loads((DEMO / "timeline_synced.json").read_text())
    targets = json.loads((DEMO / "narration_targets.json").read_text())
    marks = {s["key"]: s["t"] for s in tl["scenes"]}
    order = [k for k in targets if k in marks]          # scene order as narrated
    total = targets["end"]

    parts, plan = [], []
    for i, key in enumerate(order[:-1]):
        nxt = order[i + 1]
        src_a = marks[key]
        src_b = marks[nxt] if nxt != "end" else min(tl["duration_s"], marks["end"] + 0.9)
        dst = targets[nxt] - targets[key]
        src = max(0.1, src_b - src_a)
        k = dst / src
        if k > MAX_SLOW:
            factor, pad = MAX_SLOW, dst - src * MAX_SLOW
        else:
            factor, pad = k, 0.0
        plan.append((key, src, dst, factor, pad))
        chain = f"[0:v]trim=start={src_a:.3f}:end={src_b:.3f},setpts=(PTS-STARTPTS)*{factor:.5f},fps={FPS},crop=1600:900:0:0,scale={OUT_W}:{OUT_H}:flags=lanczos"
        if pad > 0.02:
            chain += f",tpad=stop_mode=clone:stop_duration={pad:.3f}"
        parts.append(chain + f"[s{i}]")
    n = len(parts)
    graph = ";".join(parts)
    graph += ";" + "".join(f"[s{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,trim=duration={total:.3f},setpts=PTS-STARTPTS[scr]"
    r_out, r_in, c = CAM_D / 2, CAM_D / 2 - RING, CAM_D / 2 - 0.5
    d = f"hypot(X-{c},Y-{c})"
    ring = lambda ch, v: f"if(gt({d},{r_in}),{v},{ch}(X,Y))"  # noqa: E731
    graph += (f";[1:v]fps={FPS},crop=iw:iw:0:ih*{FACE_TOP},scale={CAM_D}:{CAM_D},format=rgba,"
              f"geq=r='{ring('r', RING_RGB[0])}':g='{ring('g', RING_RGB[1])}':b='{ring('b', RING_RGB[2])}'"
              f":a='if(gt({d},{r_out}),0,255)'[cam]")
    graph += f";[scr][cam]overlay=x=W-w-{MARGIN}:y=H-h-{MARGIN}:eof_action=pass,format=yuv420p[v]"

    for key, src, dst, factor, pad in plan:
        note = f"x{factor:.2f}" + (f" + hold {pad:.1f}s" if pad > 0.02 else "")
        print(f"  {key:16} recorded {src:5.1f}s -> narration {dst:5.1f}s  ({note})")

    cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", tl["video"], "-i", str(narration), "-filter_complex", graph,
           "-map", "[v]", "-map", "1:a", "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
