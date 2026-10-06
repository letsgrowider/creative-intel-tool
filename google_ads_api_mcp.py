#!/usr/bin/env python3
"""
Google Ads API MCP Server - HTTP wrapper for the deployed FastAPI service.
Exposes REST endpoints as MCP tools for Claude Chat integration.
"""

import httpx
import json
from typing import Any
from mcp.server import Server
from mcp.types import Tool, TextContent, ToolResult

# API base URL (update to your Render deployment)
API_BASE = "https://google-ads-api-tmpz.onrender.com"

server = Server("google-ads-api-http")

async def call_api(endpoint: str, params: dict = None) -> dict:
    """Call the HTTP API and return JSON response."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{API_BASE}{endpoint}"
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return {"error": str(e)}

@server.call_tool()
async def search_campaigns(query: str = "", account: str = "", min_spend: float = 0, max_roas: float = 999):
    """Search campaigns by name, account, spend, or ROAS threshold."""
    params = {
        "query": query,
        "account": account,
        "min_spend": min_spend,
        "max_roas": max_roas
    }
    result = await call_api("/skills/analyze/search", params)

    if "error" in result:
        text = f"Error: {result['error']}"
    else:
        text = result.get("results", str(result))

    return ToolResult(content=[TextContent(text=text)])

@server.call_tool()
async def account_health(account: str = ""):
    """Get account health score (0-100) and identify issues."""
    params = {"account": account} if account else {}
    result = await call_api("/skills/audit/account-health", params)

    if "error" in result:
        text = f"Error: {result['error']}"
    else:
        text = result.get("health_report", str(result))

    return ToolResult(content=[TextContent(text=text)])

@server.call_tool()
async def optimization_recommendations(account: str = ""):
    """Get optimization recommendations for underperforming campaigns."""
    params = {"account": account} if account else {}
    result = await call_api("/skills/optimize/recommendations", params)

    if "error" in result:
        text = f"Error: {result['error']}"
    else:
        text = result.get("recommendations", str(result))

    return ToolResult(content=[TextContent(text=text)])

@server.call_tool()
async def account_summary(account: str = ""):
    """Get performance summary for account(s)."""
    params = {"account": account} if account else {}
    result = await call_api("/skills/analytics/account-summary", params)

    if "error" in result:
        text = f"Error: {result['error']}"
    else:
        text = result.get("summary", str(result))

    return ToolResult(content=[TextContent(text=text)])

@server.call_tool()
async def refresh_data():
    """Manually refresh campaign data from Google Ads API."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{API_BASE}/refresh")
            response.raise_for_status()
            return ToolResult(content=[TextContent(text=f"✅ Data refreshed: {response.json()}")])
    except Exception as e:
        return ToolResult(content=[TextContent(text=f"❌ Refresh failed: {e}")])

@server.call_tool()
async def health_check():
    """Check API health status."""
    result = await call_api("/health")

    if "error" in result:
        text = f"❌ API Down: {result['error']}"
    else:
        text = f"✅ API Live: {result}"

    return ToolResult(content=[TextContent(text=text)])

async def main():
    """Run MCP server."""
    async with server:
        print("Google Ads API HTTP MCP Server running...")
        print(f"Backend: {API_BASE}")
        await server.wait_for_shutdown()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
