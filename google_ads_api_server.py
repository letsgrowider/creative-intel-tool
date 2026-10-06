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

def load_data():
    """Load campaign data from JSON."""
    if not DATA_FILE.exists():
        raise HTTPException(status_code=500, detail="Campaign data not found. Run query_google_ads.py first.")
    return json.loads(DATA_FILE.read_text())

# ============================================================================
# DATA MODELS
# ============================================================================

class CampaignData(BaseModel):
    account_id: str
    account_name: str
    campaign_id: str
    campaign_name: str
    status: str
    impressions: int
    clicks: int
    cost: float
    conversions: int
    value: float
    cpa: float
    roas: float

class AccountSummary(BaseModel):
    name: str
    campaigns: int
    spend: float
    conversions: int
    value: float
    cpa: float
    roas: float

class OptimizationRecommendation(BaseModel):
    campaign: str
    account: str
    issue: str
    severity: str  # critical, high, medium, low
    recommendation: str
    potential_impact: str

# ============================================================================
# SKILL 1: ANALYZE - Campaign Performance Audit
# ============================================================================

@app.get("/skills/analyze/search", response_model=List[CampaignData])
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
    """Audit account health with 74-point scoring."""
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
    score = 50  # baseline
    issues = []

    # ROAS checks
    if avg_roas < 0.5:
        score -= 20
        issues.append("Critical: ROAS < 0.5x (massive waste)")
    elif avg_roas < 1.0:
        score -= 10
        issues.append("High: ROAS < 1.0x (negative ROI)")
    elif avg_roas > 2.0:
        score += 10
        issues.append("Excellent: ROAS > 2.0x")

    # Campaign structure
    if len(campaigns) < 3:
        score -= 15
        issues.append("Poor: Too few campaigns (<3)")
    elif len(campaigns) > 50:
        score -= 5
        issues.append("Warning: Over 50 campaigns (hard to manage)")

    # Spend concentration
    top_3_spend = sum(sorted([c['cost'] for c in campaigns], reverse=True)[:3])
    if top_3_spend / total_cost > 0.7:
        score -= 10
        issues.append("High: Top 3 campaigns = 70%+ of budget (concentration risk)")

    # Conversion rate
    total_clicks = sum(c['clicks'] for c in campaigns)
    conv_rate = total_conversions / total_clicks if total_clicks > 0 else 0
    if conv_rate < 0.01:
        score -= 15
        issues.append("Critical: Conversion rate < 1%")

    return {
        "account": account or "All Accounts",
        "health_score": max(0, min(100, score)),
        "metrics": {
            "total_campaigns": len(campaigns),
            "total_spend": round(total_cost, 2),
            "total_conversions": total_conversions,
            "total_value": round(total_value, 2),
            "avg_roas": round(avg_roas, 2),
            "avg_cpa": round(avg_cpa, 2),
            "conversion_rate": round(conv_rate * 100, 2)
        },
        "issues": issues
    }

# ============================================================================
# SKILL 3: BUDGET - Budget Allocation & Bidding Strategy
# ============================================================================

@app.get("/skills/budget/allocation")
async def budget_allocation(account: Optional[str] = Query(None)):
    """Analyze budget allocation and recommend rebalancing."""
    data = load_data()
    campaigns = data["campaigns"]

    if account:
        campaigns = [c for c in campaigns if account.lower() in c['account_name'].lower()]

    # Rank by ROAS
    campaigns.sort(key=lambda x: x['roas'], reverse=True)

    total_spend = sum(c['cost'] for c in campaigns)

    recommendations = []

    # 70/20/10 rule
    for i, c in enumerate(campaigns):
        if i < len(campaigns) * 0.7:
            target_pct = 70
            phase = "Scale (Top 70%)"
        elif i < len(campaigns) * 0.9:
            target_pct = 20
            phase = "Test (Next 20%)"
        else:
            target_pct = 10
            phase = "Experiment (Last 10%)"

        current_pct = (c['cost'] / total_spend) * 100 if total_spend > 0 else 0

        if abs(current_pct - (target_pct / (len(campaigns) * 0.3))) > 5:
            recommendations.append({
                "campaign": c['campaign_name'],
                "current_spend": c['cost'],
                "current_pct": round(current_pct, 1),
                "roas": c['roas'],
                "recommendation": f"Move to {phase} bucket",
                "action": "scale" if c['roas'] > 1.5 else "optimize" if c['roas'] > 0.5 else "pause"
            })

    return {
        "account": account or "All Accounts",
        "total_budget": round(total_spend, 2),
        "70_20_10_allocation": {
            "scale_top_70": round(total_spend * 0.7, 2),
            "test_next_20": round(total_spend * 0.2, 2),
            "experiment_last_10": round(total_spend * 0.1, 2)
        },
        "recommendations": recommendations[:20]
    }

# ============================================================================
# SKILL 4: OPTIMIZE - Performance Optimization
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
        # Rule 1: ROAS < 0.5 = critical waste
        if c['roas'] < 0.5 and c['cost'] > 500:
            recommendations.append({
                "campaign": c['campaign_name'],
                "account": c['account_name'],
                "issue": f"Negative ROI (ROAS {c['roas']}x)",
                "severity": "critical",
                "recommendation": "PAUSE immediately - losing $0.50+ per $1 spent",
                "potential_impact": f"Save ${c['cost'] * 0.5:,.2f}/month",
                "cost": c['cost']
            })

        # Rule 2: High CPA (>$100)
        elif c['cpa'] > 100 and c['conversions'] > 10:
            recommendations.append({
                "campaign": c['campaign_name'],
                "account": c['account_name'],
                "issue": f"High CPA (${c['cpa']})",
                "severity": "high",
                "recommendation": "Lower bid targets or tighten audience targeting",
                "potential_impact": f"Reduce CPA by 20-30%",
                "cost": c['cost']
            })

        # Rule 3: Low CTR (<2%)
        elif c['clicks'] > 0 and (c['impressions'] / c['clicks'] > 50):
            ctr = (c['clicks'] / c['impressions'] * 100) if c['impressions'] > 0 else 0
            recommendations.append({
                "campaign": c['campaign_name'],
                "account": c['account_name'],
                "issue": f"Low CTR ({ctr:.2f}%)",
                "severity": "medium",
                "recommendation": "Improve ad copy, headlines, or targeting",
                "potential_impact": f"Improve CTR by 30-50%",
                "cost": c['cost']
            })

        # Rule 4: 3x Kill Rule - if ROAS < 0.3x and spend > $1k
        elif c['roas'] < 0.3 and c['cost'] > 1000:
            recommendations.append({
                "campaign": c['campaign_name'],
                "account": c['account_name'],
                "issue": "3x Kill Rule triggered - extreme underperformance",
                "severity": "critical",
                "recommendation": "DELETE this campaign - not recoverable",
                "potential_impact": f"Stop wasting ${c['cost']:,.2f}/month",
                "cost": c['cost']
            })

    # Filter by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    recommendations.sort(key=lambda x: (severity_order.get(x['severity'], 999), -x['cost']))

    # Filter
    if severity:
        recommendations = [r for r in recommendations if r['severity'] == severity or severity == "all"]

    total_potential_savings = sum(c['cost'] for c in campaigns if c['roas'] < 0.5)

    return {
        "total_recommendations": len(recommendations),
        "total_potential_savings": round(total_potential_savings, 2),
        "recommendations": recommendations[:50]
    }

# ============================================================================
# SKILL 5: ANALYTICS - Account Summary & Reporting
# ============================================================================

@app.get("/skills/analytics/account-summary")
async def analytics_account_summary(account: Optional[str] = Query(None)):
    """Get account-level summary."""
    data = load_data()
    campaigns = data["campaigns"]

    # Group by account
    by_account = {}
    for c in campaigns:
        acc = c['account_name']
        if acc not in by_account:
            by_account[acc] = {"campaigns": 0, "cost": 0, "conversions": 0, "value": 0, "list": []}
        by_account[acc]["campaigns"] += 1
        by_account[acc]["cost"] += c['cost']
        by_account[acc]["conversions"] += c['conversions']
        by_account[acc]["value"] += c['value']
        by_account[acc]["list"].append(c)

    # Filter if account specified
    if account:
        by_account = {k: v for k, v in by_account.items() if account.lower() in k.lower()}

    # Format
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

    # Totals
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

# ============================================================================
# ROOT
# ============================================================================

@app.get("/")
async def root():
    """API documentation."""
    return {
        "name": "Google Ads Audit API",
        "version": "1.0.0",
        "endpoints": {
            "analyze": "/skills/analyze/search",
            "audit": "/skills/audit/account-health",
            "budget": "/skills/budget/allocation",
            "optimize": "/skills/optimize/recommendations",
            "analytics": "/skills/analytics/account-summary",
            "health": "/health"
        },
        "docs": "/docs"
    }

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
