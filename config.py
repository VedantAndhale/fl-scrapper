from __future__ import annotations

CATEGORY_URLS = [
    "https://flooringliquidators.net/countertops/prefab-countertops/quartz",
    "https://flooringliquidators.net/countertops/prefab-countertops/granite",
    "https://flooringliquidators.net/countertops/prefab-countertops/marble",
    "https://flooringliquidators.net/countertops/prefab-countertops/quartzite",
    "https://flooringliquidators.net/countertops/prefab-countertops/engineered-granite",
]

INVENTORY_API_BASE = "https://products.mm-api.agency/fliq/inventory"

DEFAULT_OUTPUT_CSV = "output/products.csv"
REQUEST_TIMEOUT_SECONDS = 25
REQUEST_RETRIES = 3
REQUEST_BACKOFF_SECONDS = 0.8
REQUEST_JITTER_RANGE_SECONDS = (0.15, 0.40)

PRODUCT_WORKERS = 8
INVENTORY_WORKERS = 12
MAX_PAGINATION_PAGES = 50
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
