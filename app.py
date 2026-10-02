#!/usr/bin/env python3
"""
ClipForge Backend - Full power yt-dlp engine
Designed to run in Docker on free cloud platforms.
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import subprocess
import threading
import time
import os
from pathlib import Path
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Allow frontend on Cloudflare Pages to talk to this backend

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

RATE_LIMIT_SECONDS = 15
MAX_FILE_AGE_HOURS = 6
download_log = {}


def get_format_args(fmt: str) -> list:
    if fmt == "audio":
        return ["-f", "ba/b", "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0"]
    elif fmt == "1080":
        return ["-f", "bv*[height<=1080]+ba/b", "--merge-output-format", "mp4"]
    elif fmt == "720":
        return ["-f", "bv*[height<=720]+ba/b", "--merge-output-format", "mp4"]
    else:
        return ["-f", "bv*[height<=2160]+ba/b", "--merge-output-format", "mp4"]


def cleanup_old_files():
    now = time.time()
    max_age = MAX_FILE_AGE_HOURS * 3600
    for f in DOWNLOAD_DIR.iterdir():
        if f.is_file() and (now - f.stat().st_mtime) > max_age:
            try:
                f.unlink()
            except OSError:
                pass


@app.route("/")
def health():
    return jsonify({
        "status": "online",
        "service": "ClipForge Backend",
        "version": "1.0",
        "engine": "yt-dlp + ffmpeg + aria2"
    })


@app.route("/api/download", methods=["POST"])
def download():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    fmt = data.get("format", "best")

    if not url:
        return jsonify(ok=False, message="No URL provided")

    # Rate limit
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip:
        ip = ip.split(",")[0].strip()
    now = time.time()
    if ip in download_log and (now - download_log[ip]) < RATE_LIMIT_SECONDS:
        return jsonify(ok=False, message=f"Please wait {RATE_LIMIT_SECONDS} seconds")
    download_log[ip] = now

    cleanup_old_files()

    # Unique filename
    timestamp = int(time.time())
    outtmpl = str(DOWNLOAD_DIR / f"%(title).60B [{timestamp}].%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-o", outtmpl,
        "--embed-metadata",
        "--embed-thumbnail",
        "--embed-chapters",
        "--no-mtime",
        "--retries", "8",
        "--fragment-retries", "8",
        "--downloader", "aria2c",
        "--downloader-args", "aria2c:-x 16 -s 16 -k 1M --summary-interval=0",
    ] + get_format_args(fmt) + [url]

    def run_download():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            # Optional: log result.stdout / result.stderr if needed
        except Exception as e:
            print(f"Download error: {e}")

    threading.Thread(target=run_download, daemon=True).start()

    return jsonify(
        ok=True,
        message="Download started on the server. High quality file is being processed."
    )


@app.route("/files/<path:filename>")
def serve_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


@app.route("/api/list")
def list_files():
    """Simple list of recent files (for future UI improvement)"""
    files = []
    for f in sorted(DOWNLOAD_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
        if f.is_file():
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "url": f"/files/{f.name}"
            })
    return jsonify(files)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"ClipForge Backend running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
