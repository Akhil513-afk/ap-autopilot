# Adding your voice and face to the demo

**Files in this folder**

| File | What it is |
|---|---|
| `ap-autopilot-demo.mp4` | The silent screen demo: 4:51, 1600×900. |
| `NARRATION_SCRIPT.md` | What to say, with a timestamp for every line. |
| `narration.srt` | The same lines as subtitles, used as a teleprompter. |

Pick one of the two options below. Both give you the screen on the left and your face on the right.

---

## Option A: Loom (easiest, about 10 minutes)

The brief accepts Loom.

1. Install Loom and choose **Screen + Cam**. Set the camera bubble to the **right side** of the screen.
2. Open `ap-autopilot-demo.mp4` in **IINA** or **VLC**, set it to full screen, and mute the player.
3. Load `narration.srt` as subtitles (VLC: *Subtitle → Add Subtitle File*; IINA: drag the file onto the player). Your lines now appear on screen at the right moment, like a teleprompter.
4. Start Loom, then press play on the video and read along.
5. Trim the first and last seconds in Loom, and copy the share link. **That link is deliverable #2.**

## Option B: a clean side-by-side MP4 (more polished)

1. **Record yourself.**
   - Open QuickTime Player, choose *File → New Movie Recording*, and pick your camera and microphone from the arrow next to the record button.
   - Put the QuickTime window off to one side, and play `ap-autopilot-demo.mp4` (muted, with `narration.srt` loaded) in IINA or VLC on the main screen.
2. **Sync it.**
   - Press record in QuickTime first, then **clap once at the exact moment you press play** on the demo.
   - Read the script, then stop recording when the demo ends.
3. **Find the clap.** Open your recording and note the second where the clap happens (for example `3.2`).
4. **Compose.** From the `invoice-ap` folder, run:
   ```bash
   scripts/compose_video.sh ~/Movies/your-recording.mov 3.2
   ```
   This writes `demo/final-demo.mp4`: 1920×1080, the demo on the left (1440×810), your camera on the right (480×810), and your voice.
   - If your voice is in a separate file: `scripts/compose_video.sh cam.mov 3.2 voice.m4a`.
5. Upload `final-demo.mp4` (Loom upload, YouTube *unlisted*, or Google Drive) and share the link.

---

## Tips
- **Do a practice read first.** Every line fits its scene at a relaxed pace, and the table in `NARRATION_SCRIPT.md` shows each line's word count and how many seconds you have.
- **If you stumble, keep going.** The scene captions and the cursor carry the story, so a missed word won't matter.
- **Replace `[your name]`** in the first line.
- **Re-recording the screen video:** if you change the app, the recording can be redone automatically. Start the app with `./run.sh`, then run:
  ```bash
  .venv/bin/python scripts/record_demo.py
  ```
  Then run this to regenerate `NARRATION_SCRIPT.md` and `narration.srt` with new timestamps:
  ```bash
  .venv/bin/python scripts/make_narration.py
  ```
  A raw recording may come out slightly over 5:00. The final 4:51 video was the raw recording sped up by 5%; ask if you need that step again.
