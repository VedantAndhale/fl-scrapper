from __future__ import annotations

import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from config import MAX_PAGINATION_PAGES
from http_client import HttpClient
from models import ProductSeed


def scrape_category_product_urls(client: HttpClient, category_url: str) -> list[ProductSeed]:
    discovered_page_urls = _discover_pagination_pages(client, category_url)
    product_urls: set[str] = set()

    for page_url in discovered_page_urls:
        html = _fetch_html(client, page_url)
        if not html:
            continue
        found = _extract_product_urls(html)
        for product_url in found:
            product_urls.add(_normalize_url(product_url))

    seeds = [
        ProductSeed(category_url=category_url, product_url=url)
        for url in sorted(product_urls)
    ]
    logging.info("Category %s -> %d unique products", category_url, len(seeds))
    return seeds


def _discover_pagination_pages(client: HttpClient, category_url: str) -> list[str]:
    base_html = _fetch_html(client, category_url)
    if not base_html:
        return [category_url]

    pages = {_normalize_url(category_url)}
    soup = BeautifulSoup(base_html, "html.parser")

    # First preference: explicit pagination links in HTML.
    for anchor in soup.select(".pages a[href], .toolbar .pages a[href]"):
        href = anchor.get("href")
        if href:
            pages.add(_normalize_url(href))

    # Fallback: probe ?p=N for categories where pager may be hidden.
    no_result_streak = 0
    for page_num in range(2, MAX_PAGINATION_PAGES + 1):
        candidate = _with_page_param(category_url, page_num)
        html = _fetch_html(client, candidate)
        if not html:
            no_result_streak += 1
            if no_result_streak >= 2:
                break
            continue

        found = _extract_product_urls(html)
        if not found:
            no_result_streak += 1
            if no_result_streak >= 2:
                break
            continue

        no_result_streak = 0
        pages.add(_normalize_url(candidate))

    return sorted(pages)


def _extract_product_urls(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: set[str] = set()

    # Primary selector observed on this site.
    for anchor in soup.select("ol.products.list.items.product-items a.item[href]"):
        href = anchor.get("href")
        if href:
            urls.add(href)

    # Fallback selector for slight layout variations.
    if not urls:
        for anchor in soup.select('a[href*="/countertops/prefab-countertops/"][href$=".html"]'):
            href = anchor.get("href")
            if href:
                urls.add(href)

    return urls


def _fetch_html(client: HttpClient, url: str) -> str:
    try:
        response = client.get(url)
        if response.status_code != 200:
            logging.warning("Listing fetch failed %s [%s]", url, response.status_code)
            return ""
        return response.text
    except Exception as exc:  # noqa: BLE001
        logging.warning("Listing fetch exception %s: %s", url, exc)
        return ""


def _with_page_param(url: str, page_num: int) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["p"] = str(page_num)
    updated = parsed._replace(query=urlencode(query))
    return urlunparse(updated)


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    filtered_query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "___store"]
    normalized = parsed._replace(query=urlencode(sorted(filtered_query)), fragment="")
    return urlunparse(normalized)
