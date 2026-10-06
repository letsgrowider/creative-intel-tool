#!/usr/bin/env python3
"""
Parse United Car Rental CSV reports and build structured data with search terms + demographics.
"""

import json
import csv
from pathlib import Path
from datetime import datetime

# Read the CSV file you provided
csv_path = Path.home() / "Downloads" / "United Car - Monthly Report'26 - Aug'26.csv"

if not csv_path.exists():
    print(f"❌ File not found: {csv_path}")
    exit(1)

# Parse campaign data
campaigns_data = {}
search_terms_data = []
demographics_data = {"age": [], "gender": []}

with open(csv_path, 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.strip().split('\n')

# Extract sections
campaign_section = []
search_terms_section = []
gender_section = []
age_section = []

current_section = None

for line in lines:
    if 'Campaign Performance' in line:
        current_section = 'campaign'
        continue
    elif 'Search Terms' in line:
        current_section = 'search_terms'
        continue
    elif 'Gender Performance' in line:
        current_section = 'gender'
        continue
    elif 'Age Performance' in line:
        current_section = 'age'
        continue
    elif current_section and line.strip() and not line.startswith(','):
        if current_section == 'campaign':
            campaign_section.append(line)
        elif current_section == 'search_terms':
            search_terms_section.append(line)
        elif current_section == 'gender':
            gender_section.append(line)
        elif current_section == 'age':
            age_section.append(line)

# Parse campaigns
for line in campaign_section[1:]:  # Skip header
    if not line.strip() or line.startswith(','):
        continue
    parts = [p.strip() for p in line.split(',')]
    if len(parts) >= 9 and parts[0]:
        try:
            campaign = {
                "campaign_name": parts[0],
                "clicks": int(parts[1]) if parts[1] else 0,
                "impressions": int(parts[2].replace(',', '')) if parts[2] else 0,
                "ctr": float(parts[3].rstrip('%')) if parts[3] else 0,
                "avg_cpc": float(parts[4]) if parts[4] else 0,
                "cost": float(parts[5].replace('$', '')) if parts[5] else 0,
                "conversions": int(parts[6]) if parts[6] else 0,
                "cpa": float(parts[7].replace('$', '')) if parts[7] else 0,
                "conv_rate": float(parts[8].rstrip('%')) if parts[8] else 0
            }
            campaigns_data[parts[0]] = campaign
        except:
            pass

# Parse search terms
for line in search_terms_section[1:]:
    if not line.strip() or line.startswith(','):
        continue
    parts = [p.strip() for p in line.split(',')]
    if len(parts) >= 8 and parts[0]:
        try:
            term = {
                "search_term": parts[0],
                "clicks": int(parts[1]) if parts[1] else 0,
                "impressions": int(parts[2]) if parts[2] else 0,
                "ctr": float(parts[3].rstrip('%')) if parts[3] else 0,
                "avg_cpc": float(parts[4]) if parts[4] else 0,
                "cost": float(parts[5].replace('$', '')) if parts[5] else 0,
                "conversions": int(parts[6]) if parts[6] else 0,
                "cpa": float(parts[7].replace('$', '')) if parts[7] else 0,
            }
            search_terms_data.append(term)
        except:
            pass

# Parse gender
for line in gender_section[1:]:
    if not line.strip() or line.startswith(','):
        continue
    parts = [p.strip() for p in line.split(',')]
    if len(parts) >= 8 and parts[0]:
        try:
            gender = {
                "gender": parts[0],
                "clicks": int(parts[1]) if parts[1] else 0,
                "impressions": int(parts[2]) if parts[2] else 0,
                "ctr": float(parts[3].rstrip('%')) if parts[3] else 0,
                "avg_cpc": float(parts[4]) if parts[4] else 0,
                "cost": float(parts[5].replace('$', '')) if parts[5] else 0,
                "conversions": int(parts[6]) if parts[6] else 0,
                "cpa": float(parts[7].replace('$', '')) if parts[7] else 0,
            }
            demographics_data["gender"].append(gender)
        except:
            pass

# Parse age
for line in age_section[1:]:
    if not line.strip() or line.startswith(','):
        continue
    parts = [p.strip() for p in line.split(',')]
    if len(parts) >= 8 and parts[0]:
        try:
            age = {
                "age_range": parts[0],
                "clicks": int(parts[1]) if parts[1] else 0,
                "impressions": int(parts[2]) if parts[2] else 0,
                "ctr": float(parts[3].rstrip('%')) if parts[3] else 0,
                "avg_cpc": float(parts[4]) if parts[4] else 0,
                "cost": float(parts[5].replace('$', '')) if parts[5] else 0,
                "conversions": int(parts[6]) if parts[6] else 0,
                "cpa": float(parts[7].replace('$', '')) if parts[7] else 0,
            }
            demographics_data["age"].append(age)
        except:
            pass

# Build campaign objects with detailed breakdowns
campaigns_list = []
for campaign_name, campaign_data in campaigns_data.items():
    campaign_obj = {
        "campaign_id": campaign_name.lower().replace(' ', '_'),
        "campaign_name": campaign_name,
        "account_id": "257-130-9613",
        "account_name": "United Car Rental",
        "impressions": campaign_data["impressions"],
        "clicks": campaign_data["clicks"],
        "cost": campaign_data["cost"],
        "conversions": campaign_data["conversions"],
        "value": campaign_data["conversions"] * campaign_data.get("cpa", 0),  # Estimate
        "cpa": campaign_data["cpa"],
        "roas": campaign_data["cost"] / campaign_data["conversions"] if campaign_data["conversions"] > 0 else 0,
        "search_terms": search_terms_data,
        "demographics": demographics_data
    }
    campaigns_list.append(campaign_obj)

# Build output
output = {
    "total_accounts": 1,
    "total_campaigns": len(campaigns_list),
    "summary": {
        "total_cost_usd": sum(c["cost"] for c in campaigns_list),
        "total_conversions": sum(c["conversions"] for c in campaigns_list),
        "total_value": sum(c["value"] for c in campaigns_list),
        "avg_cpa": sum(c["cpa"] * c["conversions"] for c in campaigns_list) / max(sum(c["conversions"] for c in campaigns_list), 1),
        "roas": sum(c["value"] for c in campaigns_list) / max(sum(c["cost"] for c in campaigns_list), 1)
    },
    "campaigns": campaigns_list,
    "month": "August 2026"
}

# Save
output_path = Path("/Users/alokvedi_1/Claude code/united_car_detailed.json")
output_path.write_text(json.dumps(output, indent=2))

print(f"✅ Parsed United Car Rental data")
print(f"  Campaigns: {len(campaigns_list)}")
print(f"  Search Terms: {len(search_terms_data)}")
print(f"  Demographics: {len(demographics_data['gender'])} genders, {len(demographics_data['age'])} age ranges")
print(f"  Saved: {output_path}")
