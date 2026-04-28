# 机会卡片（单个机会的标准记录格式）

每个采集到的机会，最终输出为以下 JSON 格式：

```json
{
  "id": "OPP-20260416-001",
  "source": "plugin-marketplace",
  "source_url": "https://原始来源链接",
  "title": "一句话描述机会",
  "demand_desc": "用户在解决什么问题",
  "pain_points": ["痛点1", "痛点2"],
  "images": ["https://image.example.com/opp-001-img1.png"],
  "image_insights": "视觉模型分析结果：图片显示月收益截图...",
  "evidence": "需求信号来源（下载量/评论/帖子数等）",
  "existing_solutions": [
    {"name": "现有产品名", "url": "", "rating": 3.8, "main_complaint": "差评摘要"}
  ],
  "scores": {
    "pain_intensity": 4,
    "willingness_to_pay": 3,
    "competition_gap": 4,
    "self_match": 5
  },
  "total_score": 16,
  "tags": ["省时间", "AI", "自动化"],
  "mvp_estimate": "1周",
  "monetization": "月订阅 / 一次性买断",
  "status": "new",
  "created_at": "2026-04-16"
}
```

## 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| id | 是 | 格式 OPP-YYYYMMDD-NNN |
| source | 是 | 数据源名称，对应 sources/ 下的目录名 |
| source_url | 是 | 原始链接，可追溯 |
| title | 是 | 一句话描述 |
| demand_desc | 是 | 用户在解决什么问题 |
| pain_points | 是 | 至少1个痛点 |
| images | 否 | 原始图片 URL 列表；当前阶段不下载本地 |
| image_insights | 否 | 视觉大模型对图片的分析结果；仅在文本信息不足时调用 |
| evidence | 是 | 需求信号的具体数据 |
| existing_solutions | 否 | 已有的竞品 |
| scores | 是 | 四维评分（1-5） |
| total_score | 是 | 总分 |
| tags | 是 | 标签，便于分类筛选 |
| mvp_estimate | 是 | MVP 周期估算 |
| monetization | 否 | 变现方式建议 |
| status | 是 | new / reviewing / validated / building / shipped |
