"""
Competitive Creative Intelligence Tool — Flask web app.
Run: python3 app.py
Open: http://localhost:5001
"""

import os
import sys
import json
import time
import uuid
import glob
import threading
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, jsonify, Response, send_file

sys.path.insert(0, os.path.dirname(__file__))
from scrape_meta_ads import scrape_meta_ads
from download_ad_media import download_ad_media
from analyze_ads_gemini import analyze_ads_gemini
from generate_visual_report import generate_visual_report

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

JOBS_ROOT = os.path.join(os.path.dirname(__file__), "jobs")


# ── Disk-backed job state (survives server restarts) ─────────────────────────

def _job_file(job_id: str) -> str:
    return os.path.join(JOBS_ROOT, job_id, "job.json")


def _save_job(job_id: str, state: dict):
    Path(_job_file(job_id)).write_text(json.dumps(state), encoding="utf-8")


def _load_job(job_id: str) -> dict | None:
    p = _job_file(job_id)
    if os.path.exists(p):
        try:
            return json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _log(job_id: str, msg: str, step: int = None):
    state = _load_job(job_id) or {"status": "running", "logs": [], "report_path": None}
    state["logs"].append({"msg": msg, "step": step, "ts": time.time()})
    _save_job(job_id, state)


# ── Password protection ───────────────────────────────────────────────────────

def _check_auth(password: str) -> bool:
    app_password = os.environ.get("APP_PASSWORD", "")
    return bool(app_password) and password == app_password


def _auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not os.environ.get("APP_PASSWORD"):
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or not _check_auth(auth.password):
            return Response(
                "Access denied. Enter team password.",
                401,
                {"WWW-Authenticate": 'Basic realm="Creative Intel Tool"'},
            )
        return f(*args, **kwargs)
    return decorated


# ── Pipeline ─────────────────────────────────────────────────────────────────

def run_pipeline(job_id, page_urls, max_ads, brand_name, brand_voice, base_dir):
    def upd(msg, step=None):
        _log(job_id, msg, step)

    try:
        state = _load_job(job_id)
        state["status"] = "running"
        _save_job(job_id, state)

        upd(f"Scraping {len(page_urls)} page(s) — up to {max_ads} ads each...", 1)
        ads = scrape_meta_ads(page_urls, max_ads=max_ads)
        upd(f"✓ {len(ads)} ads returned", 1)

        if not ads:
            raise ValueError("No ads found. Check page URLs.")

        upd("Downloading media files...", 2)
        ads = download_ad_media(ads, base_dir=base_dir)
        downloaded = sum(1 for a in ads if a.get("localPath"))
        upd(f"✓ {downloaded}/{len(ads)} files downloaded", 2)

        upd("Analyzing ads with Gemini 2.5 Flash...", 3)
        ads = analyze_ads_gemini(ads, base_dir=base_dir)
        analyzed = sum(1 for a in ads if a.get("analysisPath"))
        upd(f"✓ {analyzed}/{len(ads)} ads analyzed", 3)

        upd("Synthesizing intelligence report with Claude...", 4)
        report_path = generate_visual_report(
            ads=ads,
            base_dir=base_dir,
            brand_name=brand_name,
            brand_voice=brand_voice,
        )
        upd("✓ Report ready!", 4)

        state = _load_job(job_id)
        state["status"] = "done"
        state["report_path"] = report_path
        _save_job(job_id, state)

    except Exception as e:
        upd(f"ERROR: {e}")
        state = _load_job(job_id) or {}
        state["status"] = "error"
        state["error"] = str(e)
        _save_job(job_id, state)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
@_auth_required
def index():
    return render_template("form.html")


@app.route("/run", methods=["POST"])
@_auth_required
def run():
    data = request.json or {}
    job_id = str(uuid.uuid4())[:8]

    urls = [u.strip() for u in data.get("competitor_urls", []) if u.strip()]
    if data.get("client_facebook", "").strip():
        urls.insert(0, data["client_facebook"].strip())

    if not urls:
        return jsonify({"error": "At least one Facebook page URL required"}), 400

    base_dir = os.path.join(JOBS_ROOT, job_id)
    os.makedirs(base_dir, exist_ok=True)

    initial_state = {
        "status": "pending",
        "logs": [],
        "report_path": None,
        "brand_name": data.get("brand_name", "Unknown"),
    }
    _save_job(job_id, initial_state)

    threading.Thread(
        target=run_pipeline,
        args=(
            job_id, urls,
            int(data.get("max_ads", 50)),
            data.get("brand_name", ""),
            data.get("brand_voice", ""),
            base_dir,
        ),
        daemon=True,
    ).start()

    return jsonify({"job_id": job_id})


@app.route("/progress/<job_id>")
@_auth_required
def progress(job_id):
    def stream():
        seen = 0
        not_found_count = 0
        while True:
            job = _load_job(job_id)
            if not job:
                not_found_count += 1
                if not_found_count > 10:
                    yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                    break
                time.sleep(1)
                continue
            not_found_count = 0
            for entry in job["logs"][seen:]:
                yield f"data: {json.dumps(entry)}\n\n"
            seen = len(job["logs"])
            if job["status"] in ("done", "error"):
                yield f"data: {json.dumps({'status': job['status'], 'job_id': job_id})}\n\n"
                break
            time.sleep(1)

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/report/<job_id>")
@_auth_required
def report(job_id):
    job = _load_job(job_id)
    if not job:
        return "Job not found", 404
    if job["status"] == "error":
        return f"Pipeline failed: {job.get('error', 'Unknown error')}", 500
    report_path = job.get("report_path")
    if not report_path or not os.path.exists(report_path):
        # Try to find the report file directly
        matches = glob.glob(os.path.join(JOBS_ROOT, job_id, "output", "*.html"))
        if matches:
            return send_file(matches[0])
        return "Report not ready yet", 404
    return send_file(report_path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n  Creative Intelligence Tool — http://localhost:{port}\n")
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
