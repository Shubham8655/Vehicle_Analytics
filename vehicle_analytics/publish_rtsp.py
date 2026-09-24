"""Loop an MP4 to MediaMTX and probe the RTSP endpoint using bundled FFmpeg."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg


def publish(source: str, url: str) -> None:
    video = Path(source).resolve()
    if not video.is_file():
        raise FileNotFoundError(f"Video file not found: {video}")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [ffmpeg, "-re", "-stream_loop", "-1", "-i", str(video), "-an", "-c:v", "libx264",
               "-preset", "ultrafast", "-tune", "zerolatency", "-pix_fmt", "yuv420p", "-f", "rtsp",
               "-rtsp_transport", "tcp", url]
    print(f"Publishing {video.name} to {url}. Press Ctrl+C to stop.", flush=True)
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("FFmpeg failed. Confirm MediaMTX is running and the RTSP publish URL is correct.") from exc


def probe(url: str) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp", "-i", url,
               "-frames:v", "1", "-f", "null", "-"]
    print(f"Checking {url} ...", flush=True)
    subprocess.run(command, check=True)
    print("RTSP stream is accessible and delivered a video frame.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["publish", "probe"])
    parser.add_argument("--source", default="traffic.mp4")
    parser.add_argument("--url", default="rtsp://127.0.0.1:8554/traffic")
    args = parser.parse_args()
    publish(args.source, args.url) if args.action == "publish" else probe(args.url)


if __name__ == "__main__":
    main()
