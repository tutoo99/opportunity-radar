#!/usr/bin/env python3
"""
风向标 AI 分析脚本。

输入：
- 优先读取 `fengxiangbiao_latest.json`
- 不存在时回退到 `latest.json`

输出：
- `fengxiangbiao_analyzed.json`        全量分析结果
- `fengxiangbiao_opportunities.json`   通过筛选的机会项
- `fengxiangbiao_brief.md`             Markdown 简报

环境变量：
- ANALYZE_PROVIDER            文本模型供应商：ark（默认）/ glm
- ARK_API_KEY                 火山引擎 API Key（ark 供应商时必填）
- ARK_BASE_URL                默认 https://ark.cn-beijing.volces.com/api/v3
- FENXIANGBIAO_TEXT_MODEL     ark 默认 doubao-1-5-pro-32k-250115
- FENXIANGBIAO_VISION_MODEL   默认 doubao-seed-1-8-251228
- FENXIANGBIAO_ENABLE_VISION  默认 1，设为 0 可关闭图片分析
- GLM_API_KEY                 智谱 API Key（glm 供应商时必填）
- GLM_BASE_URL                默认 https://open.bigmodel.cn/api/paas/v4
- GLM_TEXT_MODEL              默认 glm-4-plus
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "sources" / "shengcai" / "data"
PROFILE_PATH = ROOT_DIR / "profile.md"

DEFAULT_INPUT_CANDIDATES = [
    DATA_DIR / "fengxiangbiao_latest.json",
    DATA_DIR / "latest.json",
]

ANALYZED_PATH = DATA_DIR / "fengxiangbiao_analyzed.json"
OPPORTUNITIES_PATH = DATA_DIR / "fengxiangbiao_opportunities.json"
BRIEF_PATH = DATA_DIR / "fengxiangbiao_brief.md"
FOR_ME_PATH = DATA_DIR / "fengxiangbiao_for_me.json"
FOR_ME_BRIEF_PATH = DATA_DIR / "fengxiangbiao_for_me.md"

PROVIDER = os.getenv("ANALYZE_PROVIDER", "ark").strip().lower()

ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
TEXT_MODEL = os.getenv("FENXIANGBIAO_TEXT_MODEL", "doubao-1-5-pro-32k-250115")
VISION_MODEL = os.getenv("FENXIANGBIAO_VISION_MODEL", "doubao-seed-1-8-251228")

GLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
GLM_TEXT_MODEL = os.getenv("GLM_TEXT_MODEL", "glm4.7")


@dataclass
class ModelConfig:
    api_key: str
    base_url: str = ARK_BASE_URL
    text_model: str = TEXT_MODEL
    vision_model: str = VISION_MODEL
    enable_vision: bool = True
    provider: str = PROVIDER


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def read_profile_text() -> str:
    return PROFILE_PATH.read_text(encoding="utf-8")


def choose_input_path(cli_input: Optional[str]) -> Path:
    if cli_input:
        path = Path(cli_input).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"指定输入文件不存在：{path}")
        return path

    for path in DEFAULT_INPUT_CANDIDATES:
        if path.exists():
            return path

    raise FileNotFoundError("未找到可分析的输入文件：fengxiangbiao_latest.json / latest.json")


def clean_html(text: str) -> str:
    text = text or ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_text(text: str) -> str:
    text = clean_html(text)
    return text.replace("\u00a0", " ").strip()


def build_analysis_context(item: Dict[str, Any]) -> Dict[str, Any]:
    comments = item.get("comments_text") or []
    comments = [normalize_text(comment) for comment in comments if normalize_text(comment)]

    content = normalize_text(item.get("content", ""))
    ai_summary = normalize_text(item.get("ai_summary", ""))
    title = normalize_text(item.get("title", ""))
    tags = item.get("tags") or []

    merged_text_parts = [title, content, ai_summary, " / ".join(tags), " | ".join(comments[:8])]
    merged_text = "\n".join(part for part in merged_text_parts if part)

    return {
        "topic_id": item.get("topic_id"),
        "title": title,
        "content": content,
        "ai_summary": ai_summary,
        "tags": tags,
        "comments_text": comments,
        "image_urls": item.get("image_urls") or [],
        "reading_count": item.get("reading_count", 0),
        "like_count": item.get("like_count", 0),
        "comment_count": item.get("comment_count", 0),
        "favorite_count": item.get("favorite_count", 0),
        "coin_count": item.get("coin_count", 0),
        "is_bid_winning": item.get("is_bid_winning", False),
        "source_page_url": item.get("source_page_url"),
        "merged_text": merged_text,
    }


def should_request_vision(context: Dict[str, Any], text_result: Dict[str, Any]) -> bool:
    if not context.get("image_urls"):
        return False

    if not text_result.get("need_image_analysis"):
        return False

    return True


def get_model_config(enable_vision: bool) -> ModelConfig:
    provider = PROVIDER
    if provider == "glm":
        api_key = os.getenv("GLM_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("缺少 GLM_API_KEY，无法执行 AI 分析。")
        return ModelConfig(
            api_key=api_key,
            base_url=GLM_BASE_URL,
            text_model=GLM_TEXT_MODEL,
            enable_vision=False,  # GLM vision not supported yet
            provider="glm",
        )
    # 默认 ark
    api_key = os.getenv("ARK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("缺少 ARK_API_KEY，无法执行 AI 分析。")
    return ModelConfig(api_key=api_key, enable_vision=enable_vision, provider="ark")


def extract_json_from_text(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("模型返回为空")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"未能从模型输出中提取 JSON：{text[:200]}")

    return json.loads(match.group(0))


def call_text_model(config: ModelConfig, system_prompt: str, user_prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=120, max_retries=1)
    resp = client.chat.completions.create(
        model=config.text_model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content or ""


def call_vision_model(config: ModelConfig, image_urls: List[str], prompt: str) -> str:
    import httpx

    payload = {
        "model": config.vision_model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}]
                + [{"type": "input_image", "image_url": url} for url in image_urls[:3]],
            }
        ],
    }
    headers = {
        "authorization": f"Bearer {config.api_key}",
        "content-type": "application/json",
    }
    response = httpx.post(
        f"{config.base_url.rstrip('/')}/responses",
        headers=headers,
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()

    text_parts: List[str] = []
    for item in data.get("output", []):
        for content_item in item.get("content", []):
            if content_item.get("type") == "output_text":
                text_parts.append(content_item.get("text", ""))

    return "\n".join(part for part in text_parts if part).strip()


def build_text_analysis_prompts(context: Dict[str, Any], profile_text: str) -> tuple[str, str]:
    system_prompt = f"""
你是一个商业机会分析师，负责从“风向标”帖子中识别真实需求并按四维模型评分。

必须遵守：
1. 输出必须是合法 JSON，不要输出 Markdown。
2. 判断“自身匹配”时，必须引用下方 profile 中的具体能力，不允许臆测。
3. 如果只是资讯、政策、热点、普通工具推荐，而没有明确用户痛点或产品切入点，`is_real_opportunity` 应偏向 false。
4. `score_pain`、`score_payment`、`score_gap`、`score_fit` 都是 1-5 整数。
5. `confidence` 输出 0-1 之间的小数。

用户 profile：
{profile_text}

输出 JSON schema：
{{
  "is_real_opportunity": true,
  "signal_type": "需求机会/工具推荐/资讯动态/案例拆解/政策信号/噪音",
  "demand_summary": "一句话需求描述",
  "target_user": "目标用户",
  "problem_statement": "核心痛点",
  "payment_signal": "付费意愿判断",
  "competition_gap": "竞争空白判断",
  "evidence_points": ["证据1", "证据2"],
  "need_image_analysis": false,
  "image_analysis_reason": "为什么需要或不需要看图",
  "score_pain": 1,
  "score_payment": 1,
  "score_gap": 1,
  "score_fit": 1,
  "fit_reason": "必须结合 profile 说明",
  "is_fit_for_me": true,
  "fit_penalty_reason": "如果不适合我，说明卡在哪",
  "action_priority_for_me": "立即验证/低成本观察/暂不投入",
  "suggested_mvp": "建议的最小产品/服务切入点",
  "risk_notes": ["风险1", "风险2"],
  "confidence": 0.78
}}
""".strip()

    user_prompt = f"""
请分析这条风向标帖子：

{json.dumps(context, ensure_ascii=False, indent=2)}

请特别注意：
- 标题、正文、评论、标签一起综合判断
- 不要把“有人推荐工具”自动等同于“有创业机会”
- 如果机会更偏服务、内容产品、信息整理，也可以判为真实机会
- `need_image_analysis=true` 只在文本明显不够、且图片可能承载核心信息时才给出
- `is_fit_for_me` 要更严格地结合 profile 中的时间、资金、兴趣方向、变现偏好、红线判断
- 如果和“需要大量运营”“灰色/擦边”“前期大投入”“偏离技术能力边界”冲突，应降低个人适配判断
""".strip()
    return system_prompt, user_prompt


def build_vision_prompt(context: Dict[str, Any], text_result: Dict[str, Any]) -> str:
    return f"""
请分析这些图片中是否包含对商业机会判断有帮助的信息。

帖子标题：{context.get("title")}
文本初判需求：{text_result.get("demand_summary")}
文本初判痛点：{text_result.get("problem_statement")}

请重点提取：
1. 图片是否包含收益、转化、对比、功能、评论、数据等强信号
2. 图片是否强化了“真实需求/可变现/竞争空白”的判断
3. 如果图片没有新增信息，也要明确说明

请只输出简洁中文，不要输出 Markdown。
""".strip()


def build_refine_prompt(
    context: Dict[str, Any],
    profile_text: str,
    text_result: Dict[str, Any],
    image_insights: str,
) -> tuple[str, str]:
    system_prompt = f"""
你是一个商业机会分析师，需要结合图片分析结果修正原始评分。
输出必须是合法 JSON，schema 与前一步完全一致。
用户 profile：
{profile_text}
""".strip()

    user_prompt = f"""
原始帖子上下文：
{json.dumps(context, ensure_ascii=False, indent=2)}

第一轮文本分析结果：
{json.dumps(text_result, ensure_ascii=False, indent=2)}

图片分析结果：
{image_insights}

请在必要时修正：
- `is_real_opportunity`
- 需求描述
- 四维评分
- 风险与 MVP 建议
""".strip()
    return system_prompt, user_prompt


def score_total(item: Dict[str, Any]) -> int:
    return int(item.get("score_pain", 0)) + int(item.get("score_payment", 0)) + int(item.get("score_gap", 0)) + int(item.get("score_fit", 0))


def classify_priority(total_score: int) -> str:
    if total_score >= 17:
        return "必做"
    if total_score >= 15:
        return "重点关注"
    if total_score >= 12:
        return "值得观察"
    if total_score >= 8:
        return "可选"
    return "暂缓"


def derive_fit_fields(item: Dict[str, Any]) -> None:
    score_fit = int(item.get("score_fit", 0) or 0)
    total_score = int(item.get("score_total", 0) or 0)
    fit_reason = (item.get("fit_reason") or "").strip()
    fit_penalty_reason = (item.get("fit_penalty_reason") or "").strip()

    if item.get("is_fit_for_me") is None:
        item["is_fit_for_me"] = score_fit >= 3

    if not fit_penalty_reason:
        if item["is_fit_for_me"]:
            fit_penalty_reason = "无明显个人约束冲突"
        elif fit_reason:
            fit_penalty_reason = fit_reason
        else:
            fit_penalty_reason = "与当前能力边界、时间投入或变现偏好不够匹配"
    item["fit_penalty_reason"] = fit_penalty_reason

    if not item.get("action_priority_for_me"):
        if not item.get("is_real_opportunity"):
            action_priority = "暂不投入"
        elif score_fit >= 4 and total_score >= 15:
            action_priority = "立即验证"
        elif score_fit >= 3 and total_score >= 12:
            action_priority = "低成本观察"
        else:
            action_priority = "暂不投入"
        item["action_priority_for_me"] = action_priority


def conservative_dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique_items = []
    for item in items:
        title = normalize_text(item.get("title", ""))
        key = (item.get("topic_id"), title)
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)
    return unique_items


def analyze_item(config: ModelConfig, item: Dict[str, Any], profile_text: str) -> Dict[str, Any]:
    context = build_analysis_context(item)
    system_prompt, user_prompt = build_text_analysis_prompts(context, profile_text)
    raw_result = call_text_model(config, system_prompt, user_prompt)
    text_result = extract_json_from_text(raw_result)

    image_insights = None
    final_result = text_result

    if config.enable_vision and should_request_vision(context, text_result):
        try:
            image_prompt = build_vision_prompt(context, text_result)
            image_insights = call_vision_model(config, context["image_urls"], image_prompt)
            if image_insights:
                refine_system, refine_user = build_refine_prompt(context, profile_text, text_result, image_insights)
                refine_result = call_text_model(config, refine_system, refine_user)
                final_result = extract_json_from_text(refine_result)
        except Exception as exc:
            image_insights = f"图片分析失败：{exc}"

    final_result["score_total"] = score_total(final_result)
    final_result["priority"] = classify_priority(final_result["score_total"])
    derive_fit_fields(final_result)
    final_result["image_insights"] = image_insights
    final_result["source"] = "shengcai"
    final_result["topic_id"] = item.get("topic_id")
    final_result["title"] = item.get("title")
    final_result["tags"] = item.get("tags") or []
    final_result["source_page_url"] = item.get("source_page_url")
    final_result["detail_url"] = item.get("detail_url")
    final_result["image_urls"] = item.get("image_urls") or []
    final_result["raw_metrics"] = {
        "reading_count": item.get("reading_count", 0),
        "like_count": item.get("like_count", 0),
        "comment_count": item.get("comment_count", 0),
        "favorite_count": item.get("favorite_count", 0),
        "coin_count": item.get("coin_count", 0),
        "is_bid_winning": item.get("is_bid_winning", False),
    }
    return final_result


def build_brief_markdown(opportunities: List[Dict[str, Any]], all_results: List[Dict[str, Any]]) -> str:
    today = time.strftime("%Y-%m-%d")
    must_do = [item for item in opportunities if item["priority"] == "必做"]
    focus = [item for item in opportunities if item["priority"] == "重点关注"]
    watch = [item for item in opportunities if item["priority"] == "值得观察"]

    def render_section(title: str, items: List[Dict[str, Any]]) -> List[str]:
        lines = [f"## {title}", ""]
        if not items:
            lines.append("- 暂无")
            lines.append("")
            return lines

        for item in items:
            lines.extend(
                [
                    f"### [{item['score_total']}分] {item['title']}",
                    f"- 来源：shengcai | [链接]({item.get('source_page_url') or ''})",
                    f"- 需求：{item.get('demand_summary', '')}",
                    f"- 痛点：{item.get('problem_statement', '')}",
                    f"- 付费意愿：{item.get('payment_signal', '')}",
                    f"- 竞争空白：{item.get('competition_gap', '')}",
                    f"- 自身匹配：{item.get('fit_reason', '')}",
                    f"- 是否适合我：{'是' if item.get('is_fit_for_me') else '否'}",
                    f"- 个人投入建议：{item.get('action_priority_for_me', '')}",
                    f"- 不匹配原因：{item.get('fit_penalty_reason', '')}",
                    f"- 建议切入：{item.get('suggested_mvp', '')}",
                    f"- 标签：{' | '.join(item.get('tags', []))}",
                    "",
                ]
            )
        return lines

    lines = [
        f"# 风向标机会分析简报 - {today}",
        "",
        f"- 原始条数：{len(all_results)}",
        f"- 识别为真实机会：{len(opportunities)}",
        "",
    ]
    lines.extend(render_section("必做（17-20分）", must_do))
    lines.extend(render_section("重点关注（15-16分）", focus))
    lines.extend(render_section("值得观察（12-14分）", watch))
    return "\n".join(lines).strip() + "\n"


def filter_for_me(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for item in items:
        if item.get("is_fit_for_me"):
            result.append(item)
            continue
        if item.get("action_priority_for_me") in {"立即验证", "低成本观察"}:
            result.append(item)
    result.sort(key=lambda value: (value.get("score_total", 0), value.get("confidence", 0)), reverse=True)
    return result


def build_for_me_markdown(items: List[Dict[str, Any]], all_results: List[Dict[str, Any]]) -> str:
    today = time.strftime("%Y-%m-%d")
    immediate = [item for item in items if item.get("action_priority_for_me") == "立即验证"]
    observe = [item for item in items if item.get("action_priority_for_me") == "低成本观察"]

    def render_group(title: str, rows: List[Dict[str, Any]]) -> List[str]:
        lines = [f"## {title}", ""]
        if not rows:
            lines.append("- 暂无")
            lines.append("")
            return lines

        for item in rows:
            lines.extend(
                [
                    f"### [{item.get('score_total', 0)}分] {item.get('title', '')}",
                    f"- 是否适合我：{'是' if item.get('is_fit_for_me') else '否'}",
                    f"- 行动建议：{item.get('action_priority_for_me', '')}",
                    f"- 需求：{item.get('demand_summary', '')}",
                    f"- 自身匹配：{item.get('fit_reason', '')}",
                    f"- 风险/限制：{item.get('fit_penalty_reason', '')}",
                    f"- 建议切入：{item.get('suggested_mvp', '')}",
                    f"- 标签：{' | '.join(item.get('tags', []))}",
                    "",
                ]
            )
        return lines

    lines = [
        f"# 风向标个人决策清单 - {today}",
        "",
        f"- 原始分析条数：{len(all_results)}",
        f"- 进入个人清单：{len(items)}",
        "",
    ]
    lines.extend(render_group("立即验证", immediate))
    lines.extend(render_group("低成本观察", observe))
    return "\n".join(lines).strip() + "\n"


def run_analysis(input_path: Path, enable_vision: bool) -> Dict[str, Any]:
    items = load_json(input_path)
    items = conservative_dedupe(items)
    profile_text = read_profile_text()
    config = get_model_config(enable_vision=enable_vision)

    all_results: List[Dict[str, Any]] = []
    opportunities: List[Dict[str, Any]] = []

    for index, item in enumerate(items, start=1):
        print(f"[ANALYZE] {index}/{len(items)} {item.get('title', '')[:40]}", flush=True)
        try:
            result = analyze_item(config, item, profile_text)
            all_results.append(result)
            if result.get("is_real_opportunity"):
                opportunities.append(result)
        except Exception as exc:
            print(f"[WARN] 分析失败：{item.get('title', '')[:30]} -> {exc}", flush=True)
            all_results.append(
                {
                    "source": "shengcai",
                    "topic_id": item.get("topic_id"),
                    "title": item.get("title"),
                    "analysis_error": str(exc),
                    "is_real_opportunity": False,
                    "priority": "暂缓",
                    "score_total": 0,
                    "is_fit_for_me": False,
                    "fit_penalty_reason": "分析失败，无法判断个人匹配度",
                    "action_priority_for_me": "暂不投入",
                    "tags": item.get("tags") or [],
                    "source_page_url": item.get("source_page_url"),
                    "detail_url": item.get("detail_url"),
                }
            )

    opportunities.sort(key=lambda value: (value.get("score_total", 0), value.get("confidence", 0)), reverse=True)
    for_me_items = filter_for_me(opportunities)

    save_json(ANALYZED_PATH, all_results)
    save_json(OPPORTUNITIES_PATH, opportunities)
    BRIEF_PATH.write_text(build_brief_markdown(opportunities, all_results), encoding="utf-8")
    save_json(FOR_ME_PATH, for_me_items)
    FOR_ME_BRIEF_PATH.write_text(build_for_me_markdown(for_me_items, all_results), encoding="utf-8")

    return {
        "input_path": str(input_path),
        "analyzed_count": len(all_results),
        "opportunity_count": len(opportunities),
        "for_me_count": len(for_me_items),
        "analyzed_path": str(ANALYZED_PATH),
        "opportunities_path": str(OPPORTUNITIES_PATH),
        "brief_path": str(BRIEF_PATH),
        "for_me_path": str(FOR_ME_PATH),
        "for_me_brief_path": str(FOR_ME_BRIEF_PATH),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="风向标 AI 分析脚本")
    parser.add_argument("--input", help="输入 JSON 路径，默认自动寻找 fengxiangbiao_latest.json / latest.json")
    parser.add_argument(
        "--disable-vision",
        action="store_true",
        help="关闭图片理解，仅使用文本分析",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = choose_input_path(args.input)
    summary = run_analysis(input_path=input_path, enable_vision=not args.disable_vision)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
