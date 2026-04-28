# HuggingFace 数据源

全球最大的 AI 模型社区，反映 AI 技术趋势和模型能力方向。

## 采集内容

| 内容 | API 端点 | 说明 |
|------|---------|------|
| 趋势模型 Top 30 | /api/models?sort=trending | 热门 AI 模型 |
| 趋势 Space Top 15 | /api/spaces?sort=trending | 热门 AI 应用 |

每个模型/Space 采集：ID、作者、下载量、点赞数、标签、pipeline 类型。

## 采集方式

使用 HuggingFace 公开 API（无需认证）。

- 模型: `https://huggingface.co/api/models?sort=trending&limit=30`
- Space: `https://huggingface.co/api/spaces?sort=trending&limit=15`
- 速率限制: 请求间隔 0.2s

## 运行

```bash
cd sources/builderpulse/huggingface/scripts
python collector.py
```

产出: `data/latest.json`

## 机会信号特征

- 高下载量 + 低评分模型：有需求但质量差，改进空间大
- Apache 2.0 / MIT 协议的强模型：可商用的免费底座
- TTS/语音克隆模型：消费级产品机会（播客、配音、助手）
- 多模态模型趋势：产品方向参考
- Space 排行第一：当前最有商业价值的 AI 应用方向
