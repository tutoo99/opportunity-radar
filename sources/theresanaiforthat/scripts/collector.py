#!/usr/bin/env python3
"""
ThereIsAnAIForThat weekly trending collector for opportunity-radar.

Loads the public weekly trending page and parses the static DOM under:
    //div[@id="data_hist"]/ul[@class="tasks"]

No /api/ endpoints are called.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any
from urllib.parse import urljoin

from lxml import html as lxml_html


SOURCE = "theresanaiforthat"
TRENDING_URL = "https://theresanaiforthat.com/trending/week/"
SITE_BASE = "https://theresanaiforthat.com"
DEFAULT_BROWSER_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SOURCE_DIR, "data")
LATEST_PATH = os.path.join(DATA_DIR, "latest.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("taaft-weekly-collector")


def now_iso() -> str:
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).isoformat()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return unescape(text).strip()


def first_text(node: Any, xpath: str) -> str:
    values = node.xpath(xpath)
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return ""


def first_attr(node: Any, xpath: str, attr: str) -> str:
    values = node.xpath(xpath)
    for value in values:
        if hasattr(value, "get"):
            text = clean_text(value.get(attr))
            if text:
                return text
    return ""


def normalize_url(url: str) -> str:
    text = clean_text(url)
    if not text:
        return ""
    return urljoin(SITE_BASE, text)


def parse_number(text: Any) -> int:
    value = clean_text(text).lower().replace(",", "")
    if not value:
        return 0

    match = re.search(r"([\d.]+)\s*([km])?", value)
    if not match:
        return 0

    number = float(match.group(1))
    suffix = match.group(2)
    if suffix == "k":
        number *= 1_000
    elif suffix == "m":
        number *= 1_000_000
    return int(number)


def parse_float(text: Any) -> float | None:
    value = clean_text(text).replace(",", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", value)
    if not match:
        return None
    return float(match.group(0))


def extract_slug(tool_path: str) -> str:
    path = clean_text(tool_path)
    match = re.search(r"/ai/([^/]+)/?", path)
    return match.group(1) if match else ""


def collect_tags(*values: Any) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, (list, tuple)):
            candidates = value
        else:
            candidates = [value]
        for candidate in candidates:
            tag = clean_text(candidate)
            if not tag or tag in seen:
                continue
            tags.append(tag)
            seen.add(tag)
    return tags


def parse_comment(li: Any) -> dict[str, Any]:
    comment = li.xpath('.//div[contains(concat(" ", normalize-space(@class), " "), " comment ")]')
    if not comment:
        return {}
    node = comment[0]

    upvotes = parse_number(first_text(node, './/*[contains(concat(" ", normalize-space(@class), " "), " comment_upvote ")]/text()'))
    downvotes = parse_number(first_text(node, './/*[contains(concat(" ", normalize-space(@class), " "), " comment_downvote ")]/text()'))

    return {
        "id": clean_text(node.get("data-id")),
        "user_id": clean_text(node.get("data-user")),
        "user_name": first_text(node, './/*[contains(concat(" ", normalize-space(@class), " "), " user_name ")]/text()'),
        "user_profile_url": normalize_url(first_attr(node, './/a[contains(concat(" ", normalize-space(@class), " "), " user_card ")]', "href")),
        "date": first_text(node, './/*[contains(concat(" ", normalize-space(@class), " "), " comment_date ")]//a/text()'),
        "url": normalize_url(first_attr(node, './/*[contains(concat(" ", normalize-space(@class), " "), " comment_date ")]//a', "href")),
        "body": first_text(node, './/*[contains(concat(" ", normalize-space(@class), " "), " comment_body ")]/text()'),
        "upvotes": upvotes,
        "downvotes": downvotes,
    }


def parse_li(li: Any, index: int) -> dict[str, Any] | None:
    data_id = clean_text(li.get("data-id"))
    data_name = clean_text(li.get("data-name"))
    task = clean_text(li.get("data-task"))
    task_id = clean_text(li.get("data-task_id"))
    external_url = normalize_url(li.get("data-url") or "")
    rank = clean_text(li.get("data-rank"))
    task_slug = clean_text(li.get("data-task_slug"))

    tool_path = first_attr(li, './/a[contains(concat(" ", normalize-space(@class), " "), " ai_link ")]', "href")
    tool_url = normalize_url(tool_path)
    slug = extract_slug(tool_path)

    name = data_name or first_text(li, './/a[contains(concat(" ", normalize-space(@class), " "), " ai_link ")]//span/text()')
    if not name:
        return None

    description = first_text(li, './/*[contains(concat(" ", normalize-space(@class), " "), " short_desc ")]/text()')
    task_label = first_text(li, './/a[contains(concat(" ", normalize-space(@class), " "), " task_label ")]/text()')
    task_url = normalize_url(first_attr(li, './/a[contains(concat(" ", normalize-space(@class), " "), " task_label ")]', "href"))
    task_icon = first_attr(li, './/a[contains(concat(" ", normalize-space(@class), " "), " task_label ")]', "data-before")

    icon_url = normalize_url(first_attr(li, './/img[contains(concat(" ", normalize-space(@class), " "), " taaft_icon ")]', "src"))
    release_age = first_text(li, './/*[contains(concat(" ", normalize-space(@class), " "), " released ")]/span[contains(concat(" ", normalize-space(@class), " "), " relative ")]/text()')
    pricing = first_text(li, './/a[contains(concat(" ", normalize-space(@class), " "), " ai_launch_date ")]/text()')
    pricing_url = normalize_url(first_attr(li, './/a[contains(concat(" ", normalize-space(@class), " "), " ai_launch_date ")]', "href"))

    views = parse_number(first_text(li, './/*[contains(concat(" ", normalize-space(@class), " "), " stats_views ")]//span/text()'))
    saves = parse_number(first_text(li, './/*[contains(concat(" ", normalize-space(@class), " "), " saves ")]/text()'))
    rating = parse_float(first_text(li, './/*[contains(concat(" ", normalize-space(@class), " "), " average_rating ")]/text()'))

    comment = parse_comment(li)
    comments_count = 1 if comment.get("body") else 0

    tags = collect_tags(task_label, task, task_slug, "weekly_trending")
    images = [icon_url] if icon_url else []
    title = f"{name} - {description}" if description else name

    raw_lines = [
        f"Rank: {rank or index + 1}",
        f"Name: {name}",
        f"Description: {description or 'N/A'}",
        f"Task: {task_label or task or 'N/A'}",
        f"Pricing: {pricing or 'N/A'}",
        f"Released: {release_age or 'N/A'}",
        f"Views: {views:,}" if views else "Views: N/A",
        f"Saves: {saves:,}" if saves else "Saves: N/A",
        f"Rating: {rating}" if rating is not None else "Rating: N/A",
        f"External URL: {external_url or 'N/A'}",
    ]
    if comment.get("body"):
        raw_lines.extend(
            [
                f"Featured comment user: {comment.get('user_name') or 'N/A'}",
                f"Featured comment date: {comment.get('date') or 'N/A'}",
                f"Featured comment: {comment.get('body')}",
                f"Comment votes: +{comment.get('upvotes', 0)} / -{comment.get('downvotes', 0)}",
            ]
        )

    return {
        "id": data_id or slug or name,
        "title": title,
        "url": tool_url or external_url or TRENDING_URL,
        "score": views,
        "comments_count": comments_count,
        "author": comment.get("user_name", ""),
        "type": "ai_tool",
        "raw_text": "\n".join(raw_lines),
        "images": images,
        "collected_tags": tags,
        "_theresanaiforthat": {
            "id": data_id,
            "name": name,
            "slug": slug,
            "rank": rank,
            "task": task,
            "task_id": task_id,
            "task_slug": task_slug,
            "task_label": task_label,
            "task_icon": task_icon,
            "task_url": task_url,
            "tool_url": tool_url,
            "external_url": external_url,
            "icon_url": icon_url,
            "description": description,
            "release_age": release_age,
            "pricing": pricing,
            "pricing_url": pricing_url,
            "views": views,
            "saves": saves,
            "rating": rating,
            "featured_comment": comment,
        },
    }


def parse_html(page_html: str, max_items: int | None = None) -> list[dict[str, Any]]:
    doc = lxml_html.fromstring(page_html)
    lis = doc.xpath('//div[@id="data_hist"]/ul[contains(concat(" ", normalize-space(@class), " "), " tasks ")]/li')
    if not lis:
        lis = doc.xpath('//ul[contains(concat(" ", normalize-space(@class), " "), " tasks ")]/li')

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, li in enumerate(lis):
        if max_items is not None and len(items) >= max_items:
            break
        item = parse_li(li, index)
        if not item:
            continue
        item_id = str(item["id"])
        if item_id in seen:
            continue
        seen.add(item_id)
        items.append(item)
    return items


def fetch_page_html(args: argparse.Namespace) -> str:
    from DrissionPage import ChromiumOptions, ChromiumPage

    options = ChromiumOptions()
    browser_path = args.browser_path or next((path for path in DEFAULT_BROWSER_PATHS if os.path.exists(path)), "")
    if browser_path:
        options.set_browser_path(browser_path)
    options.auto_port()
    options.headless(args.headless)
    if args.headless:
        options.set_argument("--headless", "new")
    options.set_argument("--disable-blink-features=AutomationControlled")
    options.set_argument("--window-size", "1440,1200")
    options.set_user_agent(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    )
    if args.user_data_path:
        options.set_user_data_path(os.path.abspath(args.user_data_path))

    page = ChromiumPage(options, timeout=args.timeout)
    try:
        log.info("Opening %s", TRENDING_URL)
        page.get(TRENDING_URL)
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            html_text = page.html
            if 'id="data_hist"' in html_text and 'class="tasks"' in html_text:
                return html_text
            if "Just a moment" in html_text or "cf_chl" in html_text:
                log.info("Cloudflare challenge page detected; waiting for browser challenge to settle ...")
            time.sleep(2)

        html_text = page.html
        if "Just a moment" in html_text or "cf_chl" in html_text:
            raise RuntimeError(
                "Cloudflare challenge did not clear before timeout. "
                "Run with --no-headless, wait for the page to load, then retry with --user-data-path."
            )
        return html_text
    finally:
        if not args.keep_browser_open:
            try:
                page.quit()
            except Exception:
                pass


def write_json(path: str, payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect ThereIsAnAIForThat weekly trending AI tools.")
    parser.add_argument("--max-items", type=int, default=None, help="Maximum list items to parse.")
    parser.add_argument("--html-file", help="Parse a local HTML file instead of launching a browser.")
    parser.add_argument("--save-html", help="Save fetched HTML to this path.")
    parser.add_argument("--output", default=LATEST_PATH, help="Normalized output JSON path.")
    parser.add_argument("--timeout", type=int, default=60, help="Page load/challenge timeout in seconds.")
    parser.add_argument("--browser-path", help="Path to Chrome/Chromium executable.")
    parser.add_argument("--headless", dest="headless", action="store_true", default=True, help="Run browser headless.")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Run browser visibly.")
    parser.add_argument("--keep-browser-open", action="store_true", help="Leave browser open after collection.")
    parser.add_argument("--user-data-path", help="Chromium user data path for reusing solved browser sessions.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_items is not None and args.max_items < 1:
        log.error("--max-items must be at least 1.")
        return 2

    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.html_file:
        log.info("Reading local HTML: %s", args.html_file)
        with open(args.html_file, "r", encoding="utf-8") as fh:
            page_html = fh.read()
    else:
        page_html = fetch_page_html(args)

    if args.save_html:
        html_path = args.save_html
    elif not args.html_file:
        html_path = os.path.join(DATA_DIR, f"raw_{timestamp}.html")
    else:
        html_path = ""

    if html_path:
        os.makedirs(os.path.dirname(os.path.abspath(html_path)), exist_ok=True)
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(page_html)
        log.info("Raw HTML: %s", html_path)

    items = parse_html(page_html, args.max_items)
    if not items:
        log.error("No tools found under #data_hist ul.tasks.")
        return 1

    result = {
        "source": SOURCE,
        "collected_at": now_iso(),
        "items": items,
        "meta": {
            "url": TRENDING_URL,
            "period": "week",
            "parser": "#data_hist ul.tasks > li",
            "count": len(items),
        },
    }

    snapshot_path = os.path.join(DATA_DIR, f"theresanaiforthat_week_{timestamp}.json")
    write_json(args.output, result)
    write_json(snapshot_path, result)

    log.info("Done. Wrote %d item(s).", len(items))
    log.info("Latest: %s", args.output)
    log.info("Snapshot: %s", snapshot_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
