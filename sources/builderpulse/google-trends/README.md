# Google Trends 数据源

全球搜索趋势，覆盖 125 个国家/地区的实时热搜关键词。

## 采集内容

| 内容 | 方式 | 说明 |
|------|------|------|
| 各国实时热搜 | GitHub 仓库预抓取 JSON | 125 国，每国 ~10 条，含关联搜索 |
| 兜底数据源 | Google Trends RSS | 仓库缺失时自动回退到 RSS |

每条趋势包含：
- **title**: 热搜关键词（核心信号）
- **trafficCount**: 搜索流量级别（如 "50000+"）
- **relatedSearch**: 3 条关联新闻（标题 + URL + 来源）
- **geo / geo_name**: 国家代码和中文名
- **picture**: 相关图片 URL

## 采集方式

### 主数据源：GitHub 仓库
从 fdciabdul/Google-Trends-Keywords-Scraper 仓库下载预抓取的 JSON 数据，按国家代码存储（如 `US.json`, `JP.json`）。每日更新，无需 API Key。

### 兜底数据源：Google Trends RSS
当 GitHub 仓库中某个国家的 JSON 文件不存在或无法访问时，自动回退到：
```
https://trends.google.com/trending/rss?geo={COUNTRY_CODE}&hours=48
```
解析 XML 中的 `<item>` 和 `<ht:news_item>` 节点，转为与主数据源一致的 JSON 格式。

## 运行

```bash
# 采集所有 125 个国家
cd sources/builderpulse/google-trends/scripts
python collector.py

# 只采集指定国家
python collector.py --country US JP DE GB KR SG
```

产出: `data/latest.json`（覆盖更新，无版本归档）

## 机会信号特征

- **title 关键词**: 直接反映公众搜索热点，是第一层信号
- **relatedSearch 关联词**: 关键词背后的具体新闻和事件，是第二层信号
- **trafficCount 流量级别**: "50000+" 级别代表大规模关注，"200+" 级别代表小众但正在上升
- **多国共现**: 同一关键词在多个国家同时热搜 → 全球性趋势
- **与 HN/GitHub/PH 交叉**: Google Trends 热词 + HN 高赞 + GitHub 趋势 = 高置信度机会
