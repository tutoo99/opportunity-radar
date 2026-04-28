# 生财有术社群

## 数据源说明

生财有术是国内最大的创业/副业社群，内部有大量航海记录、项目复盘、需求讨论。

## 目标页面

- 生财有术 Web 端（需登录）
- 风向标页面：`https://scys.com/opportunity?filter=all`
- 航海手册页面
- 精华帖/热门讨论

## 采集策略

1. 用 DrissionPage 登录后从首页进入风向标页面 `https://scys.com/opportunity?filter=all`
2. 优先 listener 监听列表接口 `https://scys.com/shengcai-web/client/homePage/searchTopic` 的响应体
3. 降级方案：DOM 提取帖子列表元素

## 接口返回结构

`searchTopic` 接口每次响应默认返回 20 条数据，顶层结构如下：

```json
{
  "success": true,
  "status": 0,
  "message": null,
  "data": {
    "items": [...],
    "total": 10000
  }
}
```

`data.items` 中每条记录的核心节点：

- `topicDTO`：帖子主体，包含 `showTitle`、`articleContent`、`imageList`、`menuList`、`likeCount`、`commentsCount`、`favoriteCount`、`readingCount`、`aiSummaryContent` 等
- `topicUserDTO`：发帖用户信息，包含 `name`、`avatar`、`createUserLevel` 等
- `topicCommentDTOList`：评论列表，评论对象下可能还有 `replies`
- `detailUrl`：当前观察到可能为 `null`，不能依赖它作为详情链接

采集阶段优先保留上述结构中的关键字段，供后续 AI 过滤和评分使用。

## 重点关注的数据

- 航海项目的报名人数和完成率（判断热度）
- 帖子评论区的反复提问（判断痛点）
- 项目复盘帖中的"踩坑"和"没做好的地方"（判断竞争空白）

## 产出格式

阶段一输出原始采集 JSON；进入 AI 过滤和评分后，再整理为 `templates/opportunity-card.md` 对齐的结构。

## 注意事项

- 需要有效的 Chromium 登录态（user data 持久化 cookie）
- 脚本默认复用仓库内 `browser_user_data/` 持久目录；首次运行登录一次后，后续脚本应复用同一登录态
- 如需强制复用系统浏览器用户目录，可设置 `DP_USE_SYSTEM_USER_PATH=1`
- 生财有术有反爬机制，操作间隔需 humanize
- 社区内容有付费墙，部分帖子可能无法访问
- 如果文本信息不足且帖子图片包含关键信号，可把图片 URL 交给视觉模型分析；当前阶段不下载本地
