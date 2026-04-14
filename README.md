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
4. Commits generated repo artifacts back to the default branch when data changed

## Google Sheets With Apps Script

This repo does not push directly to Google Sheets anymore.

The current setup is:

- GitHub Actions generates CSV files in the repo
- Google Apps Script pulls those CSV files from GitHub raw URLs
- Apps Script updates one spreadsheet with four tabs

- `Current Inventory`
- `Weekly History Long`
- `Weekly History Wide`
- `Snapshot Status`

### 1. Create the target spreadsheet

- Open Google Sheets
- Create a spreadsheet for the team

How to get the spreadsheet ID:

- open the Google Sheet in your browser
- the URL looks like:

```text
https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit#gid=0
```

- copy the part between `/d/` and `/edit`
- that value goes into the Apps Script constant `SPREADSHEET_ID`

### 2. Add Apps Script

- Open `Extensions -> Apps Script` from the spreadsheet
- Add an Apps Script project bound to that spreadsheet
- Use the script to fetch these files from GitHub:
  - `output/products.csv`
  - `output/weekly_inventory_long.csv`
  - `output/weekly_inventory_wide.csv`
  - `output/weekly_snapshot_status.csv`
  - `output/last_updated_ist.txt`
- Create these sheet tabs:
  - `Current Inventory`
  - `Weekly History Long`
  - `Weekly History Wide`
  - `Snapshot Status`

Use `raw.githubusercontent.com` URLs, not the GitHub API, if you want to avoid PAT/service-account setup.

### 3. Add an Apps Script Trigger

- In Apps Script, add a time-driven trigger for your update function
- Recommended interval: every hour
- The script should compare `last_updated_ist.txt` against the last imported timestamp before rewriting tabs

## Notes

- The repo only generates and archives CSV files
- Google Sheets is updated by Apps Script, not by GitHub Actions
- Weekly history tracks inventory only; price history is not stored in the weekly outputs
- The first row in each sheet tab should remain the CSV header row
