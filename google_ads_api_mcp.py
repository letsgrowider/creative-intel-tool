#!/usr/bin/env python3
"""
Google Ads API MCP Server - HTTP wrapper for deployed FastAPI service.
Exposes REST endpoints as MCP tools for Claude Chat.
"""

import asyncio
import httpx
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# API base URL
API_BASE = "https://google-ads-api-tmpz.onrender.com"

server = Server("google-ads-api-http")

# Define available tools
TOOLS = [
    Tool(
        name="search_campaigns",
        description="Search campaigns by name, account, spend, or ROAS threshold",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Campaign name search"},
                "account": {"type": "string", "description": "Filter by account"},
                "min_spend": {"type": "number", "description": "Minimum spend"},
                "max_roas": {"type": "number", "description": "Maximum ROAS threshold"}
            }
        }
    ),
    Tool(
        name="account_health",
        description="Get account health score (0-100) and identify issues",
        inputSchema={
            "type": "object",
            "properties": {
                "account": {"type": "string", "description": "Filter by account (optional)"}
            }
        }
    ),
    Tool(
        name="optimization_recommendations",
        description="Get optimization recommendations for underperforming campaigns",
        inputSchema={
            "type": "object",
            "properties": {
                "account": {"type": "string", "description": "Filter by account (optional)"}
            }
        }
    ),
    Tool(
        name="account_summary",
        description="Get performance summary for account(s)",
        inputSchema={
            "type": "object",
            "properties": {
                "account": {"type": "string", "description": "Filter by account (optional)"}
            }
        }
    ),
    Tool(
        name="refresh_data",
        description="Manually refresh campaign data from Google Ads API (live query)",
        inputSchema={"type": "object", "properties": {}}
    ),
    Tool(
        name="health_check",
        description="Check API health status",
        inputSchema={"type": "object", "properties": {}}
    )
]

@server.list_tools()
async def list_tools():
    """List available tools."""
    return TOOLS

async def call_api(endpoint: str, params: dict = None) -> str:
    """Call the HTTP API and return response text."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{API_BASE}{endpoint}"
            response = await client.get(url, params=params)
            response.raise_for_status()
            return json.dumps(response.json(), indent=2)
    except Exception as e:
        return f"Error: {e}"

@server.call_tool()
async def tool_call(name: str, arguments: dict):
    """Handle tool calls."""
    result_text = ""

    if name == "search_campaigns":
        params = {
            "query": arguments.get("query", ""),
            "account": arguments.get("account", ""),
            "min_spend": arguments.get("min_spend", 0),
            "max_roas": arguments.get("max_roas", 999)
        }
        result_text = await call_api("/skills/analyze/search", params)

    elif name == "account_health":
        params = {"account": arguments.get("account", "")} if arguments.get("account") else {}
        result_text = await call_api("/skills/audit/account-health", params)

    elif name == "optimization_recommendations":
        params = {"account": arguments.get("account", "")} if arguments.get("account") else {}
        result_text = await call_api("/skills/optimize/recommendations", params)

    elif name == "account_summary":
        params = {"account": arguments.get("account", "")} if arguments.get("account") else {}
        result_text = await call_api("/skills/analytics/account-summary", params)

    elif name == "refresh_data":
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(f"{API_BASE}/refresh")
                response.raise_for_status()
                result_text = f"✅ Data refreshed: {json.dumps(response.json(), indent=2)}"
        except Exception as e:
            result_text = f"❌ Refresh failed: {e}"

    elif name == "health_check":
        result_text = await call_api("/health")

    else:
        result_text = f"Unknown tool: {name}"

    return [TextContent(type="text", text=result_text)]

async def main():
    """Run MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server)

if __name__ == "__main__":
    asyncio.run(main())
