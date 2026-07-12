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
import threading
from functools import wraps

from flask import Flask, render_template, request, jsonify, Response, send_file

sys.path.insert(0, os.path.dirname(__file__))
from scrape_meta_ads import scrape_meta_ads
from download_ad_media import download_ad_media
from analyze_ads_gemini import analyze_ads_gemini
from generate_visual_report import generate_visual_report

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")
jobs: dict[str, dict] = {}


# ── Password protection ───────────────────────────────────────────────────────

def _check_auth(password: str) -> bool:
    app_password = os.environ.get("APP_PASSWORD", "")
    return bool(app_password) and password == app_password


def _auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Skip auth if no password set (local dev)
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


def _log(job_id: str, msg: str, step: int = None):
    jobs[job_id]["logs"].append({"msg": msg, "step": step, "ts": time.time()})


def run_pipeline(job_id, page_urls, max_ads, brand_name, brand_voice, base_dir):
    try:
        jobs[job_id]["status"] = "running"

        _log(job_id, f"Scraping {len(page_urls)} page(s) — up to {max_ads} ads each...", 1)
        ads = scrape_meta_ads(page_urls, max_ads=max_ads)
        _log(job_id, f"✓ {len(ads)} ads returned", 1)

        if not ads:
            raise ValueError("No ads found. Check page URLs.")

        _log(job_id, "Downloading media files...", 2)
        ads = download_ad_media(ads, base_dir=base_dir)
        downloaded = sum(1 for a in ads if a.get("localPath"))
        _log(job_id, f"✓ {downloaded}/{len(ads)} files downloaded", 2)

        _log(job_id, "Analyzing ads with Gemini 2.5 Flash...", 3)
        ads = analyze_ads_gemini(ads, base_dir=base_dir)
        analyzed = sum(1 for a in ads if a.get("analysisPath"))
        _log(job_id, f"✓ {analyzed}/{len(ads)} ads analyzed", 3)

        _log(job_id, "Synthesizing intelligence report with Claude...", 4)
        report_path = generate_visual_report(
            ads=ads,
            base_dir=base_dir,
            brand_name=brand_name,
            brand_voice=brand_voice,
        )
        _log(job_id, "✓ Report ready!", 4)

        jobs[job_id]["status"] = "done"
        jobs[job_id]["report_path"] = report_path

    except Exception as e:
        _log(job_id, f"ERROR: {e}")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


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

    base_dir = os.path.join(os.path.dirname(__file__), "jobs", job_id)
    os.makedirs(base_dir, exist_ok=True)

    jobs[job_id] = {
        "status": "pending",
        "logs": [],
        "report_path": None,
        "brand_name": data.get("brand_name", "Unknown"),
    }

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
        while True:
            job = jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break
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
    job = jobs.get(job_id)
    if not job:
        return "Job not found", 404
    if job["status"] == "error":
        return f"Pipeline failed: {job.get('error', 'Unknown error')}", 500
    if not job.get("report_path"):
        return "Report not ready yet", 404
    return send_file(job["report_path"])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n  Creative Intelligence Tool — http://localhost:{port}\n")
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
