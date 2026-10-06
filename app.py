#!/usr/bin/env python3
"""
ClipForge - High Quality Fast Extractor (y2mate-style competitor)
Optimized for speed + best quality options.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import json
import time
import os
from pathlib import Path

app = Flask(__name__)
CORS(app)

@app.route("/")
def health():
    return jsonify({
        "status": "online",
        "service": "ClipForge",
        "mode": "fast-extract + high-quality"
    })


@app.route("/api/extract", methods=["POST"])
def extract():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify(ok=False, message="No URL provided")

    try:
        # Fast extraction of available formats (no full download)
        cmd = [
            "yt-dlp",
            "--no-download",
            "--dump-json",
            "--no-warnings",
            "--no-check-certificates",
            url
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=45
        )

        if result.returncode != 0:
            return jsonify(ok=False, message="Could not extract video info. Link may be invalid or protected.")

        info = json.loads(result.stdout)

        title = info.get("title", "Unknown")
        thumbnail = info.get("thumbnail")
        duration = info.get("duration")

        formats = []

        # Collect high quality video+audio formats
        for f in info.get("formats", []):
            if f.get("vcodec") != "none" and f.get("acodec") != "none":
                height = f.get("height") or 0
                if height >= 720:
                    formats.append({
                        "format_id": f["format_id"],
                        "ext": f.get("ext", "mp4"),
                        "resolution": f.get("resolution") or f"{height}p",
                        "height": height,
                        "filesize": f.get("filesize") or f.get("filesize_approx"),
                        "note": f.get("format_note", ""),
                        "url": f.get("url")
                    })

        # Best audio only
        best_audio = None
        for f in info.get("formats", []):
            if f.get("vcodec") == "none" and f.get("acodec") != "none":
                abr = f.get("abr") or 0
                if best_audio is None or abr > (best_audio.get("abr") or 0):
                    best_audio = {
                        "format_id": f["format_id"],
                        "ext": f.get("ext", "m4a"),
                        "abr": abr,
                        "filesize": f.get("filesize") or f.get("filesize_approx"),
                        "url": f.get("url")
                    }

        # Sort video formats by quality
        formats = sorted(formats, key=lambda x: x.get("height", 0), reverse=True)

        # Keep only unique good ones
        seen = set()
        clean_formats = []
        for f in formats:
            key = f["height"]
            if key not in seen and f.get("url"):
                seen.add(key)
                clean_formats.append(f)

        return jsonify({
            "ok": True,
            "title": title,
            "thumbnail": thumbnail,
            "duration": duration,
            "formats": clean_formats[:6],  # top qualities
            "audio": best_audio
        })

    except subprocess.TimeoutExpired:
        return jsonify(ok=False, message="Extraction timed out. Try again.")
    except Exception as e:
        return jsonify(ok=False, message=f"Error: {str(e)[:120]}")


@app.route("/api/download", methods=["POST"])
def download_proxy():
    """Optional: server-side download if direct link is blocked"""
    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url")
    format_id = data.get("format_id")

    if not url:
        return jsonify(ok=False, message="Missing URL")

    # For now just return the direct link (fastest)
    return jsonify({
        "ok": True,
        "message": "Use the direct link provided",
        "direct": True
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"ClipForge running on port {port}")
    app.run(host="0.0.0.0", port=port)
