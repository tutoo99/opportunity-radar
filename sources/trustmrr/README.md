# TrustMRR 数据源

Verified startup revenue database and acquisition marketplace. This source is useful for finding paid-market proof: products with verified revenue, MRR, customer counts, sale prices, multiples, growth, and traffic signals.

## 数据源

- Marketplace: `https://trustmrr.com/`
- API docs: `https://trustmrr.com/docs/api`
- API base: `https://trustmrr.com/api/v1`

TrustMRR API requires an API key from the developer dashboard. Keys start with `tmrr_`.

## 采集方式

Official API via `httpx`.

This is a permitted source type under the opportunity-radar rules because TrustMRR provides a documented API. Authentication is done through:

```bash
export TRUSTMRR_API_KEY="tmrr_your_api_key"
```

## 运行

```bash
cd sources/trustmrr
python scripts/collector.py
```

Common filters:

```bash
# Top verified-revenue startups
python scripts/collector.py --sort revenue-desc --max-items 100

# Fast-growing small revenue products
python scripts/collector.py --sort growth-desc --min-revenue-usd 100 --max-revenue-usd 5000

# Products currently listed for sale
python scripts/collector.py --on-sale true --sort best-deal --max-items 100

# Fetch detailed tech stack for top 20 list results
python scripts/collector.py --fetch-details 20
```

Output:

- `data/latest.json`: normalized opportunity-radar format
- `data/trustmrr_YYYYMMDD_HHMMSS.json`: timestamped snapshot
- `data/raw_YYYYMMDD_HHMMSS.json`: raw API payloads and fetch metadata

## 机会信号特征

| Signal | Why it matters |
|--------|----------------|
| Verified revenue and MRR | Direct paid demand proof |
| Growth rate | Market momentum and product-market pull |
| Asking price and multiple | Acquisition value and competition floor |
| Category and target audience | Helps map repeatable micro-SaaS niches |
| Customers and subscriptions | Separates one-off revenue from recurring demand |
| Traffic and revenue per visitor | Monetization efficiency |
| Tech stack details | Helps score fit against `profile.md` |

## 字段说明

The collector keeps original TrustMRR fields under `_trustmrr` while also emitting the common `items[]` shape used by the opportunity-radar pipeline:

```json
{
  "id": "startup-slug",
  "title": "Product - short description",
  "url": "https://trustmrr.com/startup/startup-slug",
  "score": 42500,
  "comments_count": 7800,
  "author": "x_handle",
  "type": "verified_revenue",
  "raw_text": "...",
  "images": ["https://..."],
  "collected_tags": ["saas", "stripe", "b2b"]
}
```

`score` is the last-30-days verified revenue in USD cents. `comments_count` is mapped to customer count for pipeline compatibility.
