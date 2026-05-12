---
name: opportunity-radar
description: >
  机会雷达系统。从多信息源系统化采集和筛选商业机会，通过评分模型匹配个人能力边界，
  输出可落地的机会清单。TRIGGER when: user asks to "找机会" "挖掘需求" "采集商机"
  "机会分析" "筛选副业方向" "scan opportunities" "demand research" "market research"
  "跑一下机会雷达" "看看有什么机会"。
version: "1.0"
last_updated: 2026-04-16
---

# 机会雷达系统

从多个信息源系统化采集商业机会，用统一评分模型筛选出适合自己做的方向。

## 前置条件

- Python 3 + DrissionPage（`pip install DrissionPage`）
- profile.md 已填写（个人能力边界、兴趣方向、资源约束）

## 个人资料

任务开始前，先读取 `profile.md`。

profile.md 定义了谁在使用这个系统——他的技术能力、资源约束、兴趣方向、变现偏好和红线。所有评分环节中的"自身匹配"维度，都基于这份资料。

**profile 修改后无需改任何代码或规则，评分自动适配。**

## AI 能力接入

机会雷达不是纯规则系统，AI 贯穿整个流程。明确哪些环节必须接入大模型：

| 环节 | AI 能力 | 说明 |
|------|---------|------|
| 需求提取 | 文本大模型 | 从标题/描述/评论中提取一句话需求，判断真需求还是噪音 |
| 评分 | 文本大模型 | 四维评分，需要理解语义，不能纯规则 |
| 图片信息提取 | 视觉大模型 | 帖子中的截图、对比图、产品图含关键信息，必须用视觉模型提取 |
| 每日简报生成 | 文本大模型 | 汇总当日数据，生成可读的日报 |
| 去重合并 | 文本大模型 | 判断不同来源的条目是否指向同一需求 |

### 图片处理规范

帖子中的图片（截图、对比图、产品图、数据图）往往是最有价值的信息，比如：

- 收益截图 → 变现能力验证
- 产品对比图 → 竞品功能差距
- 用户反馈截图 → 真实痛点
- 流量数据图 → 需求规模

**禁止使用传统 OCR**，原因：
1. 中文识别准确率不够，尤其手写体、模糊截图
2. 速度慢，批量处理时效率太低
3. 无法理解图片语义（只知道"写了什么"，不知道"什么意思"）

**统一使用视觉大模型（Vision LLM）处理图片**，优势：
1. 能理解图片含义，不仅仅是识别文字
2. 能从图中提取结构化信息（数据、对比关系、功能列表）
3. 中文处理能力强

#### 智能判断：是否需要图片理解

图片理解**速度慢、成本高**，不能无差别调用。必须先做判断：

**原则：文本信息足够判断时，跳过图片理解。**

判断流程：
1. 先用文本信息完成需求提取和初步评分
2. 判断是否满足以下任一条件：
   - 文本信息不足以提取需求描述（信息缺失）
   - 需要验证变现能力（收益截图、销量数据图）
   - 需要判断竞争差距（产品对比图、功能截图）
   - 图片是帖子核心内容而非配图（比如帖子就是一张图，文字只是标题）
3. 满足任一条件 → 调用视觉大模型分析图片
4. 不满足 → 跳过，节省成本和时间

采集脚本中图片处理流程：
```python
# 1. 采集时记录图片 URL
img_url = item.ele("css:img").attr("src")

# 2. 只记录 URL，不在此处调用视觉模型
item_data["images"] = [img_url]
```

**注意**：采集脚本当前只负责记录图片 URL。图片分析在阶段二（AI过滤）由 agent 根据上述判断逻辑决定是否调用视觉模型。当前阶段不下载到本地，也不接对象存储；等流程稳定后再考虑切到对象存储。采集和分析解耦，换模型不影响采集逻辑。

#### 文本大模型接入方式

当前使用火山引擎 doubao-1.5-pro-32k（OpenAI 兼容格式），用于需求提取、评分、去重合并、每日简报生成：

```python
from openai import OpenAI

client = OpenAI(
    api_key="ARK_API_KEY",
    base_url="https://ark.cn-beijing.volces.com/api/v3"
)

resp = client.chat.completions.create(
    model="doubao-1-5-pro-32k-250115",
    messages=[
        {"role": "system", "content": "你是一个产品需求分析师..."},
        {"role": "user", "content": "分析以下采集数据，提取机会..."}
    ]
)
result = resp.choices[0].message.content
```

兼容 OpenAI SDK，直接用 `openai` 包调用，只需改 `base_url` 和 `api_key`。

#### 视觉大模型接入方式

当前使用火山引擎 doubao-seed-1-8（支持图片理解），API 调用示例：

```python
import httpx

url = "https://ark.cn-beijing.volces.com/api/v3/responses"
headers = {
    "authorization": "Bearer ARK_API_KEY",
    "content-type": "application/json"
}
payload = {
    "model": "doubao-seed-1-8-251228",
    "input": [{
        "role": "user",
        "content": [
            {"type": "input_image", "image_url": "图片URL或base64"},
            {"type": "input_text", "text": "分析这张图片中的商业机会信号..."}
        ]
    }]
}
resp = httpx.post(url, json=payload, headers=headers)
```

## 采集规范（必须遵守）

所有数据源的采集根据实际情况选择最佳工具：

### 采集方式选择

| 方式 | 适用场景 | 工具 |
|------|---------|------|
| 公开 API 直接调用 | 有稳定免费 API 的平台 | httpx |
| curl_cffi TLS 指纹模拟 | API 有 TLS 指纹检测（如 toolify.ai），需模拟浏览器指纹 | curl_cffi (`impersonate='chrome110'`) |
| DrissionPage 页面采集 | 需要登录/反爬/API 受限的平台（默认选择） | DrissionPage |
| ruyiPage 页面操作 | 纯代替人工操作（填表/发布），响应体较小时 | ruyiPage |
| 第三方数据仓库 | GitHub 上的预抓取数据项目 | httpx 下载 JSON |

### ruyiPage 采集规范

当使用 ruyiPage 时，采集策略按优先级：

1. **访问目标页面**
2. **人工模拟点击/滚动/翻页进入目标页面后，用 intercept 拦截接口响应体**（优先）—— 数据结构化、干净、量大
3. **DOM 元素提取**（降级）—— 确认没有可用接口时，使用 `page.ele()` 提取页面内容
4. **图片 URL 记录**（补充）—— 帖子中的图片保留原始 URL，留待 AI 按需分析

listener 示例（监听响应）：
```python
page.listen.start("api.example.com/data", method="POST")
# 触发页面操作（滚动、点击等）
packet = page.listen.wait(timeout=10)
if packet:
    body = packet.response.body
page.listen.stop()
```

DOM 提取示例：
```python
items = page.eles("css:.list-item")
for item in items:
    title = item.ele("css:h3").text
    # ...
```

**禁止绕过页面直接请求目标网站的业务接口**，必须通过 DrissionPage 访问页面后，再用 listener 或 DOM 提取。

**例外**：大模型 API（文本理解、图片理解）允许直接通过 SDK / `httpx` / OpenAI 兼容接口调用，不受上述限制。有稳定免费公开 API 的数据源（如 Hacker News API、HuggingFace API）也允许直接 httpx 调用。

详细的 DrissionPage 自动化与监听方式，以本 skill 中现有脚本实现为准；如需 listener 用法，可参考 `sources/shengcai/scripts/fengxiangbiao_collector.py`。

## 工作流

### 阶段一：采集

根据指定的数据源（或全部），运行对应脚本采集原始数据。

每个 source 的脚本在 `sources/<source-name>/scripts/` 下，产出该数据源的原始 JSON。

### 阶段二：AI 过滤

将原始数据交给 AI，执行：
1. **去重**：同一机会在不同源出现，合并
2. **需求提取**：从数据中提取一句话需求描述
3. **信号判断**：判断这是真需求还是噪音

**对于 BuilderPulse 数据源（全球开发者信号），使用五维分析框架**（详见 `references/builderpulse-methodology.md`）：
1. **发现机会** — 产品发布、搜索飙升、开源增长、用户抱怨
2. **技术选型** — 公司关停/降级、工具增长、模型趋势、技术栈分析
3. **竞争情报** — 收入定价、旧项目复活、"XX 已死"迁移
4. **趋势判断** — 关键词频率变化、VC 方向、降温词、新词雷达
5. **行动触发** — 结合 profile.md 给出具体构建建议

**多源交叉验证**：
- 3+ 数据源同时出现相同信号 → 高置信度 ★★★
- 2 个数据源交叉验证 → 中置信度 ★★
- 仅 1 个数据源 → 低置信度 ★

中文数据源和 BuilderPulse 数据源在阶段二合并去重，共同进入阶段三评分。

### 阶段三：评分

对过滤后的机会按四维模型打分（1-5分），详见 `references/scoring-model.md`：

| 维度 | 1分 | 5分 |
|------|------|------|
| 痛点强度 | 偶尔有人提 | 大量用户抱怨/付费购买 |
| 付费意愿 | 没人卖同类产品 | 多个卖家，价格稳定 |
| 竞争空白 | 头部完善，4.5星以上 | 现有产品评分低，差评集中 |
| 自身匹配 | 需要学新技术 | 现有技术栈1-2周能出MVP |

**自身匹配维度必须基于 profile.md 判断，不得假设用户能力。**

### 阶段四：输出

- 单个机会 → `templates/opportunity-card.md` 格式
- 每日简报 → `templates/daily-brief.md` 格式

总分 15 分以上标记为「重点关注」，12-14 分标记为「值得观察」。

## 存储策略

当前阶段只要求把采集结果和分析结果保存到本地 JSON 文件中，不接数据库。

- 阶段一：保存原始采集 JSON
- 阶段二/三：保存过滤、评分后的 JSON
- 阶段四：保存机会卡 JSON 或日报 Markdown

## 数据源

每个数据源在 `sources/` 下有独立目录，结构统一：

```
sources/<name>/
├── README.md      # 这个源的说明、目标URL、采集要点
├── scripts/       # 采集脚本
└── data/          # 采集结果 JSON
```

当前已注册的数据源：

### 中文数据源

|| 名称 | 说明 | 状态 |
||------|------|------|
|| shengcai | 生财有术·风向标 | 开发中 |
| xiaohongshu | 小红书 | 待开发 |
| plugin-marketplace | 全球插件市场 | 待开发 |
| xiaoyuzhou | 小宇宙播客 | 待开发 |
| trustmrr | TrustMRR verified startup revenue | 已就绪 |
| theresanaiforthat | ThereIsAnAIForThat 每周 AI 工具趋势 | 已就绪 |

### 全球开发者信号源（BuilderPulse）

|| 名称 | 平台 | 采集方式 | 状态 |
||------|------|---------|------|
|| builderpulse/hackernews | Hacker News | 公开 API（httpx） | 已就绪 |
| builderpulse/github-trending | GitHub Trending | ruyiPage 页面采集 | 已就绪 |
| builderpulse/producthunt | Product Hunt | ruyiPage 页面采集 | 已就绪 |
| builderpulse/huggingface | HuggingFace | 公开 API（httpx） | 已就绪 |
| builderpulse/google-trends | Google Trends（125 国热搜） | GitHub 预抓取 JSON + RSS 兜底 | 已就绪 |
| builderpulse/reddit | Reddit (SaaS/SideProject/Entrepreneur/startups) | ruyiPage 页面采集 | 已就绪 |

BuilderPulse 数据源的详细说明见 `sources/builderpulse/README.md`。

### 数据源分组采集策略

BuilderPulse 的 6 个数据源可以按依赖关系分批运行：

```bash
# 第一批：API 类（无需浏览器，速度快）
python sources/builderpulse/hackernews/scripts/collector.py
python sources/builderpulse/huggingface/scripts/collector.py
python sources/builderpulse/google-trends/scripts/collector.py

# 第二批：浏览器类（需要 ruyiPage，较慢）
python sources/builderpulse/github-trending/scripts/collector.py
python sources/builderpulse/producthunt/scripts/collector.py
python sources/builderpulse/reddit/scripts/collector.py
```

### AI 产品增长趋势（Toolify.ai）

|| 名称 | 平台 | 采集方式 | 状态 ||
||------|------|---------|------||
|| toolifyai | Toolify.ai 趋势榜单 | curl_cffi TLS 指纹模拟 | 已就绪 |

Toolify.ai 每月发布 AI 产品增长榜单（Top 300），按 growth 排序。采集脚本 `sources/toolifyai/scripts/toolify_radar.py` 实现了两层筛选：

- **第一层**：月访问量 0.5M~3M + 月增长量 >= 300K
- **第二层**：回溯3个月验证持续增长（至少2个月出现在 Top300，且出现时 growth > 0）

关键 API 细节：
- 端点：`https://www.toolify.ai/self-api/v1/top/month-top`
- `per_page=300` 一次拉完整月数据
- `date` 参数取月份第1天（如3月榜单用 `2026-03-01`）
- 最新一期为上个月的榜单（当月尚未发布）
- 响应中 `handle` 字段 → 详情页 URL：`https://www.toolify.ai/zh/tool/{handle}`

依赖：`pip install curl_cffi python-dateutil`

### Verified startup revenue（TrustMRR）

|| 名称 | 平台 | 采集方式 | 状态 ||
||------|------|---------|------||
|| trustmrr | TrustMRR verified revenue marketplace | 官方 API（httpx，需要 `TRUSTMRR_API_KEY`） | 已就绪 |

TrustMRR 提供已验证收入的 startup 数据，适合发现「已经有人付费」的产品形态和交易价格区间。采集脚本 `sources/trustmrr/scripts/collector.py` 支持：

- 按收入、MRR、增长、售价、分类、出售状态筛选
- 保存统一 `latest.json`、时间戳快照、原始 API 数据
- 可选调用详情接口补充 tech stack，用于评分阶段判断自身匹配度

依赖：`pip install httpx`

### AI 工具每周趋势（ThereIsAnAIForThat）

|| 名称 | 平台 | 采集方式 | 状态 ||
||------|------|---------|------||
|| theresanaiforthat | ThereIsAnAIForThat weekly trending | DrissionPage 静态 DOM 解析 | 已就绪 |

ThereIsAnAIForThat 每周趋势页适合发现正在获得关注的 AI 工具。采集脚本 `sources/theresanaiforthat/scripts/collector.py` 只访问公开页面 `https://theresanaiforthat.com/trending/week/`，不调用 `/api/`，从 `#data_hist ul.tasks > li` 解析：

- `li` 属性：工具 ID、名称、任务分类、外链、榜单 rank
- `.li_row`：工具详情页、图标、短描述、任务标签
- `.comment` / `.ai_footer`：精选评论、发布时间、价格、浏览量、收藏数、评分

依赖：`pip install DrissionPage lxml`

新加数据源：在 `sources/` 下新建目录，写好 README.md，本文件列表中加一行即可。

## 目录结构

```
opportunity-radar/
├── SKILL.md                         # 本文件（主入口）
├── profile.md                       # 个人资料
├── CLAUDE.md                        # Claude Code 入口
├── .cursorrules                     # Cursor 入口
├── AGENTS.md                        # Codex 入口
├── sources/                         # 数据源（可插拔模块）
│   ├── shengcai/
│   ├── xiaohongshu/
│   ├── plugin-marketplace/
│   ├── xiaoyuzhou/
│   ├── toolifyai/                   # AI 产品增长趋势（curl_cffi）
│   ├── trustmrr/                    # Verified startup revenue（官方 API）
│   ├── theresanaiforthat/           # ThereIsAnAIForThat 每周趋势（DOM 解析）
│   └── builderpulse/                # 全球开发者信号源（6 大平台）
│       ├── README.md                # 总览 + 采集方式说明
│       ├── hackernews/              # Hacker News（公开 API）
│       ├── github-trending/         # GitHub Trending（ruyiPage）
│       ├── producthunt/             # Product Hunt（ruyiPage）
│       ├── huggingface/             # HuggingFace（公开 API）
│       ├── google-trends/           # Google Trends（GitHub JSON + RSS）
│       └── reddit/                  # Reddit（ruyiPage）
├── templates/                       # 统一输出模板
│   ├── opportunity-card.md          # 机会卡片
│   └── daily-brief.md               # 每日简报
└── references/                      # 参考资料（按需读取）
    ├── scoring-model.md             # 评分模型详细说明
    ├── methodology.md               # 方法论
    └── builderpulse-methodology.md  # BuilderPulse 五维分析框架
```
