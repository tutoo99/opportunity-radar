# ThereIsAnAIForThat 每周趋势

ThereIsAnAIForThat weekly trending page. This source is useful for finding AI tools with fresh attention, visible usage intent, pricing signals, saves, ratings, and user comments.

## 数据源

- URL: `https://theresanaiforthat.com/trending/week/`
- Scope: weekly trending AI tools only

## 采集方式

Static DOM extraction from the public trending page.

The collector does not call `/api/` endpoints. It loads the public page with DrissionPage, waits for:

```xpath
//div[@id="data_hist"]/ul[@class="tasks"]
```

Then it parses each `li` under that `ul`.

## 运行

```bash
cd sources/theresanaiforthat
python scripts/collector.py
```

Common options:

```bash
# Keep the browser visible while debugging Cloudflare/page loading issues
python scripts/collector.py --no-headless

# Limit parsed list items
python scripts/collector.py --max-items 50

# Parse a previously saved HTML file instead of launching a browser
python scripts/collector.py --html-file data/page.html

# Save page HTML for parser debugging
python scripts/collector.py --save-html data/page.html
```

Output:

- `data/latest.json`: normalized opportunity-radar format
- `data/theresanaiforthat_week_YYYYMMDD_HHMMSS.json`: timestamped snapshot
- `data/raw_YYYYMMDD_HHMMSS.html`: optional raw page HTML when `--save-html` is used

## 解析字段

Each item is parsed from three areas:

| Area | Fields |
|------|--------|
| `li` attributes | TAAFT id, product name, task, task id, external URL, rank, task slug |
| `.li_row` | product link, icon, short description, task label |
| `.comment` + `.ai_footer` | featured comment, comment vote counts, release age, pricing, views, saves, rating |

The collector keeps original source-specific fields under `_theresanaiforthat` while also emitting the common `items[]` shape used by the opportunity-radar pipeline:

```json
{
  "id": "60933",
  "title": "Authentic.ly - Create quality social videos in minutes with AI.",
  "url": "https://theresanaiforthat.com/ai/veeroll/",
  "score": 4753,
  "comments_count": 1,
  "author": "Lex Malabanan",
  "type": "ai_tool",
  "raw_text": "...",
  "images": ["https://media.theresanaiforthat.com/icons/veeroll.svg?height=207"],
  "collected_tags": ["Social media videos", "social-media-videos", "weekly_trending"]
}
```

`score` maps to weekly visible views when available. `comments_count` maps to visible featured comments in the list item.
