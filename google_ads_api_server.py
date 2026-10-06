#!/usr/bin/env python3
"""
Google Ads HTTP API Server - Deploy to Render/Railway
Exposes Google Ads audit & optimization skills for team use
"""

import json
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# FastAPI app
app = FastAPI(
    title="Google Ads Audit API",
    description="Campaign analysis and optimization for Growider MCC",
    version="1.0.0"
)

# Load campaign data
DATA_FILE = Path(__file__).parent / "growider_all_campaigns.json"
_cached_data = None

def load_data(force_reload=False):
    """Load campaign data from JSON (with caching)."""
    global _cached_data
    if not DATA_FILE.exists():
        raise HTTPException(status_code=500, detail="Campaign data not found. Run query_google_ads.py first.")
    if force_reload or _cached_data is None:
        _cached_data = json.loads(DATA_FILE.read_text())
    return _cached_data

# ============================================================================
# SKILL 1: ANALYZE - Campaign Performance Audit
# ============================================================================

@app.get("/skills/analyze/search")
async def analyze_search(
    query: Optional[str] = Query(None, description="Campaign name search"),
    account: Optional[str] = Query(None, description="Filter by account"),
    min_spend: float = Query(0, description="Minimum spend"),
    max_roas: float = Query(999, description="Maximum ROAS threshold"),
    limit: int = Query(50, description="Max results")
):
    """Search campaigns by performance metrics."""
    data = load_data()
    campaigns = data["campaigns"]
    
    if query:
        campaigns = [c for c in campaigns if query.lower() in c['campaign_name'].lower()]
    if account:
        campaigns = [c for c in campaigns if account.lower() in c['account_name'].lower()]
    if min_spend > 0:
        campaigns = [c for c in campaigns if c['cost'] >= min_spend]
    if max_roas < 999:
        campaigns = [c for c in campaigns if c['roas'] <= max_roas]
    
    return sorted(campaigns, key=lambda x: x['cost'], reverse=True)[:limit]

# ============================================================================
# SKILL 2: AUDIT - Full Account Health Check
# ============================================================================

@app.get("/skills/audit/account-health")
async def audit_account_health(account: Optional[str] = Query(None)):
    """Audit account health with scoring."""
    data = load_data()
    campaigns = data["campaigns"]
    
    if account:
        campaigns = [c for c in campaigns if account.lower() in c['account_name'].lower()]
    
    # Calculate metrics
    total_cost = sum(c['cost'] for c in campaigns)
    total_conversions = sum(c['conversions'] for c in campaigns)
    total_value = sum(c['value'] for c in campaigns)
    avg_roas = total_value / total_cost if total_cost > 0 else 0
    avg_cpa = total_cost / total_conversions if total_conversions > 0 else 0
    
    # Health score (0-100)
    score = 50
    issues = []
    
    if avg_roas < 0.5:
        score -= 20
        issues.append("Critical: ROAS < 0.5x (massive waste)")
    elif avg_roas < 1.0:
        score -= 10
        issues.append("High: ROAS < 1.0x (negative ROI)")
    elif avg_roas > 2.0:
        score += 10
        issues.append("Excellent: ROAS > 2.0x")
    
    if len(campaigns) < 3:
        score -= 15
        issues.append("Poor: Too few campaigns")
    elif len(campaigns) > 50:
        score -= 5
        issues.append("Warning: Over 50 campaigns")
    
    top_3_spend = sum(sorted([c['cost'] for c in campaigns], reverse=True)[:3])
    if top_3_spend / total_cost > 0.7 if total_cost > 0 else False:
        score -= 10
        issues.append("High: Top 3 campaigns = 70%+ budget")
    
    return {
        "account": account or "All Accounts",
        "health_score": max(0, min(100, score)),
        "metrics": {
            "total_campaigns": len(campaigns),
            "total_spend": round(total_cost, 2),
            "total_conversions": total_conversions,
            "total_value": round(total_value, 2),
            "avg_roas": round(avg_roas, 2),
            "avg_cpa": round(avg_cpa, 2)
        },
        "issues": issues
    }

# ============================================================================
# SKILL 3: OPTIMIZE - Performance Optimization
# ============================================================================

@app.get("/skills/optimize/recommendations")
async def optimize_recommendations(
    account: Optional[str] = Query(None),
    severity: Optional[str] = Query("high", description="critical, high, medium, low")
):
    """Get optimization recommendations sorted by impact."""
    data = load_data()
    campaigns = data["campaigns"]
    
    if account:
        campaigns = [c for c in campaigns if account.lower() in c['account_name'].lower()]
    
    recommendations = []
    
    for c in campaigns:
        if c['roas'] < 0.5 and c['cost'] > 500:
            recommendations.append({
                "campaign": c['campaign_name'],
                "account": c['account_name'],
                "issue": f"Negative ROI (ROAS {c['roas']}x)",
                "severity": "critical",
                "recommendation": "PAUSE immediately",
                "potential_impact": f"Save ${c['cost'] * 0.5:,.2f}/month",
                "cost": c['cost']
            })
        elif c['cpa'] > 100 and c['conversions'] > 10:
            recommendations.append({
                "campaign": c['campaign_name'],
                "account": c['account_name'],
                "issue": f"High CPA (${c['cpa']})",
                "severity": "high",
                "recommendation": "Lower bid targets or tighten audience",
                "potential_impact": "Reduce CPA by 20-30%",
                "cost": c['cost']
            })
    
    recommendations.sort(key=lambda x: (-recommendations.index(x) if x['severity'] == 'critical' else 1, -x['cost']))
    return {
        "total_recommendations": len(recommendations),
        "total_potential_savings": sum(r['cost'] for r in recommendations if r['severity'] == 'critical'),
        "recommendations": recommendations[:50]
    }

# ============================================================================
# SKILL 4: ANALYTICS - Account Summary
# ============================================================================

@app.get("/skills/analytics/account-summary")
async def analytics_account_summary(account: Optional[str] = Query(None)):
    """Get account-level summary."""
    data = load_data()
    campaigns = data["campaigns"]
    
    by_account = {}
    for c in campaigns:
        acc = c['account_name']
        if acc not in by_account:
            by_account[acc] = {"campaigns": 0, "cost": 0, "conversions": 0, "value": 0}
        by_account[acc]["campaigns"] += 1
        by_account[acc]["cost"] += c['cost']
        by_account[acc]["conversions"] += c['conversions']
        by_account[acc]["value"] += c['value']
    
    if account:
        by_account = {k: v for k, v in by_account.items() if account.lower() in k.lower()}
    
    summaries = []
    for acc_name in sorted(by_account.keys()):
        a = by_account[acc_name]
        cpa = a['cost'] / a['conversions'] if a['conversions'] > 0 else 0
        roas = a['value'] / a['cost'] if a['cost'] > 0 else 0
        
        summaries.append({
            "account": acc_name,
            "campaigns": a['campaigns'],
            "spend": round(a['cost'], 2),
            "conversions": a['conversions'],
            "value": round(a['value'], 2),
            "cpa": round(cpa, 2),
            "roas": round(roas, 2)
        })
    
    total_spend = sum(s['spend'] for s in summaries)
    total_conversions = sum(s['conversions'] for s in summaries)
    total_value = sum(s['value'] for s in summaries)
    
    return {
        "accounts": summaries,
        "totals": {
            "total_accounts": len(summaries),
            "total_campaigns": sum(s['campaigns'] for s in summaries),
            "total_spend": round(total_spend, 2),
            "total_conversions": total_conversions,
            "total_value": round(total_value, 2),
            "avg_cpa": round(total_spend / total_conversions if total_conversions > 0 else 0, 2),
            "avg_roas": round(total_value / total_spend if total_spend > 0 else 0, 2)
        }
    }

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    try:
        data = load_data()
        return {
            "status": "ok",
            "campaigns_loaded": len(data['campaigns']),
            "accounts": data['total_accounts']
        }
    except:
        return {"status": "error", "detail": "Campaign data not loaded"}

@app.get("/skills/details/search-terms")
async def search_terms_breakdown(
    account: Optional[str] = Query(None, description="Filter by account"),
    campaign: Optional[str] = Query(None, description="Filter by campaign"),
    limit: int = Query(100, description="Max results")
):
    """Get search term performance breakdown for campaigns."""
    data = load_data()
    campaigns = data.get("campaigns", [])

    if account:
        campaigns = [c for c in campaigns if account.lower() in c.get('account_name', '').lower()]
    if campaign:
        campaigns = [c for c in campaigns if campaign.lower() in c.get('campaign_name', '').lower()]

    # Aggregate search terms from selected campaigns
    search_terms_agg = {}
    for campaign in campaigns:
        terms = campaign.get("search_terms", [])
        for term in terms[:limit]:
            key = term.get("search_term", "")
            if key not in search_terms_agg:
                search_terms_agg[key] = {
                    "search_term": key,
                    "impressions": 0,
                    "clicks": 0,
                    "cost": 0,
                    "conversions": 0,
                    "value": 0
                }
            search_terms_agg[key]["impressions"] += term.get("impressions", 0)
            search_terms_agg[key]["clicks"] += term.get("clicks", 0)
            search_terms_agg[key]["cost"] += term.get("cost", 0)
            search_terms_agg[key]["conversions"] += term.get("conversions", 0)
            search_terms_agg[key]["value"] += term.get("value", 0)

    # Sort by cost
    search_terms_sorted = sorted(
        search_terms_agg.values(),
        key=lambda x: x["cost"],
        reverse=True
    )[:limit]

    # Calculate metrics
    for term in search_terms_sorted:
        if term["cost"] > 0:
            term["cpc"] = round(term["cost"] / term["clicks"], 2) if term["clicks"] > 0 else 0
            term["cpa"] = round(term["cost"] / term["conversions"], 2) if term["conversions"] > 0 else 0
            term["ctr"] = round(100 * term["clicks"] / term["impressions"], 2) if term["impressions"] > 0 else 0
        else:
            term["cpc"] = term["cpa"] = term["ctr"] = 0

    return {"search_terms": search_terms_sorted}

@app.get("/skills/details/demographics")
async def demographics_breakdown(
    account: Optional[str] = Query(None, description="Filter by account")
):
    """Get age and gender demographic breakdown."""
    data = load_data()
    campaigns = data.get("campaigns", [])

    if account:
        campaigns = [c for c in campaigns if account.lower() in c.get('account_name', '').lower()]

    # Aggregate demographics from selected campaigns
    age_agg = {}
    gender_agg = {}

    for campaign in campaigns:
        demographics = campaign.get("demographics", {})

        # Age data
        for age in demographics.get("age", []):
            key = age.get("age_range", "")
            if key not in age_agg:
                age_agg[key] = {
                    "age_range": key,
                    "impressions": 0,
                    "clicks": 0,
                    "cost": 0,
                    "conversions": 0,
                    "value": 0
                }
            age_agg[key]["impressions"] += age.get("impressions", 0)
            age_agg[key]["clicks"] += age.get("clicks", 0)
            age_agg[key]["cost"] += age.get("cost", 0)
            age_agg[key]["conversions"] += age.get("conversions", 0)
            age_agg[key]["value"] += age.get("value", 0)

        # Gender data
        for gender in demographics.get("gender", []):
            key = gender.get("gender", "")
            if key not in gender_agg:
                gender_agg[key] = {
                    "gender": key,
                    "impressions": 0,
                    "clicks": 0,
                    "cost": 0,
                    "conversions": 0,
                    "value": 0
                }
            gender_agg[key]["impressions"] += gender.get("impressions", 0)
            gender_agg[key]["clicks"] += gender.get("clicks", 0)
            gender_agg[key]["cost"] += gender.get("cost", 0)
            gender_agg[key]["conversions"] += gender.get("conversions", 0)
            gender_agg[key]["value"] += gender.get("value", 0)

    # Calculate metrics
    for age in age_agg.values():
        if age["cost"] > 0:
            age["cpa"] = round(age["cost"] / age["conversions"], 2) if age["conversions"] > 0 else 0
            age["ctr"] = round(100 * age["clicks"] / age["impressions"], 2) if age["impressions"] > 0 else 0
        else:
            age["cpa"] = age["ctr"] = 0

    for gender in gender_agg.values():
        if gender["cost"] > 0:
            gender["cpa"] = round(gender["cost"] / gender["conversions"], 2) if gender["conversions"] > 0 else 0
            gender["ctr"] = round(100 * gender["clicks"] / gender["impressions"], 2) if gender["impressions"] > 0 else 0
        else:
            gender["cpa"] = gender["ctr"] = 0

    return {
        "age": sorted(age_agg.values(), key=lambda x: x["cost"], reverse=True),
        "gender": sorted(gender_agg.values(), key=lambda x: x["cost"], reverse=True)
    }

@app.post("/refresh")
async def refresh_data():
    """Refresh campaign data from Google Ads API (calls query_google_ads.py)."""
    import subprocess
    global _cached_data
    try:
        result = subprocess.run(
            ["python3", "query_google_ads.py"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            # Force reload data from file
            _cached_data = None
            load_data(force_reload=True)
            return {"status": "success", "message": "Campaign data refreshed from Google Ads API"}
        else:
            return {"status": "error", "message": result.stderr}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/skills/details/united-car-report")
async def united_car_report():
    """Get detailed United Car Rental report with search terms + demographics (August)."""
    try:
        uc_file = Path(__file__).parent / "united_car_detailed.json"
        if uc_file.exists():
            data = json.loads(uc_file.read_text())
            return data
        else:
            return {"error": "Report not found"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
async def root():
    """API documentation."""
    return {
        "name": "Google Ads Audit API",
        "version": "1.0.0",
        "endpoints": {
            "analyze": "/skills/analyze/search",
            "audit": "/skills/audit/account-health",
            "optimize": "/skills/optimize/recommendations",
            "analytics": "/skills/analytics/account-summary",
            "refresh": "/refresh (POST)",
            "health": "/health"
        },
        "docs": "/docs"
    }

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
