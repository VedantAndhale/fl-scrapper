# Flooring Liquidators Prefab Countertop Scraper

Scrapes product data and live inventory from:

- Quartz
- Granite
- Marble
- Quartzite

## Output

CSV columns:

- `product_id`
- `product_name`
- `price`
- `inventory`
- `category_name`

`inventory` is pulled from the live endpoint used by **Check Live Inventory**.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python main.py --output output/products.csv
```

Optional:

```bash
python main.py --verbose
```

## Weekly Automation (GitHub Actions)

This repo includes a workflow at `.github/workflows/weekly_scraper.yml` that:

- Runs every Monday at **09:00 IST** (`30 3 * * 1` UTC)
- Can also be triggered manually from GitHub Actions UI
- Regenerates `output/products.csv`
- Writes `output/last_updated_ist.txt` as `YYYY-MM-DD HH:mm:ss IST`
- Saves weekly snapshots to `output/archive/products_YYYY-MM-DD.csv`
- Keeps only the latest **13** snapshots (one quarter)

### Google Sheet Formulas

Use these formulas in your shared sheet:

- `A1`: `Last Updated (IST)`
- `B1`:

```gs
=INDEX(IMPORTDATA("https://raw.githubusercontent.com/<user>/<repo>/<branch>/output/last_updated_ist.txt"),1,1)
```

- `A3`:

```gs
=IMPORTDATA("https://raw.githubusercontent.com/<user>/<repo>/<branch>/output/products.csv")
```

Replace `<user>` and `<repo>` with your GitHub repository path.
