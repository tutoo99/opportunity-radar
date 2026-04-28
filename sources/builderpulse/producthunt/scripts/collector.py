#!/usr/bin/env python3
"""
Product Hunt Collector — Opportunity Radar
Collects top products from the daily homepage feed using ruyiPage.

Strategy: Load producthunt.com homepage, extract ApolloSSRDataTransport JSON
embedded in the HTML by React/Apollo SSR. This gives us all product data
(name, tagline, upvotes, comments, topics, rank) without needing to parse
the DOM at all.

Usage:
    python collector.py
"""

from __future__ import annotations

import json
import os
import re
import time
import logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("producthunt-collector")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HOMEPAGE_URL = "https://www.producthunt.com/"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "latest.json")
MAX_PRODUCTS = 30
TOP_N_COMMENTS = 5  # collect comments for top N products
COMMENTS_PER_PRODUCT = 5
NAVIGATE_DELAY = 3  # seconds between product page navigations


def now_iso() -> str:
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def safe_int(text: str) -> int:
    """Extract an integer from a string like '448 upvotes' or '1,024'."""
    if not text:
        return 0
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else 0


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def extract_rehydrate_json(html):
    """Extract the ApolloSSRDataTransport rehydrate JSON from page HTML.

    Product Hunt embeds GraphQL query results in a JSON blob using
    window[Symbol.for("ApolloSSRDataTransport")] which contains a 'rehydrate'
    key with all query data. The homefeed query has today's top products.

    The JSON uses JavaScript 'undefined' literals which we replace with null.
    """
    idx = html.find('"rehydrate":{')
    if idx < 0:
        return None

    start = idx + len('"rehydrate":')
    depth = 0
    end = start
    for i in range(start, min(len(html), start + 10_000_000)):
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    else:
        return None

    json_str = html[start:end].replace("undefined", "null")

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def parse_homefeed_posts(rehydrate_data):
    """Extract post data from the homefeed query result.

    Returns a list of dicts with: name, slug, tagline, dailyRank, latestScore,
    commentsCount, topics, shortenedUrl, etc.
    """
    posts = []
    for key, val in rehydrate_data.items():
        inner = val.get("data", {})
        if not isinstance(inner, dict):
            continue
        if "homefeed" not in inner:
            continue

        edges = inner["homefeed"].get("edges", [])
        for edge in edges:
            node = edge.get("node", {})
            items = node.get("items", [])
            for item in items:
                if item.get("__typename") != "Post":
                    continue
                posts.append(item)

    return posts


# ---------------------------------------------------------------------------
# Main collector
# ---------------------------------------------------------------------------
def collect():
    from ruyipage import launch

    page = launch(headless=True)
    items = []

    try:
        # --- Step 1: Load homepage and extract embedded data -----------------
        log.info("Navigating to Product Hunt homepage ...")
        page.get(HOMEPAGE_URL)
        time.sleep(4)  # wait for React SSR to render

        # Wait for the page to have meaningful content
        try:
            page.ele("css:h3", timeout=15)
            log.info("Homepage loaded.")
        except Exception:
            log.warning("Homepage content not found.")

        # --- Step 2: Parse embedded JSON data --------------------------------
        html = page.html
        rehydrate_data = extract_rehydrate_json(html)

        if not rehydrate_data:
            log.error("Could not extract ApolloSSRDataTransport JSON from page.")
            return items

        posts = parse_homefeed_posts(rehydrate_data)
        if not posts:
            log.error("No posts found in homefeed data.")
            return items

        log.info("Found %d post(s) in homefeed.", len(posts))

        # --- Step 3: Build item records --------------------------------------
        for idx, post in enumerate(posts[:MAX_PRODUCTS]):
            try:
                name = post.get("name", f"unknown-{idx}")
                tagline = post.get("tagline", "") or ""
                slug = post.get("slug", "")
                daily_rank = post.get("dailyRank", "")
                score = safe_int(post.get("latestScore", 0))
                comments_count = safe_int(post.get("commentsCount", 0))

                # Build product URL
                product_slug = post.get("product", {}).get("slug", "")
                if product_slug:
                    url = f"https://www.producthunt.com/products/{product_slug}"
                else:
                    url = f"https://www.producthunt.com/posts/{slug}"

                # Topics / tags
                topic_edges = post.get("topics", {}).get("edges", [])
                topics = [t["node"]["name"] for t in topic_edges if t.get("node")]

                # Featured comment (pinned comment shown on homepage)
                featured = post.get("featuredComment")
                featured_text = ""
                if featured:
                    featured_text = featured.get("bodyText", "")

                # Makers / voters (friend voters for social proof)
                friend_voters = post.get("friendVoters", {})
                voter_names = [
                    v["node"]["name"]
                    for v in friend_voters.get("edges", [])
                    if v.get("node")
                ]

                item = {
                    "id": slugify(name),
                    "title": f"{name} - {tagline}" if tagline else name,
                    "url": url,
                    "score": score,
                    "comments_count": comments_count,
                    "author": voter_names[0] if voter_names else "unknown",
                    "type": "product",
                    "raw_text": tagline,
                    "images": [],
                    "collected_tags": topics,
                    "_comment_texts": [],  # filled below
                    "_post_url": url,
                    "_rank": daily_rank,
                    "_featured_comment": featured_text,
                }
                items.append(item)
                log.info("  [%s] %s — %d upvotes", daily_rank or str(idx + 1), name, score)

            except Exception as exc:
                log.warning("  Failed to parse post %d: %s", idx, exc)
                continue

        # --- Step 4: Collect comments for top products ----------------------
        top_items = [it for it in items if it["_post_url"]][:TOP_N_COMMENTS]
        for rank, item in enumerate(top_items, 1):
            try:
                log.info("Fetching comments for #%s: %s ...", item["_rank"] or rank, item["title"][:60])
                page.get(item["_post_url"])
                time.sleep(4)
                # Scroll to load comments
                page.run_js("window.scrollBy(0, 1200)")
                time.sleep(2)

                # Try multiple selectors for comment bodies
                comment_texts = []
                for sel in [
                    "css:div[class*='commentBody'], div[class*='comment-body']",
                    "css:div[class*='commentContent']",
                    "css:[data-test='comment-body']",
                ]:
                    # Try compound selector parts individually
                    for single_sel in sel.split(", "):
                        try:
                            comment_els = page.eles(single_sel)
                            for c in comment_els[:COMMENTS_PER_PRODUCT]:
                                txt = c.text.strip() if c.text else ""
                                if txt and len(txt) > 5 and txt not in comment_texts:
                                    comment_texts.append(txt)
                        except Exception:
                            pass

                item["_comment_texts"] = comment_texts
                item["comments_count"] = max(item["comments_count"], len(comment_texts))

                # Go back to homepage for next product
                if rank < len(top_items):
                    page.get(HOMEPAGE_URL)
                    time.sleep(NAVIGATE_DELAY)

            except Exception as exc:
                log.warning("  Failed to get comments for %s: %s", item["id"], exc)
                if rank < len(top_items):
                    try:
                        page.get(HOMEPAGE_URL)
                        time.sleep(NAVIGATE_DELAY)
                    except Exception:
                        pass

    except Exception as exc:
        log.error("Fatal error during collection: %s", exc)
    finally:
        try:
            page.quit()
        except Exception:
            pass

    # --- Post-process: build raw_text, clean temp fields -------------------
    for item in items:
        parts = [item["raw_text"]]  # tagline
        if item.get("collected_tags"):
            parts.append(" | ".join(item["collected_tags"]))
        if item.get("_featured_comment"):
            parts.append("Featured: " + item["_featured_comment"])
        comments = item.pop("_comment_texts", [])
        if comments:
            parts.append("Comments: " + " | ".join(comments))
        item["raw_text"] = " | ".join(parts)
        item.pop("_post_url", None)
        item.pop("_rank", None)
        item.pop("_featured_comment", None)

    return items


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    log.info("=== Product Hunt Collector Start ===")
    items = collect()

    payload = {
        "source": "producthunt",
        "collected_at": now_iso(),
        "items": items,
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    log.info("Saved %d items to %s", len(items), OUTPUT_PATH)
    log.info("=== Product Hunt Collector End ===")


if __name__ == "__main__":
    main()
