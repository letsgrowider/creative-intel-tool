#!/usr/bin/env python3
"""
Query Google Ads API for all MCC accounts with detailed breakdowns.
Includes search terms, demographics (age, gender).
"""

import json
from pathlib import Path
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.oauth2 import service_account
from collections import defaultdict

# Credentials
DEVELOPER_TOKEN = "2HYgJd1IJOpk1f8Ogm5iqg"
MCC_ACCOUNT_ID = "7061241746"
SERVICE_ACCOUNT_FILE = Path.home() / "Downloads" / "brand-ads-dashboard-82311484407a.json"

def authenticate():
    """Authenticate using service account."""
    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"❌ Service account file not found: {SERVICE_ACCOUNT_FILE}")
        return None

    credentials = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE),
        scopes=["https://www.googleapis.com/auth/adwords"]
    )

    print(f"✅ Authenticated as {credentials.service_account_email}")
    return credentials

def query_accounts(client):
    """List all accessible accounts."""
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

def get_campaign_performance(client, customer_id):
    """Get campaign metrics."""
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
                "cost": round(cost_usd, 2),
                "conversions": int(metrics.conversions),
                "value": round(metrics.conversions_value, 2),
                "cpa": round(cpa, 2),
                "roas": round(roas, 2)
            })

        return campaigns
    except GoogleAdsException as ex:
        print(f"❌ Request failed: {ex.error.code()}")
        for error in ex.failure.errors:
            print(f"  Error: {error.message}")
        return []

def get_search_terms(client, customer_id):
    """Get search term performance."""
    ga_service = client.get_service("GoogleAdsService")

    query = """
    SELECT
        search_term_view.search_term,
        metrics.impressions,
        metrics.clicks,
        metrics.cost_micros,
        metrics.conversions,
        metrics.conversions_value
    FROM search_term_view
    ORDER BY metrics.cost_micros DESC
    LIMIT 500
    """

    try:
        response = ga_service.search(customer_id=customer_id, query=query)

        search_terms = []
        for row in response:
            metrics = row.metrics
            cost_usd = metrics.cost_micros / 1_000_000

            search_terms.append({
                "search_term": row.search_term_view.search_term,
                "impressions": metrics.impressions,
                "clicks": metrics.clicks,
                "cost": round(cost_usd, 2),
                "conversions": int(metrics.conversions),
                "value": round(metrics.conversions_value, 2)
            })

        return search_terms
    except GoogleAdsException:
        return []

def get_demographics(client, customer_id):
    """Get age and gender demographic performance."""
    ga_service = client.get_service("GoogleAdsService")

    # Age ranges
    age_query = """
    SELECT
        age_range_view.age_range,
        metrics.impressions,
        metrics.clicks,
        metrics.cost_micros,
        metrics.conversions,
        metrics.conversions_value
    FROM age_range_view
    """

    # Gender
    gender_query = """
    SELECT
        gender_view.gender,
        metrics.impressions,
        metrics.clicks,
        metrics.cost_micros,
        metrics.conversions,
        metrics.conversions_value
    FROM gender_view
    """

    demographics = {"age": [], "gender": []}

    try:
        # Age data
        response = ga_service.search(customer_id=customer_id, query=age_query)
        for row in response:
            metrics = row.metrics
            cost_usd = metrics.cost_micros / 1_000_000
            age_range = row.age_range_view.age_range

            demographics["age"].append({
                "age_range": age_range,
                "impressions": metrics.impressions,
                "clicks": metrics.clicks,
                "cost": round(cost_usd, 2),
                "conversions": int(metrics.conversions),
                "value": round(metrics.conversions_value, 2)
            })

        # Gender data
        response = ga_service.search(customer_id=customer_id, query=gender_query)
        for row in response:
            metrics = row.metrics
            cost_usd = metrics.cost_micros / 1_000_000
            gender = row.gender_view.gender

            demographics["gender"].append({
                "gender": gender,
                "impressions": metrics.impressions,
                "clicks": metrics.clicks,
                "cost": round(cost_usd, 2),
                "conversions": int(metrics.conversions),
                "value": round(metrics.conversions_value, 2)
            })

    except GoogleAdsException:
        pass

    return demographics

def main():
    print("🔐 Google Ads Detailed Query (All Accounts)\n")

    # Authenticate
    creds = authenticate()
    if not creds:
        return

    # Create client
    config_path = Path.home() / ".config" / "google-ads.yaml"
    client = GoogleAdsClient.load_from_storage(config_path)

    # List accounts
    print("📊 Fetching all accessible accounts...\n")
    accounts = query_accounts(client)
    print(f"✅ Found {len(accounts)} accounts\n")

    all_campaigns = []

    for account in accounts:
        print(f"  Querying {account['name']} ({account['id']})...")

        # Get campaign data
        campaigns = get_campaign_performance(client, account['id'])

        # Get search terms & demographics
        search_terms = get_search_terms(client, account['id'])
        demographics = get_demographics(client, account['id'])

        # Enrich campaigns with account info and breakdowns
        for campaign in campaigns:
            campaign["account_id"] = account['id']
            campaign["account_name"] = account['name']
            campaign["search_terms"] = search_terms
            campaign["demographics"] = demographics
            all_campaigns.append(campaign)

    # Summary stats
    total_cost = sum(c['cost'] for c in all_campaigns)
    total_conversions = sum(c['conversions'] for c in all_campaigns)
    total_value = sum(c['value'] for c in all_campaigns)
    avg_cpa = (total_cost / total_conversions) if total_conversions > 0 else 0
    roas = (total_value / total_cost) if total_cost > 0 else 0

    print(f"\n📈 Summary:")
    print(f"  Accounts: {len(accounts)}")
    print(f"  Campaigns: {len(all_campaigns)}")
    print(f"  Total Spend: ${total_cost:,.2f}")
    print(f"  Total Conversions: {total_conversions:,}")
    print(f"  Avg CPA: ${avg_cpa:.2f}")
    print(f"  ROAS: {roas:.2f}x")

    # Save to JSON
    output = {
        "total_accounts": len(accounts),
        "total_campaigns": len(all_campaigns),
        "summary": {
            "total_cost_usd": round(total_cost, 2),
            "total_conversions": total_conversions,
            "total_value": round(total_value, 2),
            "avg_cpa": round(avg_cpa, 2),
            "roas": round(roas, 2),
        },
        "campaigns": all_campaigns
    }

    json_file = Path("growider_all_campaigns.json")
    json_file.write_text(json.dumps(output, indent=2))
    print(f"\n✅ Data saved to {json_file}")

if __name__ == "__main__":
    main()
