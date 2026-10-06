#!/usr/bin/env python3
"""Query Google Ads API for confirmbus account performance data."""

import json
from pathlib import Path
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.oauth2 import service_account

# Credentials
DEVELOPER_TOKEN = "2HYgJd1IJOpk1f8Ogm5iqg"
MCC_ACCOUNT_ID = "7061241746"
SERVICE_ACCOUNT_FILE = Path.home() / "Downloads" / "brand-ads-dashboard-82311484407a.json"

def authenticate():
    """Authenticate using service account."""
    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"❌ Service account file not found: {SERVICE_ACCOUNT_FILE}")
        return None

    # Load service account credentials
    credentials = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE),
        scopes=["https://www.googleapis.com/auth/adwords"]
    )

    print(f"✅ Authenticated as {credentials.service_account_email}")
    return credentials

def query_accounts(client):
    """List all accessible Google Ads accounts."""
    ga_service = client.get_service("GoogleAdsService")

    try:
        response = ga_service.search(
            customer_id=MCC_ACCOUNT_ID,
            query="SELECT customer.id, customer.descriptive_name FROM customer",
        )

        accounts = []
        for row in response:
            customer = row.customer
            accounts.append({
                "id": customer.id,
                "name": customer.descriptive_name
            })

        return accounts
    except GoogleAdsException as ex:
        print(f"❌ Request failed with status code {ex.error.code()}")
        for error in ex.failure.errors:
            print(f"  Error: {error.message}")
        return []

def get_account_performance(client, customer_id):
    """Get performance metrics for an account."""
    ga_service = client.get_service("GoogleAdsService")

    query = """
    SELECT
        campaign.id,
        campaign.name,
        metrics.impressions,
        metrics.clicks,
        metrics.cost_micros,
        metrics.conversions,
        metrics.conversions_value
    FROM campaign
    WHERE campaign.status = 'ENABLED'
    ORDER BY metrics.cost_micros DESC
    LIMIT 100
    """

    try:
        response = ga_service.search(customer_id=customer_id, query=query)

        campaigns = []
        for row in response:
            campaign = row.campaign
            metrics = row.metrics

            cost_usd = metrics.cost_micros / 1_000_000
            cpa = (cost_usd / metrics.conversions) if metrics.conversions > 0 else 0
            roas = (metrics.conversions_value / cost_usd) if cost_usd > 0 else 0

            campaigns.append({
                "campaign_id": campaign.id,
                "campaign_name": campaign.name,
                "impressions": metrics.impressions,
                "clicks": metrics.clicks,
                "cost_usd": round(cost_usd, 2),
                "conversions": int(metrics.conversions),
                "conversion_value": round(metrics.conversions_value, 2),
                "cpa": round(cpa, 2),
                "roas": round(roas, 2)
            })

        return campaigns
    except GoogleAdsException as ex:
        print(f"❌ Request failed: {ex.error.code()}")
        for error in ex.failure.errors:
            print(f"  Error: {error.message}")
        return []

def main():
    print("🔐 Google Ads API Query")
    print(f"Developer Token: {DEVELOPER_TOKEN[:20]}...")
    print(f"MCC: {MCC_ACCOUNT_ID}\n")

    # Authenticate
    creds = authenticate()
    if not creds:
        return

    # Create client using google-ads.yaml
    config_path = Path.home() / ".config" / "google-ads.yaml"
    client = GoogleAdsClient.load_from_storage(config_path)

    # List accounts
    print("📊 Fetching accessible accounts...\n")
    accounts = query_accounts(client)

    # Find confirmbus
    confirmbus = None
    for acc in accounts:
        print(f"  {acc['id']}: {acc['name']}")
        if "confirmbus" in acc['name'].lower():
            confirmbus = acc

    if not confirmbus:
        print("\n❌ confirmbus account not found")
        print(f"Found {len(accounts)} accounts. Make sure confirmbus MCC is linked.")
        return

    print(f"\n✅ Found: {confirmbus['name']} ({confirmbus['id']})")

    # Get performance
    print(f"\n📈 Fetching campaign performance for {confirmbus['name']}...\n")
    campaigns = get_account_performance(client, confirmbus['id'])

    if not campaigns:
        print("No campaigns found or API error")
        return

    # Display
    total_cost = sum(c['cost_usd'] for c in campaigns)
    total_conversions = sum(c['conversions'] for c in campaigns)
    total_value = sum(c['conversion_value'] for c in campaigns)
    avg_cpa = (total_cost / total_conversions) if total_conversions > 0 else 0
    roas = (total_value / total_cost) if total_cost > 0 else 0

    print("Campaign Performance:")
    print("-" * 120)
    print(f"{'Campaign':<40} {'Impr':>8} {'Clicks':>8} {'Cost':>10} {'Conv':>6} {'CPA':>8} {'ROAS':>6}")
    print("-" * 120)

    for c in campaigns:
        print(f"{c['campaign_name']:<40} {c['impressions']:>8} {c['clicks']:>8} "
              f"${c['cost_usd']:>9.2f} {c['conversions']:>6} ${c['cpa']:>7.2f} {c['roas']:>5.2f}x")

    print("-" * 120)
    print(f"{'TOTAL':<40} {sum(c['impressions'] for c in campaigns):>8} "
          f"{sum(c['clicks'] for c in campaigns):>8} ${total_cost:>9.2f} {total_conversions:>6} "
          f"${avg_cpa:>7.2f} {roas:>5.2f}x")

    # Save JSON
    output = {
        "account": confirmbus,
        "summary": {
            "total_cost_usd": round(total_cost, 2),
            "total_conversions": total_conversions,
            "total_value": round(total_value, 2),
            "avg_cpa": round(avg_cpa, 2),
            "roas": round(roas, 2),
        },
        "campaigns": campaigns
    }

    json_file = Path("confirmbus_performance.json")
    json_file.write_text(json.dumps(output, indent=2))
    print(f"\n📁 Data saved to {json_file}")

if __name__ == "__main__":
    main()
