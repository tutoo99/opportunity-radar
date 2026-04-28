#!/usr/bin/env python3
"""
Hacker News collector for opportunity-radar skill.
Collects top stories, Show HN, and Ask HN posts using the public HN API.
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Union

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "https://hacker-news.firebaseio.com/v0"
TOP_STORIES_COUNT = 30
HIGH_SCORE_THRESHOLD = 100
TOP_COMMENTS_COUNT = 10
REQUEST_DELAY = 0.1  # seconds between API calls

OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "data", "latest.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def classify_story(title: str) -> str:
    """Return 'show_hn', 'ask_hn', or 'story' based on title prefix."""
    if title and title.startswith("Show HN"):
        return "show_hn"
    if title and title.startswith("Ask HN"):
        return "ask_hn"
    return "story"


async def fetch_json(client: httpx.AsyncClient, path: str) -> Optional[Union[dict, list]]:
    """Fetch JSON from the HN API with error handling."""
    url = f"{API_BASE}{path}"
    try:
        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        log.warning("Failed to fetch %s: %s", url, exc)
        return None


def strip_html(text: Optional[str]) -> str:
    """Rough HTML tag stripping for comment text."""
    if not text:
        return ""
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()


# ---------------------------------------------------------------------------
# Main collection logic
# ---------------------------------------------------------------------------


async def collect() -> dict:
    async with httpx.AsyncClient() as client:
        # 1. Fetch top story IDs
        log.info("Fetching top stories list …")
        story_ids = await fetch_json(client, "/topstories.json")
        if not story_ids:
            log.error("Could not fetch topstories.json — aborting.")
            sys.exit(1)

        target_ids = story_ids[:TOP_STORIES_COUNT]
        log.info("Will fetch details for %d stories.", len(target_ids))

        # 2. Fetch each story item
        items = []
        for idx, sid in enumerate(target_ids, 1):
            sid = str(sid)
            story = await fetch_json(client, f"/item/{sid}.json")
            time.sleep(REQUEST_DELAY)

            if not story or story.get("type") != "story":
                log.warning("Skipping item %s (not a story or fetch failed).", sid)
                continue

            title = story.get("title", "")
            story_type = classify_story(title)

            item: dict = {
                "id": sid,
                "title": title,
                "url": story.get("url", ""),
                "score": story.get("score", 0),
                "comments_count": story.get("descendants", 0),
                "author": story.get("by", ""),
                "type": story_type,
                "raw_text": title,
                "images": [],
                "collected_tags": [],
            }

            # 3. Fetch top-level comments for high-score stories
            if item["score"] > HIGH_SCORE_THRESHOLD:
                kids = story.get("kids", [])
                comment_parts = []
                for cid in kids[:TOP_COMMENTS_COUNT]:
                    comment = await fetch_json(client, f"/item/{cid}.json")
                    time.sleep(REQUEST_DELAY)
                    if not comment or comment.get("type") != "comment":
                        continue
                    author = comment.get("by", "")
                    text = strip_html(comment.get("text", ""))
                    comment_parts.append(f"[{author}] {text}")

                if comment_parts:
                    item["raw_text"] = title + "\n" + item["url"] + "\n" + "\n---\n".join(comment_parts)

            items.append(item)
            log.info(
                "  [%2d/%d] id=%-8s score=%-5d type=%-8s %s",
                idx, len(target_ids), sid, item["score"], story_type, title[:60],
            )

    return {
        "source": "hackernews",
        "collected_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "items": items,
    }


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------


def main():
    log.info("=== Hacker News Collector ===")
    log.info("Output -> %s", OUTPUT_FILE)

    result = asyncio.run(collect())

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)

    log.info("Done — wrote %d items.", len(result["items"]))


if __name__ == "__main__":
    main()
