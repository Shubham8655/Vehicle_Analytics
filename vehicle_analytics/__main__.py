"""Run the Python web dashboard and live pipeline."""

import uvicorn

from .config import settings
from .publish_rtsp import publish

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(prog="vehicle-analytics")
    parser.add_argument("command", nargs="?", choices=["serve", "publish-rtsp", "probe-rtsp"], default="serve")
    parser.add_argument("--source", default=settings.video_source)
    parser.add_argument("--url", default="rtsp://127.0.0.1:8554/traffic")
    args = parser.parse_args()
    if args.command == "serve":
        uvicorn.run("vehicle_analytics.web:app", host=settings.host, port=settings.port, reload=False)
    elif args.command == "publish-rtsp":
        publish(args.source, args.url)
    else:
        from .publish_rtsp import probe
        probe(args.url)
