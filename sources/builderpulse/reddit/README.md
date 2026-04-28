# Reddit 数据源

全球最大的论坛社区，包含丰富的商业讨论、收入分享、用户抱怨。

## 采集内容

| Subreddit | 采集内容 | 机会信号类型 |
|-----------|---------|-------------|
| r/SaaS | SaaS 创业讨论 | 收入数据、定价策略、获客渠道 |
| r/SideProject | 副业项目分享 | 产品验证、MVP 反馈、变现案例 |
| r/Entrepreneur | 创业讨论 | 市场需求、商业模型 |
| r/startups | 初创公司 | 融资方向、市场机会 |

每个 subreddit 采集 Top 20 热帖 + 前 5 条评论。

## 采集方式

使用 ruyiPage 浏览器自动化采集 old.reddit.com（DOM 结构更简单）。

- 目标 URL: `https://old.reddit.com/r/{subreddit}/hot/`
- 速率限制: subreddit 切换间隔 2s，帖子页切换间隔 1s

## 运行

```bash
cd sources/builderpulse/reddit/scripts
python collector.py
```

产出: `data/latest.json`

## 机会信号特征

- 收入里程碑帖（"$X MRR", "$X ARR"）：验证市场规模和定价
- "I built X in Y hours" 帖子：2 小时构建类机会，低门槛
- 抱怨帖（针对具体工具/服务）：痛点强度信号，竞品机会
- "Looking for recommendations" 帖子：直接需求表达
- 评论区的高赞回答：真实用户痛点和付费意愿
