# GitHub Trending 数据源

全球开源项目趋势风向标，反映技术方向和开发者需求。

## 采集内容

| 内容 | 页面 | 说明 |
|------|------|------|
| 趋势仓库 Top 30 | /trending | 全语言热门项目 |
| Python 趋势 Top 15 | /trending/python | Python 生态热门 |
| TypeScript 趋势 Top 15 | /trending/typescript | TS 生态热门 |

每个仓库采集：名称、描述、今日新增 star、语言、fork 数、贡献者。

## 采集方式

使用 ruyiPage 浏览器自动化采集 GitHub Trending 页面（无公开 API）。

- 目标 URL: `https://github.com/trending`
- 元素: `article.Box-row`
- 速率限制: 页面切换间隔 2s

## 运行

```bash
cd sources/builderpulse/github-trending/scripts
python collector.py
```

产出: `data/latest.json`

## 机会信号特征

- 高 star 增长 + 低 fork 比：新项目，竞争空白大
- 无商业化版本的开源项目：托管服务机会
- 标注 "Show HN" 的仓库：来自 HN 交叉验证
- 同一领域多个项目上榜：赛道确认信号
