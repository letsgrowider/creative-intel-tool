#!/usr/bin/env python3
"""
Google Ads MCP Server - Query and audit campaigns across Growider MCC.
Exposes tools for searching, analyzing, and optimizing campaigns.
"""

import json
from pathlib import Path
from typing import Any
import subprocess
import sys

# For MCP
from mcp.server import Server
from mcp.types import Tool, TextContent, ToolResult

# Initialize MCP server
server = Server("google-ads-audit")

# Load campaign data
DATA_FILE = Path(__file__).parent / "growider_all_campaigns.json"

def load_data():
    """Load campaign data from JSON."""
    if not DATA_FILE.exists():
        return None
    return json.loads(DATA_FILE.read_text())

@server.call_tool()
async def search_campaigns(query: str = "", account: str = "", min_spend: float = 0, max_roas: float = 999):
    """Search campaigns by name, account, spend, or ROAS threshold."""
    data = load_data()
    if not data:
        return ToolResult(content=[TextContent(text="No campaign data found. Run query_google_ads.py first.")])

    results = data["campaigns"]

    # Filter by query (campaign name)
    if query:
        results = [c for c in results if query.lower() in c['campaign_name'].lower()]

    # Filter by account
    if account:
        results = [c for c in results if account.lower() in c['account_name'].lower()]

    # Filter by spend
    if min_spend > 0:
        results = [c for c in results if c['cost'] >= min_spend]

    # Filter by ROAS threshold (campaigns underperforming)
    if max_roas < 999:
        results = [c for c in results if c['roas'] <= max_roas]

    # Format results
    output = f"Found {len(results)} campaigns:\n\n"
    for c in sorted(results, key=lambda x: x['cost'], reverse=True)[:20]:
        output += f"• {c['campaign_name']:50} | {c['account_name']:20} | Spend: ${c['cost']:>10.2f} | ROAS: {c['roas']:>5.2f}x\n"

    return ToolResult(content=[TextContent(text=output)])

@server.call_tool()
async def analyze_performance(account: str = "", threshold_roas: float = 0.5):
    """Identify underperforming campaigns (ROAS below threshold)."""
    data = load_data()
    if not data:
        return ToolResult(content=[TextContent(text="No campaign data found.")])

    campaigns = data["campaigns"]

    # Filter by account if specified
    if account:
        campaigns = [c for c in campaigns if account.lower() in c['account_name'].lower()]

    # Find underperformers
    underperformers = [c for c in campaigns if c['roas'] < threshold_roas and c['cost'] > 100]
    underperformers.sort(key=lambda x: x['roas'])

    output = f"Underperforming Campaigns (ROAS < {threshold_roas}x, Spend > $100):\n\n"
    total_waste = 0
    for c in underperformers[:25]:
        potential_waste = c['cost'] * (1 - c['roas']) if c['roas'] > 0 else c['cost']
        total_waste += potential_waste
        output += f"❌ {c['campaign_name']:45} | {c['account_name']:20} | Spend: ${c['cost']:>10.2f} | ROAS: {c['roas']:>5.2f}x | Potential Waste: ${potential_waste:>10.2f}\n"

    output += f"\n💰 Total Potential Waste (top 25): ${total_waste:,.2f}\n"

    return ToolResult(content=[TextContent(text=output)])

@server.call_tool()
async def get_account_summary(account: str = ""):
    """Get performance summary for an account or all accounts."""
    data = load_data()
    if not data:
        return ToolResult(content=[TextContent(text="No campaign data found.")])

    campaigns = data["campaigns"]

    # Group by account
    by_account = {}
    for c in campaigns:
        acc = c['account_name']
        if acc not in by_account:
            by_account[acc] = {"campaigns": 0, "cost": 0, "conversions": 0, "value": 0, "campaigns_list": []}
        by_account[acc]["campaigns"] += 1
        by_account[acc]["cost"] += c['cost']
        by_account[acc]["conversions"] += c['conversions']
        by_account[acc]["value"] += c['value']
        by_account[acc]["campaigns_list"].append(c)

    # Filter if account specified
    if account:
        by_account = {k: v for k, v in by_account.items() if account.lower() in k.lower()}

    # Format output
    output = "Account Performance Summary:\n\n"
    output += f"{'Account':<30} {'Campaigns':>10} {'Spend':>12} {'Conversions':>12} {'Value':>12} {'CPA':>10} {'ROAS':>8}\n"
    output += "-" * 100 + "\n"

    for acc in sorted(by_account.keys()):
        a = by_account[acc]
        cpa = a['cost'] / a['conversions'] if a['conversions'] > 0 else 0
        roas = a['value'] / a['cost'] if a['cost'] > 0 else 0
        output += f"{acc:<30} {a['campaigns']:>10} ${a['cost']:>11.2f} {a['conversions']:>12} ${a['value']:>11.2f} ${cpa:>9.2f} {roas:>7.2f}x\n"

    return ToolResult(content=[TextContent(text=output)])

@server.call_tool()
async def refresh_data():
    """Refresh campaign data by querying Google Ads API."""
    try:
        result = subprocess.run(
            [sys.executable, "query_google_ads.py"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=120
        )
        return ToolResult(content=[TextContent(text=result.stdout if result.returncode == 0 else result.stderr)])
    except Exception as e:
        return ToolResult(content=[TextContent(text=f"Error refreshing data: {e}")])

@server.call_tool()
async def top_campaigns(account: str = "", limit: int = 10, metric: str = "spend"):
    """Get top campaigns by spend, conversions, or ROAS."""
    data = load_data()
    if not data:
        return ToolResult(content=[TextContent(text="No campaign data found.")])

    campaigns = data["campaigns"]

    # Filter by account if specified
    if account:
        campaigns = [c for c in campaigns if account.lower() in c['account_name'].lower()]

    # Sort by metric
    if metric == "conversions":
        campaigns.sort(key=lambda x: x['conversions'], reverse=True)
        metric_name = "Conversions"
    elif metric == "roas":
        campaigns.sort(key=lambda x: x['roas'], reverse=True)
        metric_name = "ROAS"
    else:  # spend
        campaigns.sort(key=lambda x: x['cost'], reverse=True)
        metric_name = "Spend"

    output = f"Top {limit} Campaigns by {metric_name}:\n\n"
    for i, c in enumerate(campaigns[:limit], 1):
        output += f"{i:2}. {c['campaign_name']:<45} | {c['account_name']:<20} | ${c['cost']:>10.2f} | Conv: {c['conversions']:>6} | ROAS: {c['roas']:>5.2f}x\n"

    return ToolResult(content=[TextContent(text=output)])

async def main():
    """Run MCP server."""
    async with server:
        print("Google Ads Audit MCP Server running...")
        await server.wait_for_shutdown()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
