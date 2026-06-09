#!/usr/bin/env python3.11
"""Add a Chinese voiceover + sidecar captions to the recorded demo.

The narration captions are already burned into the recording (record_demo.py
renders an on-page subtitle overlay), so this script only:
  * writes captions.srt                  — sidecar caption track (from timeline.json)
  * builds a macOS TTS voiceover (Tingting, zh_CN) placed at each caption's time
  * transcodes the captioned webm -> echo_translate_demo.mp4 (no audio)
  * muxes the voiceover -> echo_translate_demo_narrated.mp4
  * builds echo_translate_demo.gif       — captioned, looping, for README preview

Pure ffmpeg + macOS `say`. No paid services, no text filters required.
"""
from __future__ import annotations

import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
VIDEO = os.path.join(OUT, "echo_translate_demo.webm")
TL = os.path.join(OUT, "timeline.json")
VOICE = os.environ.get("TTS_VOICE", "Tingting")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=OUT, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def probe_duration(path: str) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path])
    return float(out.strip())


def srt_ts(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    ms = int(round((s - int(s)) * 1000))
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"


def main() -> None:
    timeline = json.load(open(TL, encoding="utf-8"))
    duration = probe_duration(VIDEO)

    # 1) captions.srt sidecar
    with open(os.path.join(OUT, "captions.srt"), "w", encoding="utf-8") as f:
        for i, item in enumerate(timeline):
            start = item["t"]
            end = timeline[i + 1]["t"] - 0.08 if i + 1 < len(timeline) else duration
            f.write(f"{i + 1}\n{srt_ts(start)} --> {srt_ts(max(end, start + 0.6))}\n"
                    f"{item['caption']}\n\n")
    print("✅ captions.srt")

    # 2) TTS voiceover clips (macOS `say` -> wav)
    wavs = []
    for i, item in enumerate(timeline):
        aiff, wav = os.path.join(OUT, f"vo_{i}.aiff"), os.path.join(OUT, f"vo_{i}.wav")
        subprocess.run(["say", "-v", VOICE, "-o", aiff, item["caption"]], check=True)
        run(["ffmpeg", "-y", "-i", aiff, "-ar", "44100", "-ac", "2", wav])
        os.remove(aiff)
        wavs.append((item["t"], wav))
    print(f"✅ {len(wavs)} voiceover clips ({VOICE})")

    # 3) plain mp4 (captions already baked into the recording)
    run(["ffmpeg", "-y", "-i", "echo_translate_demo.webm",
         "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-crf", "24",
         "echo_translate_demo.mp4"])
    print("✅ echo_translate_demo.mp4")

    # 4) narrated mp4 = mp4 + voiceover placed at each timestamp
    inputs = ["-i", "echo_translate_demo.mp4"]
    for _, wav in wavs:
        inputs += ["-i", os.path.basename(wav)]
    parts = [f"[{i}:a]adelay={int(t * 1000)}:all=1[a{i}]"
             for i, (t, _) in enumerate(wavs, start=1)]
    parts.append("".join(f"[a{i}]" for i in range(1, len(wavs) + 1))
                 + f"amix=inputs={len(wavs)}:normalize=0:dropout_transition=0[a]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(parts),
         "-map", "0:v", "-map", "[a]", "-t", f"{duration:.2f}",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
         "echo_translate_demo_narrated.mp4"])
    print("✅ echo_translate_demo_narrated.mp4 (voiceover + baked captions)")

    # 5) captioned GIF for README (two-pass palette)
    vf = "fps=11,scale=760:-1:flags=lanczos"
    run(["ffmpeg", "-y", "-i", "echo_translate_demo.webm",
         "-vf", vf + ",palettegen=stats_mode=diff", "pal.png"])
    run(["ffmpeg", "-y", "-i", "echo_translate_demo.webm", "-i", "pal.png",
         "-lavfi", vf + "[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
         "echo_translate_demo.gif"])
    print("✅ echo_translate_demo.gif")

    for _, wav in wavs:
        os.remove(wav)
    for f in ("pal.png", "echo_translate_demo.webm"):
        p = os.path.join(OUT, f)
        if os.path.exists(p):
            os.remove(p)


if __name__ == "__main__":
    main()
