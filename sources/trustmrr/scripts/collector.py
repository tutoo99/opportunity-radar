#!/usr/bin/env python3
"""
TrustMRR collector for opportunity-radar.

Collects verified startup revenue data through the official TrustMRR API and
normalizes it into the shared opportunity-radar JSON shape.

Required:
    export TRUSTMRR_API_KEY="tmrr_..."

Usage:
    python scripts/collector.py
    python scripts/collector.py --on-sale true --sort best-deal --fetch-details 20
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx


API_BASE = "https://trustmrr.com/api/v1"
MARKETPLACE_BASE = "https://trustmrr.com/startup"
MAX_API_LIMIT = 50
DEFAULT_MAX_ITEMS = 100
RATE_LIMIT_SLEEP_SECONDS = 3

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SOURCE_DIR, "data")
LATEST_PATH = os.path.join(DATA_DIR, "latest.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("trustmrr-collector")


def now_iso() -> str:
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).isoformat()


def cents_from_usd(value: float | None) -> int | None:
    if value is None:
        return None
    return int(round(value * 100))


def fmt_usd_cents(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"${int(value) / 100:,.0f}"
    except (TypeError, ValueError):
        return "N/A"


def fmt_percent(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"

    return f"{numeric:.1f}%"


def clean_tags(values: list[Any]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        tags.append(text)
        seen.add(text)
    return tags


def normalize_tech_stack(startup: dict[str, Any]) -> list[str]:
    tech_stack = startup.get("techStack")
    if not isinstance(tech_stack, list):
        return []

    techs: list[str] = []
    for tech in tech_stack:
        if not isinstance(tech, dict):
            continue
        slug = tech.get("slug")
        category = tech.get("category")
        if slug and category:
            techs.append(f"{slug} ({category})")
        elif slug:
            techs.append(str(slug))
    return techs


def normalize_startup(startup: dict[str, Any]) -> dict[str, Any]:
    slug = str(startup.get("slug") or startup.get("name") or "").strip()
    name = str(startup.get("name") or slug or "unknown").strip()
    description = str(startup.get("description") or "").strip()
    revenue = startup.get("revenue") if isinstance(startup.get("revenue"), dict) else {}
    url = f"{MARKETPLACE_BASE}/{slug}" if slug else "https://trustmrr.com/"
    x_handle = startup.get("xHandle")
    founder = f"@{x_handle}" if x_handle else ""
    techs = normalize_tech_stack(startup)

    collected_tags = clean_tags(
        [
            startup.get("category"),
            startup.get("paymentProvider"),
            startup.get("targetAudience"),
            startup.get("country"),
            "on_sale" if startup.get("onSale") else "not_for_sale",
            *techs[:10],
        ]
    )

    raw_lines = [
        f"Name: {name}",
        f"Description: {description or 'N/A'}",
        f"Category: {startup.get('category') or 'N/A'}",
        f"Target audience: {startup.get('targetAudience') or 'N/A'}",
        f"Website: {startup.get('website') or 'N/A'}",
        f"Founder X: {founder or 'N/A'}",
        f"Payment provider: {startup.get('paymentProvider') or 'N/A'}",
        f"Last 30 days revenue: {fmt_usd_cents(revenue.get('last30Days'))}",
        f"MRR: {fmt_usd_cents(revenue.get('mrr'))}",
        f"All-time revenue: {fmt_usd_cents(revenue.get('total'))}",
        f"Customers: {startup.get('customers') if startup.get('customers') is not None else 'N/A'}",
        "Active subscriptions: "
        f"{startup.get('activeSubscriptions') if startup.get('activeSubscriptions') is not None else 'N/A'}",
        f"30d revenue growth: {fmt_percent(startup.get('growth30d'))}",
        f"30d MRR growth: {fmt_percent(startup.get('growthMRR30d'))}",
        f"Profit margin last 30 days: {fmt_percent(startup.get('profitMarginLast30Days'))}",
        f"Visitors last 30 days: {startup.get('visitorsLast30Days') or 'N/A'}",
        f"Revenue per visitor: {startup.get('revenuePerVisitor') or 'N/A'}",
        f"Google search impressions: {startup.get('googleSearchImpressionsLast30Days') or 'N/A'}",
        f"On sale: {bool(startup.get('onSale'))}",
        f"Asking price: {fmt_usd_cents(startup.get('askingPrice'))}",
        f"Revenue multiple: {startup.get('multiple') if startup.get('multiple') is not None else 'N/A'}",
    ]
    if techs:
        raw_lines.append("Tech stack: " + ", ".join(techs))

    item_type = "startup_for_sale" if startup.get("onSale") else "verified_revenue"
    title = f"{name} - {description}" if description else name

    images: list[str] = []
    icon = startup.get("icon")
    if isinstance(icon, str) and icon.startswith("http"):
        images.append(icon)

    return {
        "id": slug,
        "title": title,
        "url": url,
        "score": revenue.get("last30Days") or revenue.get("mrr") or 0,
        "comments_count": startup.get("customers") or startup.get("activeSubscriptions") or 0,
        "author": x_handle or "",
        "type": item_type,
        "raw_text": "\n".join(raw_lines),
        "images": images,
        "collected_tags": collected_tags,
        "_trustmrr": startup,
    }


def request_json(
    client: httpx.Client,
    path: str,
    api_key: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{API_BASE}{path}"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    for attempt in range(1, 4):
        response = client.get(url, params=params, headers=headers)
        if response.status_code == 429:
            reset = response.headers.get("X-RateLimit-Reset")
            sleep_seconds = RATE_LIMIT_SLEEP_SECONDS
            if reset and reset.isdigit():
                sleep_seconds = max(sleep_seconds, int(reset) - int(time.time()) + 1)
            log.warning("Rate limited. Sleeping %ss before retry.", sleep_seconds)
            time.sleep(sleep_seconds)
            continue

        if response.status_code == 401:
            raise RuntimeError("TrustMRR API returned 401. Check TRUSTMRR_API_KEY.")

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if attempt >= 3:
                raise RuntimeError(f"TrustMRR API request failed: {exc}") from exc
            log.warning("Request failed (%s). Retrying attempt %d/3.", exc, attempt + 1)
            time.sleep(1.5 * attempt)
            continue

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("TrustMRR API returned a non-object JSON payload.")
        return payload

    raise RuntimeError("TrustMRR API request failed after retries.")


def build_list_params(args: argparse.Namespace, page: int, limit: int) -> dict[str, Any]:
    params: dict[str, Any] = {
        "page": page,
        "limit": limit,
        "sort": args.sort,
    }

    optional_params = {
        "onSale": args.on_sale,
        "category": args.category,
        "xHandle": args.x_handle,
        "minRevenue": cents_from_usd(args.min_revenue_usd),
        "maxRevenue": cents_from_usd(args.max_revenue_usd),
        "minMrr": cents_from_usd(args.min_mrr_usd),
        "maxMrr": cents_from_usd(args.max_mrr_usd),
        "minGrowth": args.min_growth,
        "maxGrowth": args.max_growth,
        "minPrice": cents_from_usd(args.min_price_usd),
        "maxPrice": cents_from_usd(args.max_price_usd),
    }
    params.update({key: value for key, value in optional_params.items() if value is not None})
    return params


def collect_list(client: httpx.Client, api_key: str, args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    startups: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    page = 1
    page_size = min(args.page_size, MAX_API_LIMIT)

    while len(startups) < args.max_items:
        limit = min(page_size, args.max_items - len(startups))
        params = build_list_params(args, page, limit)
        log.info("Fetching page %d (%s items max) ...", page, limit)
        payload = request_json(client, "/startups", api_key, params=params)

        data = payload.get("data", [])
        meta = payload.get("meta", {})
        if not isinstance(data, list):
            raise RuntimeError("TrustMRR list response data field is not a list.")
        if not isinstance(meta, dict):
            meta = {}

        startups.extend([item for item in data if isinstance(item, dict)])
        pages.append({"page": page, "count": len(data), "meta": meta})
        log.info("  Page %d returned %d startup(s).", page, len(data))

        if not meta.get("hasMore") or not data:
            break
        page += 1
        time.sleep(args.request_delay)

    fetch_meta = {
        "pages": pages,
        "returned": len(startups),
        "total": pages[-1]["meta"].get("total") if pages else len(startups),
    }
    return startups, fetch_meta


def enrich_details(
    client: httpx.Client,
    api_key: str,
    startups: list[dict[str, Any]],
    fetch_details: int,
    request_delay: float,
) -> list[dict[str, Any]]:
    if fetch_details <= 0:
        return startups

    enriched: list[dict[str, Any]] = []
    detail_limit = min(fetch_details, len(startups))
    detail_by_slug: dict[str, dict[str, Any]] = {}

    for idx, startup in enumerate(startups[:detail_limit], 1):
        slug = startup.get("slug")
        if not slug:
            continue
        log.info("Fetching details %d/%d: %s", idx, detail_limit, slug)
        payload = request_json(client, f"/startups/{slug}", api_key)
        detail = payload.get("data")
        if isinstance(detail, dict):
            detail_by_slug[str(slug)] = detail
        time.sleep(request_delay)

    for startup in startups:
        slug = str(startup.get("slug") or "")
        enriched.append(detail_by_slug.get(slug, startup))
    return enriched


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect TrustMRR verified startup revenue data.")
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS, help="Maximum list items to collect.")
    parser.add_argument("--page-size", type=int, default=50, help="API page size, max 50.")
    parser.add_argument("--fetch-details", type=int, default=0, help="Fetch detail endpoint for top N results.")
    parser.add_argument("--sort", default="revenue-desc", help="TrustMRR sort option.")
    parser.add_argument("--on-sale", choices=["true", "false"], help="Filter by sale status.")
    parser.add_argument("--category", help="Filter by TrustMRR category slug.")
    parser.add_argument("--x-handle", help="Filter by founder X handle, without @.")
    parser.add_argument("--min-revenue-usd", type=float, help="Minimum last-30-days revenue in USD.")
    parser.add_argument("--max-revenue-usd", type=float, help="Maximum last-30-days revenue in USD.")
    parser.add_argument("--min-mrr-usd", type=float, help="Minimum MRR in USD.")
    parser.add_argument("--max-mrr-usd", type=float, help="Maximum MRR in USD.")
    parser.add_argument("--min-growth", type=float, help="Minimum 30-day revenue growth.")
    parser.add_argument("--max-growth", type=float, help="Maximum 30-day revenue growth.")
    parser.add_argument("--min-price-usd", type=float, help="Minimum asking price in USD.")
    parser.add_argument("--max-price-usd", type=float, help="Maximum asking price in USD.")
    parser.add_argument("--request-delay", type=float, default=0.5, help="Delay between API requests.")
    parser.add_argument("--output", default=LATEST_PATH, help="Normalized output JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("TRUSTMRR_API_KEY", "").strip()
    if not api_key:
        log.error("Missing TRUSTMRR_API_KEY. Create an API key in TrustMRR developer dashboard first.")
        return 2

    if args.max_items < 1:
        log.error("--max-items must be at least 1.")
        return 2
    if args.page_size < 1 or args.page_size > MAX_API_LIMIT:
        log.error("--page-size must be between 1 and %d.", MAX_API_LIMIT)
        return 2

    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        startups, fetch_meta = collect_list(client, api_key, args)
        startups = enrich_details(client, api_key, startups, args.fetch_details, args.request_delay)

    items = [normalize_startup(startup) for startup in startups]
    result = {
        "source": "trustmrr",
        "collected_at": now_iso(),
        "items": items,
        "meta": {
            "api_base": API_BASE,
            "marketplace_base": MARKETPLACE_BASE,
            "fetch": fetch_meta,
            "sort": args.sort,
            "filters": {
                "on_sale": args.on_sale,
                "category": args.category,
                "x_handle": args.x_handle,
                "min_revenue_usd": args.min_revenue_usd,
                "max_revenue_usd": args.max_revenue_usd,
                "min_mrr_usd": args.min_mrr_usd,
                "max_mrr_usd": args.max_mrr_usd,
                "min_growth": args.min_growth,
                "max_growth": args.max_growth,
                "min_price_usd": args.min_price_usd,
                "max_price_usd": args.max_price_usd,
            },
            "fetch_details": args.fetch_details,
        },
    }

    snapshot_path = os.path.join(DATA_DIR, f"trustmrr_{timestamp}.json")
    raw_path = os.path.join(DATA_DIR, f"raw_{timestamp}.json")

    for path, payload in (
        (args.output, result),
        (snapshot_path, result),
        (raw_path, {"source": "trustmrr", "collected_at": now_iso(), "meta": fetch_meta, "startups": startups}),
    ):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

    log.info("Done. Wrote %d item(s).", len(items))
    log.info("Latest: %s", args.output)
    log.info("Snapshot: %s", snapshot_path)
    log.info("Raw: %s", raw_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
