# Google Ads Audit API

HTTP API for auditing and optimizing Google Ads campaigns across Growider MCC. Deploy to cloud (Render/Railway) for team access.

## Features

- **Analyze** — Search campaigns by performance metrics
- **Audit** — Full account health scoring (0-100)
- **Budget** — Budget allocation recommendations (70/20/10 rule)
- **Optimize** — Automated optimization recommendations
- **Analytics** — Account-level summaries and reporting

## Local Development

```bash
# Install dependencies
pip install -r requirements-api.txt

# Run server
python3 google_ads_api_server.py
# Server runs at http://localhost:8000
# Docs at http://localhost:8000/docs
```

## Deployment to Render

1. **Create Render account** → https://render.com

2. **Connect GitHub repo** (if using git)

3. **Create Web Service:**
   - Repository: your-repo
   - Build Command: `pip install -r requirements-api.txt`
   - Start Command: `python3 google_ads_api_server.py`
   - Environment:
     - `PORT=8000`

4. **Upload campaign data:**
   - Copy `growider_all_campaigns.json` to Render filesystem
   - Or set up scheduled data refresh

5. **Get API URL:**
   - Render provides: `https://your-service.onrender.com`
   - Share with team

## Deployment to Railway

1. **Create Railway account** → https://railway.app

2. **Link GitHub repo**

3. **Add Python environment**

4. **Set start command:** `python3 google_ads_api_server.py`

5. **Deploy** → Railway auto-deploys from git push

## API Endpoints

### Health Check
```
GET /health
```

### Analyze - Search Campaigns
```
GET /skills/analyze/search?query=search&account=zaveri&min_spend=1000&max_roas=0.5&limit=50
```

Response:
```json
[
  {
    "campaign_name": "Search - Leads - Hyd",
    "account_name": "Aparna RMC",
    "cost": 1039041.53,
    "conversions": 3200,
    "roas": 0.10,
    "cpa": 324.70
  }
]
```

### Audit - Account Health
```
GET /skills/audit/account-health?account=aparna
```

Response:
```json
{
  "account": "Aparna RMC",
  "health_score": 35,
  "metrics": {
    "total_campaigns": 26,
    "total_spend": 5825036.15,
    "total_conversions": 46266,
    "avg_roas": 0.23,
    "avg_cpa": 125.90
  },
  "issues": [
    "High: ROAS < 1.0x (negative ROI)",
    "High: Top 3 campaigns = 70%+ of budget (concentration risk)",
    "Critical: Conversion rate < 1%"
  ]
}
```

### Budget - Allocation Recommendations
```
GET /skills/budget/allocation?account=zaveri
```

Response:
```json
{
  "account": "Zaveri Bros",
  "total_budget": 1454438.37,
  "70_20_10_allocation": {
    "scale_top_70": 1018106.86,
    "test_next_20": 290887.67,
    "experiment_last_10": 145443.84
  },
  "recommendations": [
    {
      "campaign": "Campaign A",
      "roas": 2.5,
      "action": "scale"
    },
    {
      "campaign": "Campaign B",
      "roas": 0.3,
      "action": "pause"
    }
  ]
}
```

### Optimize - Recommendations
```
GET /skills/optimize/recommendations?account=all&severity=critical
```

Response:
```json
{
  "total_recommendations": 45,
  "total_potential_savings": 2100000.00,
  "recommendations": [
    {
      "campaign": "Bad Campaign",
      "account": "Aparna RMC",
      "issue": "Negative ROI (ROAS 0.1x)",
      "severity": "critical",
      "recommendation": "PAUSE immediately",
      "potential_impact": "Save $500,000/month",
      "cost": 1000000
    }
  ]
}
```

### Analytics - Account Summary
```
GET /skills/analytics/account-summary?account=all
```

Response:
```json
{
  "accounts": [
    {
      "account": "Zaveri Bros",
      "campaigns": 48,
      "spend": 1454438.37,
      "conversions": 92119,
      "value": 90689.00,
      "cpa": 15.79,
      "roas": 0.06
    }
  ],
  "totals": {
    "total_accounts": 11,
    "total_campaigns": 476,
    "total_spend": 9447582.97,
    "total_conversions": 242501,
    "avg_cpa": 38.96,
    "avg_roas": 0.18
  }
}
```

## Team Usage

### Via Claude Chat
1. Go to Claude Chat
2. Paste API response in prompt
3. Ask: "Analyze this campaign data and give me top 3 optimizations"
4. Claude analyzes and provides recommendations

### Via Curl
```bash
curl "https://your-service.onrender.com/skills/optimize/recommendations?severity=critical"
```

### Via Python
```python
import requests

base_url = "https://your-service.onrender.com"
response = requests.get(f"{base_url}/skills/audit/account-health?account=zaveri")
print(response.json())
```

### Via Webhook (Zapier/Make)
1. Create Zap/Automation
2. Trigger: Schedule (daily)
3. Action: HTTP request to API endpoint
4. Post result to Slack/Email

## Data Refresh

API reads from `growider_all_campaigns.json`. To refresh:

```bash
# Run locally
python3 query_google_ads.py
# Updates growider_all_campaigns.json

# Push to deployment
git push
# Render/Railway auto-redeploys
```

Or set up scheduled job in Render/Railway to refresh data daily.

## Environment Variables

- `PORT` — Server port (default: 8000)
- `DATA_FILE` — Path to campaign JSON (default: growider_all_campaigns.json)

## Errors

**"Campaign data not found"**
- Upload `growider_all_campaigns.json` to server
- Or run `python3 query_google_ads.py` first

**"No results found"**
- Check account name spelling
- Try without filters

## Support

Questions? Check `/docs` endpoint (Swagger UI) for interactive testing.
