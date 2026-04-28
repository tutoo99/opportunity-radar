#!/usr/bin/env python3
"""GitHub Trending collector using ruyiPage browser automation.

Collects trending repositories from GitHub trending pages and saves them
to a structured JSON file for the opportunity-radar skill.
"""

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

from ruyipage import launch

# Output path
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "latest.json")

# Trending pages to scrape: (url, max_items)
TRENDING_PAGES = [
    ("https://github.com/trending", 30),
    ("https://github.com/trending/python", 15),
    ("https://github.com/trending/typescript", 15),
]


def parse_number(text: str) -> int:
    """Parse a number string like '5,231' or '1.2k' into an integer."""
    if not text:
        return 0
    text = text.strip().replace(",", "")
    # Handle abbreviated numbers like "1.2k", "523"
    m = re.match(r"([\d.]+)\s*k", text, re.IGNORECASE)
    if m:
        return int(float(m.group(1)) * 1000)
    m = re.match(r"([\d.]+)\s*m", text, re.IGNORECASE)
    if m:
        return int(float(m.group(1)) * 1_000_000)
    m = re.match(r"(\d+)", text)
    if m:
        return int(m.group(1))
    return 0


def scrape_trending_page(page, url: str, max_items: int) -> list:
    """Scrape a single GitHub trending page and return parsed repo items."""
    print(f"  Navigating to {url}")
    page.get(url)
    time.sleep(3)  # Wait for dynamic content

    articles = page.eles("css:article.Box-row")
    if not articles:
        print(f"  WARNING: No article.Box-row elements found on {url}")
        # Try fallback selector
        articles = page.eles("css:[class*='Box-row']")
        if not articles:
            print(f"  ERROR: No trending repos found on {url}")
            return []

    items = []
    seen_ids = set()

    for idx, article in enumerate(articles):
        if idx >= max_items:
            break

        try:
            # Repo name: h2 a href
            name_el = article.ele("css:h2 a")
            if not name_el:
                continue
            href = name_el.attr("href") or ""
            # href is like "/owner/repo"
            repo_name = href.strip("/").strip()
            if not repo_name or "/" not in repo_name:
                continue

            # Skip duplicates across pages
            if repo_name in seen_ids:
                continue
            seen_ids.add(repo_name)

            owner = repo_name.split("/")[0]

            # Description
            desc_el = article.ele("css:p.col-9")
            description = ""
            if desc_el:
                description = (desc_el.text or "").strip()

            # Total stars (the main star count)
            stars_total = 0
            # Stars are typically in a link with href containing "/stargazers"
            star_els = article.eles("css:a[href*='/stargazers']")
            if star_els:
                stars_total = parse_number(star_els[0].text or "")

            # Stars today: look for the yellow star / "today" span
            stars_today = 0
            all_spans = article.eles("css:span")
            for span in all_spans:
                span_text = (span.text or "").strip()
                if "today" in span_text.lower():
                    m = re.search(r"([\d,.]+)\s*(?:★\s*)?today", span_text, re.IGNORECASE)
                    if m:
                        stars_today = parse_number(m.group(1))
                        break

            # Language
            language = ""
            lang_els = article.eles("css:[itemprop='programmingLanguage']")
            if lang_els:
                language = (lang_els[0].text or "").strip()

            # Forks
            forks = 0
            fork_els = article.eles("css:a[href*='/forks']")
            if fork_els:
                forks = parse_number(fork_els[0].text or "")

            # Built by (authors)
            built_by = []
            built_by_els = article.eles("css:img[alt][class*='avatar']")
            for av in built_by_els:
                alt = av.attr("alt") or ""
                if alt.startswith("@"):
                    built_by.append(alt.lstrip("@"))

            # Build collected_tags
            tags = ["trending"]
            if language:
                tags.append(language)

            # Build title
            if description:
                title = f"{repo_name} - {description}"
            else:
                title = repo_name

            # Build raw_text
            raw_parts = []
            if description:
                raw_parts.append(description)
            if language:
                raw_parts.append(language)
            if stars_total:
                raw_parts.append(f"★ {stars_total:,}")
            if forks:
                raw_parts.append(f"⑂ {forks:,}")
            raw_text = " | ".join(raw_parts)

            item = {
                "id": repo_name,
                "title": title,
                "url": f"https://github.com/{repo_name}",
                "score": stars_today,
                "comments_count": 0,
                "author": owner,
                "type": "repo",
                "raw_text": raw_text,
                "images": [],
                "collected_tags": tags,
            }
            items.append(item)

        except Exception as e:
            print(f"  Error parsing article #{idx}: {e}")
            continue

    print(f"  Collected {len(items)} repos from {url}")
    return items


def main():
    """Main entry point: scrape all trending pages and save results."""
    tz = timezone(timedelta(hours=8))
    collected_at = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")

    print(f"[GitHub Trending] Starting collection at {collected_at}")

    page = None
    try:
        page = launch(headless=True)
        all_items = []
        seen_ids = set()

        for url, max_items in TRENDING_PAGES:
            try:
                items = scrape_trending_page(page, url, max_items)
                for item in items:
                    if item["id"] not in seen_ids:
                        seen_ids.add(item["id"])
                        all_items.append(item)
            except Exception as e:
                print(f"  Error scraping {url}: {e}")
            # Rate limit between pages
            time.sleep(2)

        # Deduplicate and sort by score descending
        unique_items = {}
        for item in all_items:
            unique_items[item["id"]] = item
        sorted_items = sorted(
            unique_items.values(), key=lambda x: x["score"], reverse=True
        )

        output = {
            "source": "github-trending",
            "collected_at": collected_at,
            "items": sorted_items,
        }

        os.makedirs(DATA_DIR, exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(
            f"[GitHub Trending] Done: {len(sorted_items)} repos saved to {OUTPUT_PATH}"
        )

    except Exception as e:
        print(f"[GitHub Trending] Fatal error: {e}")
        raise
    finally:
        if page:
            try:
                page.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
