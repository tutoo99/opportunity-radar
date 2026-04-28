#!/usr/bin/env python3
"""
Reddit collector for opportunity-radar skill.
Uses ruyipage browser automation to scrape opportunity-related subreddits.

Target subreddits:
  r/SaaS        – SaaS business discussion
  r/SideProject – indie projects, monetization
  r/Entrepreneur – business opportunities
  r/startups    – startup discussion
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta

from ruyipage import FirefoxOptions, Firefox

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SUBREDDITS = ["SaaS", "SideProject", "Entrepreneur", "startups"]
POSTS_PER_SUBREDDIT = 20
TOP_COMMENTS_PER_POST = 5
SUBREDDIT_DELAY = 2  # seconds between subreddits
POST_NAV_DELAY = 1   # seconds between navigating into posts
PAGE_LOAD_WAIT = 5   # seconds to wait for page to load

REDDIT_DOMAINS = [
    "https://old.reddit.com",
    "https://www.reddit.com",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0"
)

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


def create_browser():
    """Create a headless Firefox browser with a proper User-Agent."""
    opts = FirefoxOptions()
    opts.headless = True
    opts.set_pref("general.useragent.override", USER_AGENT)
    return Firefox(opts)


def safe_text(element) -> str:
    """Extract text from a ruyipage element, returning empty string on failure."""
    try:
        txt = element.text or ""
        return txt.strip()
    except Exception:
        return ""


def safe_attr(element, attr: str) -> str:
    """Get an attribute from an element safely."""
    try:
        return element.attr(attr) or ""
    except Exception:
        return ""


def safe_eles(parent, css: str):
    """Run eles() with error handling, always returns a list."""
    try:
        result = parent.eles(css)
        return result if result else []
    except Exception as exc:
        log.warning("safe_eles failed for '%s': %s", css, exc)
        return []


def is_blocked_page(page) -> bool:
    """Check if the current page is a Reddit block/error page."""
    try:
        title = safe_text(page.ele("css:title"))
        if "blocked" in title.lower():
            return True
        body_text = page.run_js("return document.body.innerText;") or ""
        if "blocked by network security" in body_text.lower():
            return True
        if "whoa there, pardner" in body_text.lower():
            return True
    except Exception:
        pass
    return False


def classify_post_type(thing_el) -> str:
    """Infer post type from the 'thing' element classes."""
    try:
        classes = thing_el.attr("class") or ""
        if "linkflair-image" in classes:
            return "image"
        if "self" in classes:
            return "text"
    except Exception:
        pass
    return "link"


def pick_working_domain(page) -> str:
    """Try each Reddit domain and return the first one that isn't blocked."""
    for domain in REDDIT_DOMAINS:
        try:
            test_url = f"{domain}/r/SaaS/hot/"
            log.info("Testing domain: %s", domain)
            page.get(test_url)
            time.sleep(PAGE_LOAD_WAIT)
            if is_blocked_page(page):
                log.warning("Domain %s is blocked", domain)
                continue
            # Check if we can find .thing elements
            things = safe_eles(page, "css:.thing")
            if things:
                log.info("Domain %s works — found %d posts", domain, len(things))
                return domain
            # Maybe it's the new reddit layout (www.reddit.com)
            # Check for post elements in new layout
            posts = safe_eles(page, "css:shreddit-post")
            if posts:
                log.info("Domain %s works (new layout) — found %d posts", domain, len(posts))
                return domain
            log.warning("Domain %s returned no posts", domain)
        except Exception as exc:
            log.warning("Domain %s failed: %s", domain, exc)
            continue
    return REDDIT_DOMAINS[0]


# ---------------------------------------------------------------------------
# Subreddit scraper — old.reddit.com layout
# ---------------------------------------------------------------------------


def scrape_subreddit_old(page, subreddit: str, domain: str) -> list:
    """Scrape hot posts from old.reddit.com listing page."""
    url = f"{domain}/r/{subreddit}/hot/"
    log.info("Navigating to %s", url)
    try:
        page.get(url)
        time.sleep(PAGE_LOAD_WAIT)
    except Exception as exc:
        log.error("Failed to load %s: %s", url, exc)
        return []

    if is_blocked_page(page):
        log.warning("Page is blocked for r/%s on %s", subreddit, domain)
        return []

    things = safe_eles(page, "css:.thing")
    if not things:
        log.warning("No .thing elements found on %s", url)
        return []

    posts = []
    for idx, thing in enumerate(things[:POSTS_PER_SUBREDDIT]):
        try:
            title_els = safe_eles(thing, "css:a.title")
            if not title_els:
                continue
            title_el = title_els[0]
            title = safe_text(title_el)
            post_url = safe_attr(title_el, "href")
            if post_url.startswith("/"):
                post_url = f"{domain}{post_url}"

            # Score
            score_els = safe_eles(thing, "css:.score.unvoted")
            score_str = safe_text(score_els[0]) if score_els else "0"
            try:
                score = int(score_str.replace(",", ""))
            except ValueError:
                score = 0

            # Comments count
            comments_els = safe_eles(thing, "css:.comments")
            comments_str = safe_text(comments_els[0]) if comments_els else "0"
            try:
                comments_count = int(comments_str.split()[0].replace(",", ""))
            except (ValueError, IndexError):
                comments_count = 0

            # Author
            author_els = safe_eles(thing, "css:a.author")
            author = safe_text(author_els[0]) if author_els else "[deleted]"

            # Flair
            flair_els = safe_eles(thing, "css:.linkflairlabel")
            flair = safe_text(flair_els[0]) if flair_els else ""

            # Post type
            post_type = classify_post_type(thing)

            # Post body (self text) — only available on the post page
            body_text = ""
            comment_texts = []

            # Navigate into the post to get body + comments
            if post_url and domain in post_url:
                try:
                    page.get(post_url)
                    time.sleep(POST_NAV_DELAY)

                    # Self-text / body (first 500 chars)
                    body_els = safe_eles(
                        page,
                        "css:div.expando form.usertext-body .md",
                    )
                    if body_els:
                        body_text = safe_text(body_els[0])[:500]

                    # Top comments
                    comment_mds = safe_eles(page, "css:.comment .md")
                    for cmd in comment_mds[:TOP_COMMENTS_PER_POST]:
                        ct = safe_text(cmd)
                        if ct:
                            comment_texts.append(ct)

                    # Go back to listing
                    page.get(url)
                    time.sleep(POST_NAV_DELAY)
                except Exception as exc:
                    log.warning(
                        "Error scraping post page %s: %s", post_url, exc
                    )
                    try:
                        page.get(url)
                        time.sleep(POST_NAV_DELAY)
                    except Exception:
                        pass

            collected_tags = [subreddit]
            if flair:
                collected_tags.append(flair)

            raw_text_parts = [title]
            if body_text:
                raw_text_parts.append(body_text)
            if comment_texts:
                raw_text_parts.append("---\n".join(comment_texts))

            posts.append({
                "id": post_url.split("/")[-2] if post_url else "",
                "title": title,
                "url": post_url,
                "score": score,
                "comments_count": comments_count,
                "author": author,
                "type": post_type,
                "raw_text": "\n".join(raw_text_parts),
                "images": [],
                "collected_tags": collected_tags,
            })

            log.info(
                "  [%2d/%d] score=%-5d comments=%-4d r/%-14s %s",
                idx + 1, min(len(things), POSTS_PER_SUBREDDIT),
                score, comments_count, subreddit, title[:55],
            )

        except Exception as exc:
            log.warning(
                "Error processing post #%d on r/%s: %s", idx, subreddit, exc
            )
            continue

    return posts


# ---------------------------------------------------------------------------
# Subreddit scraper — new www.reddit.com layout (shreddit)
# ---------------------------------------------------------------------------


def scrape_subreddit_new(page, subreddit: str, domain: str) -> list:
    """Scrape hot posts from new www.reddit.com (shreddit-post elements)."""
    url = f"{domain}/r/{subreddit}/hot/"
    log.info("Navigating to %s", url)
    try:
        page.get(url)
        time.sleep(PAGE_LOAD_WAIT)
    except Exception as exc:
        log.error("Failed to load %s: %s", url, exc)
        return []

    if is_blocked_page(page):
        log.warning("Page is blocked for r/%s on %s", subreddit, domain)
        return []

    # New reddit uses <shreddit-post> web components
    posts = []
    post_els = safe_eles(page, "css:shreddit-post")
    if not post_els:
        # Fallback: try data-testid attribute
        post_els = safe_eles(page, 'css:[data-testid="post-container"]')

    if not post_els:
        log.warning("No post elements found on %s", url)
        return []

    for idx, post_el in enumerate(post_els[:POSTS_PER_SUBREDDIT]):
        try:
            # Title is in an <a> inside the post, or a <h3>
            title_el = post_el.ele("css:a[slot='title']") or post_el.ele("css:h3")
            if not title_el:
                title_el = post_el.ele("css:a")
            if not title_el:
                continue
            title = safe_text(title_el)
            post_url = safe_attr(title_el, "href") or ""
            if post_url.startswith("/"):
                post_url = f"{domain}{post_url}"

            # Score — look for score element
            score_el = post_el.ele("css:shreddit-post-score") or post_el.ele("css:[slot='score']")
            score_str = safe_text(score_el) if score_el else "0"
            try:
                score = int(re.sub(r"[^\d]", "", score_str))
            except (ValueError, TypeError):
                score = 0

            # Author
            author_el = post_el.ele("css:shreddit-post-author") or post_el.ele("css:a[slot='author']")
            author = safe_text(author_el) if author_el else "[deleted]"

            # Comments count
            comments_el = post_el.ele("css:a[slot='comments']") or post_el.ele("css:[data-testid='post-comments-link']")
            comments_text = safe_text(comments_el) if comments_el else ""
            try:
                comments_count = int(re.sub(r"[^\d]", "", comments_text))
            except (ValueError, TypeError):
                comments_count = 0

            # Post content (self text preview)
            content_el = post_el.ele("css:div[slot='post-media-container'] p") or post_el.ele("css:div[id^'t3_'] p")
            body_text = safe_text(content_el)[:500] if content_el else ""

            # Flair — new reddit uses various flair elements
            flair_el = post_el.ele("css:span.flair") or post_el.ele("css:[slot='post-flair']")
            flair = safe_text(flair_el) if flair_el else ""

            collected_tags = [subreddit]
            if flair:
                collected_tags.append(flair)

            raw_text_parts = [title]
            if body_text:
                raw_text_parts.append(body_text)

            posts.append({
                "id": post_url.split("/")[-2] if post_url else "",
                "title": title,
                "url": post_url,
                "score": score,
                "comments_count": comments_count,
                "author": author,
                "type": "text" if body_text else "link",
                "raw_text": "\n".join(raw_text_parts),
                "images": [],
                "collected_tags": collected_tags,
            })

            log.info(
                "  [%2d/%d] score=%-5d comments=%-4d r/%-14s %s",
                idx + 1, min(len(post_els), POSTS_PER_SUBREDDIT),
                score, comments_count, subreddit, title[:55],
            )

        except Exception as exc:
            log.warning(
                "Error processing post #%d on r/%s: %s", idx, subreddit, exc
            )
            continue

    return posts


# ---------------------------------------------------------------------------
# Subreddit scraper — dispatch
# ---------------------------------------------------------------------------


def scrape_subreddit(page, subreddit: str, domain: str) -> list:
    """Scrape hot posts, auto-detecting old vs new layout."""
    if "old.reddit.com" in domain:
        return scrape_subreddit_old(page, subreddit, domain)
    else:
        # Try old-style selectors first, then fall back to new
        things = safe_eles(page, "css:.thing")
        if things:
            return scrape_subreddit_old(page, subreddit, domain)
        return scrape_subreddit_new(page, subreddit, domain)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    log.info("=== Reddit Collector (ruyipage) ===")
    log.info("Output -> %s", OUTPUT_FILE)

    browser = None
    try:
        browser = create_browser()
        page = browser.latest_tab

        # Auto-detect working domain
        working_domain = pick_working_domain(page)
        log.info("Using domain: %s", working_domain)

        all_items = []

        for sub in SUBREDDITS:
            log.info("--- Scraping r/%s ---", sub)
            posts = scrape_subreddit(page, sub, working_domain)
            all_items.extend(posts)
            log.info("  Got %d posts from r/%s", len(posts), sub)
            if sub != SUBREDDITS[-1]:
                time.sleep(SUBREDDIT_DELAY)

        result = {
            "source": "reddit",
            "collected_at": datetime.now(
                timezone(timedelta(hours=8))
            ).isoformat(),
            "items": all_items,
        }

        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)

        log.info(
            "Done — wrote %d items across %d subreddits.",
            len(all_items),
            len(SUBREDDITS),
        )

    except Exception as exc:
        log.error("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        if browser:
            try:
                browser.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
