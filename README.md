# Scraper

Educational inventory scraper for prefab countertop products.

It scrapes product data and live inventory from:

- Quartz
- Granite
- Marble
- Quartzite
- Engineered Granite

## Outputs

Primary daily file:

- `output/products.csv`
  - columns: `product_id,product_name,price,inventory,category_name`

Weekly analysis files:

- `output/weekly_inventory_long.csv`
  - columns: `week_date,source_date,product_id,product_name,category_name,inventory`
- `output/weekly_inventory_wide.csv`
  - columns: `product_id,product_name,category_name,<one column per Monday week_date>`
- `output/weekly_snapshot_status.csv`
  - columns: `week_date,source_date,status,fallback_used,row_count`

Weekly archive/state:

- `output/archive/products_YYYY-MM-DD.csv`
  - active Monday-based weekly snapshots for the current year
- `output/archive/yearly/YYYY/`
  - yearly archived snapshots and derived CSVs once a new calendar year starts
- `output/state/pending_weekly_snapshot.json`
  - internal state used when Monday inventory is all zero

`inventory` is pulled from the live endpoint used by the site's check-inventory flow.

Deduplication is URL-based (`product_url`), not `product_id`-based.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Local Run

Generate the latest daily inventory CSV:

```bash
python main.py --output output/products.csv
```

Build/update weekly history files from the latest daily CSV:

```bash
python weekly_history.py
```

Optional debug logging:

```bash
python main.py --verbose
```

## Weekly Snapshot Rules

- Monday:
  - if all item inventories are numeric zero, do not save the weekly snapshot yet
  - create `output/state/pending_weekly_snapshot.json`
- Tuesday:
  - if Monday was pending and Tuesday inventory is valid, save Tuesday's data under Monday's `week_date`
  - if Monday and Tuesday are both all-zero, mark that week as skipped
- Wednesday or later:
  - any stale pending week is closed as skipped

When a new calendar year starts:

- the previous year's weekly snapshots are moved into `output/archive/yearly/YYYY/snapshots/`
- yearly `weekly_inventory_long.csv`, `weekly_inventory_wide.csv`, and `weekly_snapshot_status.csv` are written inside that year archive folder
- the live Google Sheet and root `output/weekly_*.csv` files continue with the current year only

Missing history values:

- if a product did not exist in a previous week, history files use `N/A`
- if a product existed and inventory was zero, the value stays `0`
- legacy non-Monday archive files are ignored when rebuilding weekly history

## GitHub Actions

The workflow at [weekly_scraper.yml](.github/workflows/weekly_scraper.yml) runs every day at `09:57 UTC` (`15:27 IST`) and can also be triggered manually.

Each run:

1. Scrapes the latest inventory into `output/products.csv`
2. Writes `output/last_updated_ist.txt`
3. Builds weekly history files with `python weekly_history.py`
4. Pushes the CSV outputs to Google Sheets with `python google_sheets_sync.py`
5. Commits generated repo artifacts back to the default branch when data changed

## Google Sheets Setup

This repo pushes data to one Google spreadsheet with four tabs:

- `Current Inventory`
- `Weekly History Long`
- `Weekly History Wide`
- `Snapshot Status`

### 1. Create a Google Cloud project

1. Open Google Cloud Console
2. Create a new project or pick an existing one
3. Go to `APIs & Services -> Library`
4. Enable `Google Sheets API`
5. Go to `IAM & Admin -> Service Accounts`
6. Click `Create Service Account`
7. Give it any name, then finish creation
8. Open that service account
9. Go to the `Keys` tab
10. Click `Add Key -> Create new key -> JSON`
11. Download the JSON file

The full contents of that downloaded JSON file are what you put into the GitHub secret `GOOGLE_SERVICE_ACCOUNT_JSON`.

### 2. Create the target spreadsheet

- Open Google Sheets
- Create a spreadsheet for the team
- Share the spreadsheet with the service account email from the JSON key
  - give it Editor access

How to get the spreadsheet ID:

- open the Google Sheet in your browser
- the URL looks like:

```text
https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit#gid=0
```

- copy the part between `/d/` and `/edit`
- that value goes into the GitHub secret `GOOGLE_SHEETS_SPREADSHEET_ID`

### 3. Add GitHub repository secrets

Add these Actions secrets in the GitHub repository:

- `GOOGLE_SHEETS_SPREADSHEET_ID`
  - the spreadsheet id from the Google Sheets URL
- `GOOGLE_SERVICE_ACCOUNT_JSON`
  - the full JSON key content for the service account

The workflow will fail with a clear error if either secret is missing.

## Notes

- The Google Sheets sync overwrites each target tab on every run
- The first row in each tab is always the CSV header row
- Weekly history tracks inventory only; price history is not stored in the weekly outputs
