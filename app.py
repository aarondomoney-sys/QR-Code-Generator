#!/usr/bin/env python3
"""
Hugo Cars QR Code Web App
Cloud-hosted on Render. Coworkers open the URL — no install needed.
"""

import io
import json
import logging
import os
import threading
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, make_response, render_template, send_file, send_from_directory

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

DATA_DIR   = Path(os.environ.get("DATA_DIR", Path(__file__).parent))
QR_DIR     = DATA_DIR / "qr_codes"
STATE_FILE = DATA_DIR / "seen_cars.json"

refresh_status = {"running": False, "last_run": None, "last_message": "Ready"}

_car_cache: list[dict] | None = None
_cache_mtime: float = 0


def load_cars() -> list[dict]:
    global _car_cache, _cache_mtime
    if not STATE_FILE.exists():
        return []
    mtime = STATE_FILE.stat().st_mtime
    if _car_cache is not None and mtime == _cache_mtime:
        return _car_cache
    data = json.loads(STATE_FILE.read_text())
    cars = []
    for url, info in data.items():
        fp = Path(info.get("file", ""))
        cars.append({
            "name":  info.get("name",  "Unknown"),
            "make":  info.get("make",  "Other"),
            "model": info.get("model", ""),
            "year":  info.get("year",  ""),
            "reg":   info.get("reg",   ""),
            "url":   url,
            "file":  fp.name if fp.exists() else None,
        })
    cars.sort(key=lambda c: (c["make"], c["year"], c["model"]))
    _car_cache = cars
    _cache_mtime = mtime
    return cars


def group_by_make(cars: list[dict]) -> list[dict]:
    """Return list of {make, cars} dicts sorted alphabetically."""
    groups: dict[str, list] = {}
    for c in cars:
        groups.setdefault(c["make"], []).append(c)
    return [{"make": make, "cars": lst} for make, lst in sorted(groups.items())]


def run_scraper(quick: bool = True):
    if refresh_status["running"]:
        return
    refresh_status["running"] = True
    refresh_status["last_message"] = "Checking hugocars.ie…"
    try:
        import generate_qr_codes as g
        g.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        seen  = g.load_seen_cars()
        cars  = g.scrape_car_listings(quick=quick)
        count = g.process_new_cars(cars, seen)
        g.save_seen_cars(seen)
        global _car_cache
        _car_cache = None
        msg = f"{count} new car(s) added." if count else "All up to date."
        refresh_status["last_message"] = msg
        log.info(msg)
    except Exception as e:
        refresh_status["last_message"] = f"Error: {e}"
        log.error(f"Scraper error: {e}")
    finally:
        refresh_status["running"] = False
        refresh_status["last_run"] = datetime.now()


def scrape_in_background(quick: bool = True):
    threading.Thread(target=run_scraper, kwargs={"quick": quick}, daemon=True).start()


@app.route("/")
def index():
    cars   = load_cars()
    groups = group_by_make(cars)
    last   = refresh_status["last_run"]
    return render_template(
        "index.html",
        groups=groups,
        total=len(cars),
        last_run=last.strftime("%-d %b %Y at %H:%M") if last else "Never",
        running=refresh_status["running"],
    )


@app.route("/qr/<filename>")
def serve_qr(filename):
    resp = make_response(send_from_directory(QR_DIR, filename))
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/download/<filename>")
def download_qr(filename):
    return send_from_directory(QR_DIR, filename, as_attachment=True)


@app.route("/download-all")
def download_all():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for car in load_cars():
            if car["file"]:
                p = QR_DIR / car["file"]
                if p.exists():
                    zf.write(p, car["file"])
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name="hugocars_qr_codes.zip")


@app.route("/refresh", methods=["POST"])
def refresh():
    if refresh_status["running"]:
        return jsonify({"status": "already_running"})
    scrape_in_background(quick=True)
    return jsonify({"status": "started"})


@app.route("/status")
def status():
    return jsonify({
        "running":      refresh_status["running"],
        "last_message": refresh_status["last_message"],
        "total":        len(load_cars()),
    })


if __name__ == "__main__":
    QR_DIR.mkdir(parents=True, exist_ok=True)

    # Scrape on startup if no data yet (first deploy / fresh container)
    if not STATE_FILE.exists() or STATE_FILE.stat().st_size < 10:
        log.info("No car data found — running initial full scrape in background…")
        scrape_in_background(quick=False)

    port = int(os.environ.get("PORT", 8080))
    log.info(f"Hugo Cars QR App on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
