# 全球插件市场

## 数据源说明

全球各大生态的插件/应用市场，数据最公开、最结构化，是需求验证的第一站。

## 目标页面

按优先级：

1. **Chrome Web Store** — 搜索关键词 + 按用户数排序
2. **WordPress Plugin Directory** — 分类浏览 + 搜索
3. **VS Code Marketplace** — 按下载量排序
4. **GPT Store** — AI应用市场
5. **Shopify App Store** — 电商类
6. **npm / PyPI** — 开发者工具类（如纳入统一流程，仍按 DrissionPage + 页面观察优先）

## 采集策略

1. 用 DrissionPage 访问各市场搜索页
2. 优先 listener 监听列表加载接口（通常翻页时会请求下一页的JSON数据）
3. 降级方案：DOM 提取插件卡片（名称、评分、下载量、描述）
4. 进入插件详情页，提取评论区的差评

## 重点关注的数据

- 下载量/安装量 → 需求规模
- 评分 → 现有产品质量
- 差评内容 → 改进方向 = 你的切入点
- 定价 → 付费意愿

## 产出格式

阶段一输出原始采集 JSON；进入 AI 过滤和评分后，再整理为 `templates/opportunity-card.md` 对齐的结构。

## 注意事项

- Chrome Web Store 需登录态才能搜索，滚动加载
- 每天只采集一次，避免被封IP
- 目标网站的数据获取遵循统一规则：优先页面内 listener，其次 DOM；不要绕过页面直接请求业务接口
