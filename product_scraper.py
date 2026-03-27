from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from http_client import HttpClient
from models import ProductRecord, ProductSeed

_ITEM_ID_RE = re.compile(r"Item\s*ID\s*:\s*([A-Za-z0-9\-]+)", re.IGNORECASE)
_PRICE_RE = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)")


def scrape_product_page(client: HttpClient, seed: ProductSeed) -> Optional[ProductRecord]:
    try:
        response = client.get(seed.product_url)
    except Exception as exc:  # noqa: BLE001
        logging.warning("Product fetch exception %s: %s", seed.product_url, exc)
        return None

    if response.status_code != 200:
        logging.warning("Product fetch failed %s [%s]", seed.product_url, response.status_code)
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    product_name = _extract_name(soup)
    product_id = _extract_item_id(soup, response.text)
    price = _extract_price(soup, response.text)
    sku = _extract_sku(soup, response.text) or product_id

    if not product_id or not product_name:
        logging.warning(
            "Missing critical fields for %s (id=%s, name=%s)",
            seed.product_url,
            bool(product_id),
            bool(product_name),
        )
        return None

    return ProductRecord(
        category_url=seed.category_url,
        category_name=_category_name_from_url(seed.category_url),
        product_url=seed.product_url,
        product_id=product_id,
        product_name=product_name,
        price=price,
        sku=sku,
    )


def _extract_name(soup: BeautifulSoup) -> Optional[str]:
    title = soup.select_one(".page-title span, h1 span, h1")
    if title and title.get_text(strip=True):
        return title.get_text(" ", strip=True)

    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        return title_tag.get_text(" ", strip=True)

    for script in soup.select('script[type="application/ld+json"]'):
        text = script.string or script.get_text(strip=True)
        if not text:
            continue
        try:
            data = json.loads(text)
        except Exception:  # noqa: BLE001
            continue

        name = _dig_json_name(data)
        if name:
            return name.strip()

    # Analytics payload fallback used on this site.
    body_text = soup.get_text(" ", strip=True)
    match = re.search(r'"item_name"\s*:\s*"([^"]+)"', body_text)
    if match:
        return match.group(1).strip()
    return None


def _dig_json_name(data: object) -> Optional[str]:
    if isinstance(data, dict):
        if isinstance(data.get("name"), str):
            return data["name"]
        for value in data.values():
            found = _dig_json_name(value)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _dig_json_name(item)
            if found:
                return found
    return None


def _extract_item_id(soup: BeautifulSoup, html: str) -> Optional[str]:
    item_node = soup.select_one(".Itemid")
    if item_node and item_node.get_text(strip=True):
        return item_node.get_text(strip=True)

    match = _ITEM_ID_RE.search(html)
    if match:
        return match.group(1).strip()

    data_sku = soup.select_one("#check-inventory[data-sku]")
    if data_sku:
        sku = data_sku.get("data-sku")
        if sku:
            return sku.strip()

    return None


def _extract_sku(soup: BeautifulSoup, html: str) -> Optional[str]:
    data_sku = soup.select_one("#check-inventory[data-sku]")
    if data_sku:
        sku = data_sku.get("data-sku")
        if sku:
            return sku.strip()

    match = re.search(r'"sku"\s*:\s*"([A-Za-z0-9\-]+)"', html)
    if match:
        return match.group(1).strip()

    return None


def _extract_price(soup: BeautifulSoup, html: str) -> Optional[Decimal]:
    # Preferred: explicit price element.
    price_node = soup.select_one("#unit_price #price")
    if price_node:
        data_price = price_node.get("data-price")
        if data_price:
            parsed = _to_decimal(data_price)
            if parsed is not None:
                return parsed

        text_price = _extract_money_from_text(price_node.get_text(" ", strip=True))
        if text_price is not None:
            return text_price

    # Fallback: page-level money parsing near pricing area.
    scoped = soup.select_one(".product-price, .our-price-wrapper")
    if scoped:
        parsed = _extract_money_from_text(scoped.get_text(" ", strip=True))
        if parsed is not None:
            return parsed

    # Final fallback: regex over raw HTML.
    return _extract_money_from_text(html)


def _extract_money_from_text(text: str) -> Optional[Decimal]:
    match = _PRICE_RE.search(text or "")
    if not match:
        return None
    return _to_decimal(match.group(1).replace(",", ""))


def _to_decimal(value: str) -> Optional[Decimal]:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def _category_name_from_url(category_url: str) -> str:
    parsed = urlparse(category_url)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        logging.warning("Unable to parse category name from URL: %s", category_url)
        return "unknown"
    return segments[-1].strip().lower() or "unknown"
