# Hacker News 数据源

全球最大的开发者社区，独立开发者产品首发地。

## 采集内容

| 内容 | 来源 | 说明 |
|------|------|------|
| Top 30 热门帖子 | 首页 | 反映开发者社区当前最关注的话题 |
| Show HN | 筛选 top stories | 独立开发者新产品首发，最直接的机会信号 |
| Ask HN | 筛选 top stories | 开发者真实需求和痛点 |
| 高赞评论 | score > 100 的帖子 | 评论中常有竞品分析、技术栈讨论、定价讨论 |

## 采集方式

使用 Hacker News 官方公开 API，无需认证，完全免费。

- 基础 URL: `https://hacker-news.firebaseio.com/v0/`
- 端点: `/topstories.json`, `/item/{id}.json`
- 速率限制: 请求间隔 0.1s

## 运行

```bash
cd sources/builderpulse/hackernews/scripts
python collector.py
```

产出: `data/latest.json`

## 机会信号特征

- Show HN 帖子：新产品发布，type=show_hn，关注评论中的功能需求和建议
- Ask HN 帖子：开发者问问题，type=ask_hn，关注"求推荐"类帖子（付费意愿信号）
- 高分帖子（score > 200）：社区共识，交叉验证信号强
- 评论数/分数比高：争议话题，可能蕴含市场分歧
