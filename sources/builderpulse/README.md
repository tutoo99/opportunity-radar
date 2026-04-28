# BuilderPulse 全球开发者信号源

从全球 6 大英文平台采集开发者生态信号，覆盖独立开发者、开源社区、AI 领域的商业机会。

## 为什么叫 BuilderPulse

参考 [BuilderPulse](https://github.com/BuilderPulse/BuilderPulse) 的方法论：每天从多个英文平台采集信号，交叉验证后提取真实机会。但我们的实现完全自主可控——自己采集、自己分析、自己评分。

## 数据源

| 子目录 | 平台 | 采集方式 | 频率 |
|--------|------|---------|------|
| hackernews | Hacker News | 公开 API（免费，无需 key） | 每天 |
| github-trending | GitHub Trending | ruyiPage 页面采集 | 每天 |
| producthunt | Product Hunt | ruyiPage 页面采集 | 每天 |
| huggingface | HuggingFace | 公开 API + ruyiPage | 每天 |
| google-trends | Google Trends | pytrends 库 | 每天 |
| reddit | Reddit | ruyiPage 采集关键 subreddit | 每天 |

## 采集方式说明

各数据源根据实际情况选择最佳采集方式，不强制统一工具：

- **有稳定公开 API 的**（Hacker News、HuggingFace）→ 直接 httpx 调用，省资源、速度快
- **需要登录/反爬的**（Product Hunt、Reddit）→ ruyiPage 模拟浏览器
- **无 API 或 API 受限的**（GitHub Trending、Google Trends）→ ruyiPage / 第三方库

## 统一输出格式

每个采集脚本产出一个 JSON 文件，格式统一：

```json
{
  "source": "hackernews",
  "collected_at": "2026-04-16T10:50:00+08:00",
  "items": [
    {
      "id": "12345",
      "title": "Show HN: I built...",
      "url": "https://...",
      "score": 500,
      "comments_count": 200,
      "author": "username",
      "type": "show_hn",
      "raw_text": "...",
      "images": [],
      "collected_tags": ["ai", "open-source"]
    }
  ]
}
```

`collected_tags` 是采集阶段能直接提取的标签（如帖子类型、分类），用于后续 AI 分析参考。真正的机会标签（痛点强度、变现方向等）在阶段二由 AI 生成。

## 分析框架

采集后的数据按五维分析框架处理（详见 `references/builderpulse-methodology.md`）：

1. **发现机会** — 产品发布、搜索飙升、开源增长、用户抱怨
2. **技术选型** — 公司关停/降级、工具增长、模型趋势、技术栈分析
3. **竞争情报** — 收入定价、旧项目复活、"XX 已死"迁移
4. **趋势判断** — 关键词频率变化、VC 方向、降温词、新词
5. **行动触发** — 结合 profile.md 给出具体构建建议

## 与中文数据源的关系

- 中文数据源（生财、小红书、小宇宙）→ 国内市场机会
- BuilderPulse 数据源 → 全球市场机会 + 技术趋势
- 两者在阶段二合并去重，在阶段三统一评分

## 依赖

```bash
pip install httpx pytrends ruyipage
```

Hacker News 和 HuggingFace 只需 httpx，无需额外依赖。
