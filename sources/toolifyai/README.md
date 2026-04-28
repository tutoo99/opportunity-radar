# Toolify.ai 趋势榜单

AI 产品月度增长榜单，发现持续增长的 AI 产品领域。

## 数据源

- URL: https://www.toolify.ai/zh/Best-trending-AI-Tools
- API: `https://www.toolify.ai/self-api/v1/top/month-top`
- 数据范围: 2023年1月至今，每月 Top 300 产品

## 采集方式

`curl_cffi` 模拟浏览器 TLS 指纹（`impersonate='chrome110'`），无需开启浏览器。

API 有 TLS 指纹检测，普通 httpx/requests 会被拒绝。`curl_cffi` 底层用 libcurl，能模拟 Chrome 的 TLS 握手指纹。

## 脚本

```bash
# 安装依赖
pip install curl_cffi python-dateutil

# 运行
python sources/toolifyai/scripts/toolify_radar.py
```

脚本功能：
1. 自动采集最近4个月的榜单数据（当月 + 回溯3个月）
2. 两层筛选（第一层：访问量+增长量阈值；第二层：持续增长验证）
3. 输出产品简报（TXT）+ 原始数据（JSON）

## 筛选逻辑

### 第一层：初筛

| 条件 | 阈值 |
|------|------|
| 月访问量 | 0.5M ~ 3M |
| 月增长量 | >= 300K |

为什么这个范围？太大（如 ChatGPT 几十亿访问）说明市场已被巨头占领；太小（< 500K）说明需求还没验证。0.5M~3M 是「需求已验证 + 竞争尚未固化」的甜蜜区。

### 第二层：持续增长验证

对第一层候选产品，回溯3个月查看是否仍在增长：

- 在 Top300 榜单中出现 >= 2 次
- 出现的月份 growth > 0（正增长）

注意：榜单只取 Top 300，如果产品当月增长量跌出前 300 就看不到了，所以允许部分月份不出现。

## API 参数

```
GET https://www.toolify.ai/self-api/v1/top/month-top
  ?page=1
  &per_page=300          # 一次拉完
  &date=2026-03-01       # 月份第1天
  &order_by=growth       # 按增长量排序
  &direction=desc
```

响应关键字段：
- `handle` → 详情页 URL 的一部分
- `name` → 产品名
- `month_visited_count` → 月访问量
- `growth` → 月增长量
- `growth_rate` → 月增长率
- `description` → 产品描述
- `tags` → 标签列表
