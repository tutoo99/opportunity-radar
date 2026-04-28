#!/usr/bin/env python3
"""
Google Trends Keywords Collector — Opportunity Radar

Primary source:  GitHub repo pre-scraped JSON per country
Fallback source: Google Trends RSS feeds (XML → JSON)

Output format matches the GitHub repo's JSON structure:
{
  "lastUpdate": "...",
  "country": {
    "COUNTRY_CODE": "国家名称",
    ...
  },
  "data": [
    {
      "title": "keyword",
      "trafficCount": "50000+",
      "pubDate": "Thu, 16 Apr 2026 09:00:00 -0700",
      "picture": "https://...",
      "pictureSource": "source name",
      "relatedSearch": [
        {
          "title": "related article title",
          "snippet": "...",
          "url": "https://...",
          "source": "source name"
        }
      ],
      "link": "https://source-of-keyword",
      "geo": "US",
      "geo_name": "美国"
    }
  ]
}

Usage:
    python collector.py                  # Fetch all countries
    python collector.py --country US JP  # Fetch specific countries only
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("google-trends-collector")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "latest.json")

GITHUB_BASE = (
    "https://raw.githubusercontent.com/fdciabdul/"
    "Google-Trends-Keywords-Scraper/main/data"
)
RSS_BASE = "https://trends.google.com/trending/rss?geo={geo}&hours=48"

# Country code → Chinese name
COUNTRY_MAP = {
    "AE": "阿联酋", "AL": "阿尔巴尼亚", "AM": "亚美尼亚", "AO": "安哥拉",
    "AR": "阿根廷", "AT": "奥地利", "AU": "澳大利亚", "AZ": "阿塞拜疆",
    "BA": "波黑", "BD": "孟加拉国", "BE": "比利时", "BF": "布基纳法索",
    "BG": "保加利亚", "BH": "巴林", "BJ": "贝宁", "BO": "玻利维亚",
    "BR": "巴西", "BY": "白俄罗斯", "CA": "加拿大", "CD": "刚果（金）",
    "CH": "瑞士", "CI": "科特迪瓦", "CL": "智利", "CM": "喀麦隆",
    "CO": "哥伦比亚", "CR": "哥斯达黎加", "CU": "古巴", "CY": "塞浦路斯",
    "CZ": "捷克", "DE": "德国", "DK": "丹麦", "DO": "多米尼加共和国",
    "DZ": "阿尔及利亚", "EC": "厄瓜多尔", "EE": "爱沙尼亚", "EG": "埃及",
    "ES": "西班牙", "ET": "埃塞俄比亚", "FI": "芬兰", "FR": "法国",
    "GB": "英国", "GE": "格鲁吉亚", "GH": "加纳", "GR": "希腊",
    "GT": "危地马拉", "HK": "中国香港", "HN": "洪都拉斯", "HR": "克罗地亚",
    "HT": "海地", "HU": "匈牙利", "ID": "印度尼西亚", "IE": "爱尔兰",
    "IL": "以色列", "IN": "印度", "IQ": "伊拉克", "IR": "伊朗",
    "IT": "意大利", "JM": "牙买加", "JO": "约旦", "JP": "日本",
    "KE": "肯尼亚", "KG": "吉尔吉斯斯坦", "KH": "柬埔寨", "KR": "韩国",
    "KW": "科威特", "KZ": "哈萨克斯坦", "LB": "黎巴嫩", "LK": "斯里兰卡",
    "LT": "立陶宛", "LV": "拉脱维亚", "LY": "利比亚", "MA": "摩洛哥",
    "MD": "摩尔多瓦", "MK": "北马其顿", "ML": "马里", "MM": "缅甸",
    "MX": "墨西哥", "MY": "马来西亚", "MZ": "莫桑比克", "NG": "尼日利亚",
    "NI": "尼加拉瓜", "NL": "荷兰", "NO": "挪威", "NP": "尼泊尔",
    "NZ": "新西兰", "OM": "阿曼", "PA": "巴拿马", "PE": "秘鲁",
    "PH": "菲律宾", "PK": "巴基斯坦", "PL": "波兰", "PR": "波多黎各",
    "PS": "巴勒斯坦", "PT": "葡萄牙", "PY": "巴拉圭", "QA": "卡塔尔",
    "RO": "罗马尼亚", "RS": "塞尔维亚", "RU": "俄罗斯", "SA": "沙特阿拉伯",
    "SE": "瑞典", "SG": "新加坡", "SI": "斯洛文尼亚", "SK": "斯洛伐克",
    "SN": "塞内加尔", "SV": "萨尔瓦多", "SY": "叙利亚", "TH": "泰国",
    "TM": "土库曼斯坦", "TN": "突尼斯", "TR": "土耳其", "TT": "特立尼达和多巴哥",
    "TW": "中国台湾", "TZ": "坦桑尼亚", "UA": "乌克兰", "UG": "乌干达",
    "US": "美国", "UY": "乌拉圭", "UZ": "乌兹别克斯坦", "VE": "委内瑞拉",
    "VN": "越南", "YE": "也门", "ZA": "南非", "ZM": "赞比亚",
    "ZW": "津巴布韦",
}

REQUEST_TIMEOUT = 15  # seconds


def now_iso():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Primary: fetch from GitHub repo
# ---------------------------------------------------------------------------
def fetch_github_country(client, geo):
    """Fetch a single country's JSON from the GitHub repo."""
    url = f"{GITHUB_BASE}/{geo}.json"
    try:
        r = client.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def collect_from_github(client, countries):
    """
    Primary collection: download pre-scraped JSON from GitHub repo.
    Returns (all_items, success_count, last_update).
    """
    all_items = []
    success_count = 0
    last_update = now_iso()

    for geo in countries:
        geo_name = COUNTRY_MAP.get(geo, geo)
        data = fetch_github_country(client, geo)
        if data:
            success_count += 1
            if isinstance(data.get("lastUpdate"), str):
                last_update = data["lastUpdate"]
            items = data.get("data", [])
            # Add geo info to each item
            for item in items:
                item["geo"] = geo
                item["geo_name"] = geo_name
            all_items.extend(items)
            log.info("  [GitHub] %s (%s): %d items", geo, geo_name, len(items))
            time.sleep(0.1)  # polite delay
        else:
            log.warning("  [GitHub] %s (%s): not found", geo, geo_name)

    return all_items, success_count, last_update


# ---------------------------------------------------------------------------
# Fallback: parse Google Trends RSS feed
# ---------------------------------------------------------------------------
def parse_rss_feed(xml_text, geo):
    """
    Parse Google Trends RSS XML into items matching the GitHub JSON format.

    RSS structure:
    <item>
      <title>keyword</title>
      <ht:approx_traffic>50000+</ht:approx_traffic>
      <pubDate>Thu, 16 Apr 2026 09:00:00 -0700</pubDate>
      <ht:news_item>
        <ht:news_item_title>article title</ht:news_item_title>
        <ht:news_item_snippet>snippet text</ht:news_item_snippet>
        <ht:news_item_url>https://...</ht:news_item_url>
        <ht:news_item_source>Source Name</ht:news_item_source>
      </ht:news_item>
      ...
    </item>
    """
    items = []
    geo_name = COUNTRY_MAP.get(geo, geo)

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.error("  [RSS] Failed to parse XML for %s: %s", geo, e)
        return items

    # Register namespace
    ns = {"ht": "http://www.google.com/schemas/2009/trends"}

    for item_el in root.findall(".//item"):
        try:
            title = item_el.findtext("title", "").strip()
            if not title:
                continue

            traffic = item_el.findtext("ht:approx_traffic", "", namespaces=ns)
            pub_date = item_el.findtext("pubDate", "")

            # Extract first picture URL from enclosure/media if available
            picture = ""
            picture_source = ""
            enclosure = item_el.find("enclosure")
            if enclosure is not None:
                picture = enclosure.get("url", "")

            # Extract related news items
            related = []
            for news in item_el.findall("ht:news_item", namespaces=ns):
                news_title = news.findtext("ht:news_item_title", "", namespaces=ns)
                news_snippet = news.findtext("ht:news_item_snippet", "", namespaces=ns)
                news_url = news.findtext("ht:news_item_url", "", namespaces=ns)
                news_source = news.findtext("ht:news_item_source", "", namespaces=ns)

                if news_title or news_url:
                    related.append({
                        "title": news_title,
                        "snippet": news_snippet,
                        "url": news_url,
                        "source": news_source,
                    })

            item = {
                "title": title,
                "trafficCount": traffic or "",
                "pubDate": pub_date,
                "picture": picture,
                "pictureSource": picture_source,
                "relatedSearch": related,
                "link": related[0]["url"] if related else "",
                "geo": geo,
                "geo_name": geo_name,
            }
            items.append(item)
        except Exception as e:
            log.warning("  [RSS] Error parsing item for %s: %s", geo, e)
            continue

    return items


def collect_from_rss(client, countries):
    """
    Fallback collection: fetch Google Trends RSS feeds.
    Returns (all_items, success_count).
    """
    all_items = []
    success_count = 0

    for geo in countries:
        geo_name = COUNTRY_MAP.get(geo, geo)
        url = RSS_BASE.format(geo=geo)
        try:
            r = client.get(url, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                items = parse_rss_feed(r.text, geo)
                if items:
                    all_items.extend(items)
                    success_count += 1
                    log.info("  [RSS] %s (%s): %d items", geo, geo_name, len(items))
                else:
                    log.warning("  [RSS] %s (%s): no items parsed", geo, geo_name)
            else:
                log.warning("  [RSS] %s (%s): HTTP %d", geo, geo_name, r.status_code)
            time.sleep(1)  # polite delay for Google
        except Exception as e:
            log.warning("  [RSS] %s (%s): error - %s", geo, geo_name, e)

    return all_items, success_count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    countries = sorted(COUNTRY_MAP.keys())

    # If specific countries requested via CLI, filter
    if args:
        filtered = [c for c in countries if c in args]
        if filtered:
            countries = filtered

    log.info("=== Google Trends Collector Start ===")
    log.info("Countries to fetch: %d", len(countries))

    client = httpx.Client(
        headers={"User-Agent": "Mozilla/5.0 (compatible; OpportunityRadar/1.0)"},
        follow_redirects=True,
    )

    # --- Primary: GitHub repo ---
    log.info("Phase 1: Fetching from GitHub repo ...")
    github_items, github_ok, last_update = collect_from_github(client, countries)

    # --- Fallback: RSS for countries not found in GitHub ---
    missing = [c for c in countries if c not in {it["geo"] for it in github_items}]
    if missing:
        log.info("Phase 2: Fallback RSS for %d missing countries ...", len(missing))
        rss_items, rss_ok = collect_from_rss(client, missing)
        if rss_items:
            github_items.extend(rss_items)
        log.info("RSS fallback got %d items from %d countries", len(rss_items), rss_ok)

    client.close()

    # --- Build output ---
    output = {
        "lastUpdate": last_update,
        "country": COUNTRY_MAP,
        "data": github_items,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = len(github_items)
    unique_titles = len(set(it["title"].lower() for it in github_items))
    log.info("Saved %d items (%d unique keywords) from %d/%d countries to %s",
             total, unique_titles, github_ok, len(countries), OUTPUT_PATH)
    log.info("=== Google Trends Collector End ===")


if __name__ == "__main__":
    main()
