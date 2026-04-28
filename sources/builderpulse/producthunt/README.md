# Product Hunt 数据源

全球最大的新产品发布社区，独立开发者的产品发布首选平台。

## 采集内容

| 内容 | 来源 | 说明 |
|------|------|------|
| 每日 Top 30 产品 | 日排行榜 | 当天最受关注的新产品 |
| 产品标签 | 产品页面 | 分类和主题 |
| 用户评论 | 产品页面 | 早期用户反馈 |

## 采集方式

使用 ruyiPage 浏览器自动化采集 Product Hunt 日排行榜。

- 目标 URL: `https://www.producthunt.com/leaderboard/daily`
- 降级: `https://www.producthunt.com/`（如果排行榜结构变化）
- 速率限制: 产品页切换间隔 3s

## 运行

```bash
cd sources/builderpulse/producthunt/scripts
python collector.py
```

产出: `data/latest.json`

## 机会信号特征

- 高票数 + 开发者工具标签：直接竞品或互补产品
- 标签含 "AI" + 低票数：AI 产品开始泛滥，差异化是关键
- 新产品与 GitHub Trending 重叠：多源验证，信号置信度高
- 评论中的 "I'd pay for..." / "shut up and take my money"：付费意愿信号
