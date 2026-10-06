# Google Ads Audit API - Team Guide

## What This Is

Shared API for auditing & optimizing Google Ads campaigns across all Growider accounts. Query campaign data, get optimization recommendations, and track account health.

**Current data:** 476 campaigns across 10 accounts | $9.4M spend | 242k conversions

## Quick Start (5 min)

### Step 1: Get the API URL
- Ask your manager for the API endpoint
- Example: `https://google-ads-api.onrender.com`

### Step 2: Test the API
Visit in browser:
```
https://google-ads-api.onrender.com/docs
```
You'll see interactive API documentation. Click "Try it out" on any endpoint.

### Step 3: Use with Claude Chat
1. Run API query (via browser or curl)
2. Paste response in Claude
3. Ask for analysis/recommendations

Example:
```
Claude, analyze this campaign data and tell me the top 3 optimization opportunities:

[paste API response]
```

## Common Use Cases

### 1. Find Underperforming Campaigns
```
https://google-ads-api.onrender.com/skills/optimize/recommendations?severity=critical
```
**What you get:** Campaigns losing money (ROAS < 0.5x), high CPA campaigns, etc.

### 2. Check Account Health
```
https://google-ads-api.onrender.com/skills/audit/account-health?account=zaveri
```
**What you get:** Health score (0-100), key issues, metrics

### 3. Budget Allocation Advice
```
https://google-ads-api.onrender.com/skills/budget/allocation?account=aparna
```
**What you get:** Which campaigns to scale, which to cut, following 70/20/10 rule

### 4. Account Performance Summary
```
https://google-ads-api.onrender.com/skills/analytics/account-summary
```
**What you get:** All accounts ranked by ROAS, spend, conversions

### 5. Search Specific Campaigns
```
https://google-ads-api.onrender.com/skills/analyze/search?query=search&max_roas=0.5&limit=20
```
**What you get:** Campaigns matching your filters

## Using via Curl (Terminal)

```bash
# Get critical issues across all accounts
curl "https://google-ads-api.onrender.com/skills/optimize/recommendations?severity=critical" | jq

# Check specific account health
curl "https://google-ads-api.onrender.com/skills/audit/account-health?account=roth" | jq

# Get budget recommendations
curl "https://google-ads-api.onrender.com/skills/budget/allocation?account=all" | jq
```

## Using via Slack Bot (Coming Soon)

Subscribe to daily digest:
```
/google-ads subscribe daily
```

Get alerts for critical issues:
```
/google-ads alerts on
```

## Understanding the Scores

### Health Score (0-100)
- **80-100:** Excellent performance
- **60-79:** Good, minor optimizations needed
- **40-59:** Poor, significant issues
- **0-39:** Critical, immediate action needed

### ROAS (Return on Ad Spend)
- **> 2.0x:** Excellent (scale this)
- **1.0-2.0x:** Good (maintain)
- **0.5-1.0x:** Poor (optimize)
- **< 0.5x:** Critical (pause/delete)

### CPA (Cost Per Acquisition)
- Lower = better
- If CPA > 2x your target, reduce bids or tighten targeting

## Common Problems & Solutions

| Issue | Fix |
|-------|-----|
| ROAS < 0.5x | Pause campaign (losing money) |
| CPA too high | Lower bid caps, tighten audience |
| Low CTR | Improve ad copy & headlines |
| Too many campaigns | Consolidate into 5-10 winners |
| Budget spread thin | Follow 70/20/10 rule |

## Questions?

- API docs: Visit `/docs` endpoint
- Issues: Ask in Slack #google-ads channel
- Suggestions: Message @team-lead

## Data Refresh

API updates every 24 hours. Want fresh data? Ask your manager to refresh or run:
```bash
python3 query_google_ads.py
```

---

**Tips:**
- Start with `/skills/optimize/recommendations?severity=critical` to find quick wins
- Use `/skills/audit/account-health` monthly to track progress
- Compare accounts with `/skills/analytics/account-summary`
