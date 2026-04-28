#!/usr/bin/env python3
"""
Toolify.ai 机会雷达

通过 toolify.ai 的月度增长榜单，发现持续增长的 AI 产品领域。

流程：
1. 检查本地已沉淀的月度数据，只拉缺少的月份（增量采集）
2. 第一层筛选：月访问量 0.5M~3M + 月增长量 >= 300K
3. 第二层筛选：对第一层产品回溯N个月，验证持续增长
4. 输出产品简报（含详情页链接）

依赖：pip install curl_cffi python-dateutil
"""

import json
import os
import time
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from curl_cffi import requests

# ============================================================
# 配置
# ============================================================
DATA_DIR = os.path.expanduser(
    "~/.hermes/skills/opportunity-radar/sources/toolifyai/data"
)
MONTHLY_DIR = os.path.join(DATA_DIR, "monthly")  # 月度数据存放目录

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9",
    "locale": "zh",
    "referer": "https://www.toolify.ai/zh/Best-trending-AI-Tools",
    "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "timezone": "Asia/Shanghai",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
}

COOKIES = {
    "locale": "zh",
    "toolify_userinfo": "%7B%7D",
    "timezone": "Asia%2FShanghai",
}

API_BASE = "https://www.toolify.ai/self-api/v1/top/month-top"

# 筛选参数（可随意调整，不需要重新采集数据）
VISIT_MIN = 500_000       # 0.5M
VISIT_MAX = 3_000_000     # 3M
GROWTH_MIN = 300_000      # 300K
LOOKBACK_MONTHS = 3       # 回溯月份


# ============================================================
# 工具函数
# ============================================================

def fmt_num(n):
    """格式化数字，如 1500000 -> 1.50M"""
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    elif n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


def get_date_params():
    """
    计算需要的月份参数。
    当前月份的榜单尚未发布，最新一期是上个月的。
    例如 5月份，最新榜单是4月的，date=2026-04-01。
    回溯3个月就是4月、3月、2月、1月。
    """
    today = date.today()
    latest = date(today.year, today.month, 1) - relativedelta(months=1)
    months = []
    for i in range(LOOKBACK_MONTHS + 1):
        d = latest - relativedelta(months=i)
        months.append(d.strftime("%Y-%m-%d"))
    return months


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ============================================================
# 数据沉淀：本地月度 JSON 存储
# ============================================================

def monthly_json_path(date_str):
    """月份文件路径，如 monthly/2026-03.json"""
    return os.path.join(MONTHLY_DIR, f"{date_str}.json")


def load_monthly(date_str):
    """加载本地已有的月度数据，返回 list 或 None"""
    path = monthly_json_path(date_str)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get("items", [])
        return data if isinstance(data, list) else None
    except Exception:
        return None


def save_monthly(date_str, items, meta=None):
    """保存月度数据到本地"""
    os.makedirs(MONTHLY_DIR, exist_ok=True)
    payload = {
        "date": date_str,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(items),
        "items": items,
    }
    if meta:
        payload["meta"] = meta
    path = monthly_json_path(date_str)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def list_local_months():
    """列出本地已有的月份数据"""
    if not os.path.exists(MONTHLY_DIR):
        return []
    months = []
    for fname in sorted(os.listdir(MONTHLY_DIR)):
        if fname.endswith(".json"):
            months.append(fname.replace(".json", ""))
    return months


# ============================================================
# API 调用
# ============================================================

def fetch_month_top(date_str, page=1, per_page=300):
    """获取某月的增长榜单"""
    params = {
        "page": str(page),
        "per_page": str(per_page),
        "date": date_str,
        "order_by": "growth",
        "direction": "desc",
    }
    resp = requests.get(
        API_BASE,
        headers=HEADERS,
        cookies=COOKIES,
        params=params,
        impersonate="chrome110",
        timeout=30,
    )
    if resp.status_code != 200:
        log(f"  API 错误: HTTP {resp.status_code}")
        return None, None

    data = resp.json()
    if data.get("code") != 200:
        log(f"  业务错误: {data.get('message')}")
        return None, None

    return data["data"].get("data", []), data["data"]


# ============================================================
# 增量采集
# ============================================================

def collect_needed_months(needed_months):
    """
    增量采集：只拉本地缺少的月份，已有的直接用本地数据。
    返回所有月份的数据（本地+新拉），按时间倒序。
    """
    local = list_local_months()
    log(f"本地已有: {local}")
    log(f"需要月份: {needed_months}")

    missing = [m for m in needed_months if m not in local]
    cached = [m for m in needed_months if m in local]

    if missing:
        log(f"需要新采集: {missing}")
    else:
        log("所有月份均有本地数据，无需采集")

    all_data = {}

    # 先加载本地数据
    for date_str in cached:
        items = load_monthly(date_str)
        if items:
            all_data[date_str] = items
            log(f"  本地加载 {date_str}: {len(items)} 条")
        else:
            # 本地文件损坏，重新拉
            log(f"  本地文件损坏，重新采集: {date_str}")
            missing.append(date_str)

    # 采集缺失的月份
    for date_str in missing:
        log(f"  采集 {date_str} ...")
        items, raw_data = fetch_month_top(date_str)
        if items is None:
            log(f"    采集失败，跳过")
            continue

        total = raw_data.get("total", 0)
        log(f"    成功! Top {len(items)} 条 (总共 {total})")

        # 沉淀到本地
        save_monthly(date_str, items, meta={"total": total})
        all_data[date_str] = items

        time.sleep(1)

    return all_data


# ============================================================
# 筛选逻辑
# ============================================================

def layer1_filter(items):
    """
    第一层筛选：当月榜单中
    - 月访问量 0.5M ~ 3M
    - 月增长量 >= 300K
    """
    results = []
    for item in items:
        visits = item.get("month_visited_count", 0)
        growth = item.get("growth", 0)
        if VISIT_MIN <= visits <= VISIT_MAX and growth >= GROWTH_MIN:
            results.append(item)
    return results


def layer2_filter(candidates, historical_data):
    """
    第二层筛选：对第一层候选产品，回溯验证是否持续增长。

    持续增长判定：
    - 在回溯的每个月中都能找到该产品
    - 月增长量不为0（即仍在增长，没有停滞或下降到0）
    - 判定条件：在榜单中出现 >= 2次，且出现时都有正增长（growth > 0）

    返回通过筛选的产品，附带历史数据。
    """
    passed = []

    for candidate in candidates:
        handle = candidate["handle"]
        name = candidate["name"]
        history = []

        for month_info in historical_data:
            month_label = month_info["label"]
            items = month_info["items"]

            # 在该月数据中查找
            found = None
            for item in items:
                if item.get("handle") == handle:
                    found = item
                    break

            if found is None:
                history.append({
                    "month": month_label,
                    "in_top300": False,
                    "visits": None,
                    "growth": None,
                    "growth_rate": None,
                })
            else:
                g = found.get("growth", 0)
                history.append({
                    "month": month_label,
                    "in_top300": True,
                    "visits": found.get("month_visited_count"),
                    "growth": g,
                    "growth_rate": found.get("growth_rate"),
                })

        # 判定：至少出现2次，且出现时都有正增长
        in_list_count = sum(1 for h in history if h["in_top300"])
        positive_growth_count = sum(
            1 for h in history if h["in_top300"] and h["growth"] and h["growth"] > 0
        )

        if in_list_count >= 2 and positive_growth_count == in_list_count:
            passed.append({
                **candidate,
                "history": history,
                "in_list_count": in_list_count,
                "positive_growth_count": positive_growth_count,
            })
        else:
            log(f"  未通过: {name} (出现{in_list_count}次, 正增长{positive_growth_count}次)")

    return passed


def generate_brief(products):
    """生成产品简报"""
    if not products:
        return "没有发现持续增长的 AI 产品领域。"

    lines = []
    lines.append("=" * 70)
    lines.append(f"  Toolify.ai 机会雷达简报")
    lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"  筛选条件: 月访问量 {fmt_num(VISIT_MIN)}~{fmt_num(VISIT_MAX)} | "
                  f"月增长量 >= {fmt_num(GROWTH_MIN)} | 持续增长 {LOOKBACK_MONTHS} 个月")
    lines.append(f"  通过筛选: {len(products)} 个产品")
    lines.append("=" * 70)

    for i, p in enumerate(products, 1):
        handle = p["handle"]
        name = p["name"]
        desc = p.get("description", "无描述")[:80]
        tags = ", ".join(p.get("tags", [])[:5])
        detail_url = f"https://www.toolify.ai/zh/tool/{handle}"

        lines.append("")
        lines.append(f"{'─' * 60}")
        lines.append(f"  #{i}  {name}")
        lines.append(f"  详情: {detail_url}")
        lines.append(f"  描述: {desc}")
        if tags:
            lines.append(f"  标签: {tags}")

        lines.append(f"  当月访问: {fmt_num(p.get('month_visited_count', 0))}  "
                      f"增长: {fmt_num(p.get('growth', 0))}  "
                      f"增长率: {p.get('growth_rate', 0):.1%}")

        lines.append(f"  历史趋势:")
        for h in reversed(p["history"]):  # 从最早到最近
            if h["in_top300"]:
                g_str = fmt_num(h["growth"]) if h["growth"] else "N/A"
                v_str = fmt_num(h["visits"]) if h["visits"] else "N/A"
                r_str = f"{h['growth_rate']:.1%}" if h["growth_rate"] is not None else "N/A"
                lines.append(f"    {h['month']}  访问 {v_str}  增长 {g_str}  增长率 {r_str}")
            else:
                lines.append(f"    {h['month']}  未进入 Top300")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


# ============================================================
# 主流程
# ============================================================

def main():
    os.makedirs(MONTHLY_DIR, exist_ok=True)

    # Step 1: 计算需要的月份
    months = get_date_params()

    # Step 2: 增量采集（只拉缺少的）
    all_data = collect_needed_months(months)

    if not all_data:
        log("无可用数据，退出")
        return

    # 构建时间倒序列表（最新在前）
    sorted_months = sorted(all_data.keys(), reverse=True)
    latest_month = sorted_months[0]
    latest_items = all_data[latest_month]
    historical_months = sorted_months[1:]

    # Step 3: 第一层筛选（只筛最新月份）
    log(f"\n第一层筛选: 月访问 {fmt_num(VISIT_MIN)}~{fmt_num(VISIT_MAX)}, 月增长 >= {fmt_num(GROWTH_MIN)}")
    candidates = layer1_filter(latest_items)
    log(f"  当月({latest_month})共 {len(latest_items)} 个产品")
    log(f"  通过第一层: {len(candidates)} 个产品")

    if not candidates:
        log("没有通过第一层筛选的产品")
        # 依然保存简报
        brief = "没有发现持续增长的 AI 产品领域。"
        print(brief)
        return

    for c in candidates:
        log(f"    - {c['name']}  访问:{fmt_num(c['month_visited_count'])}  "
            f"增长:{fmt_num(c['growth'])}  增长率:{c['growth_rate']:.1%}")

    # Step 4: 第二层筛选（用本地沉淀的历史数据）
    if not historical_months:
        log("无历史数据，跳过第二层筛选")
        final_products = candidates
        for p in final_products:
            p["history"] = []
    else:
        historical_data = [
            {"date_str": m, "label": m, "items": all_data[m]}
            for m in historical_months
        ]
        log(f"\n第二层筛选: 回溯 {len(historical_data)} 个月验证持续增长")
        final_products = layer2_filter(candidates, historical_data)
        log(f"  通过第二层: {len(final_products)} 个产品")

    # Step 5: 生成简报
    log("\n生成产品简报...")
    brief = generate_brief(final_products)
    print(brief)

    # Step 6: 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    brief_path = os.path.join(DATA_DIR, f"radar_brief_{timestamp}.txt")
    with open(brief_path, "w", encoding="utf-8") as f:
        f.write(brief)
    log(f"\n简报已保存: {brief_path}")

    json_path = os.path.join(DATA_DIR, f"radar_result_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "filter": {
                "visit_min": VISIT_MIN,
                "visit_max": VISIT_MAX,
                "growth_min": GROWTH_MIN,
                "lookback_months": LOOKBACK_MONTHS,
            },
            "months_used": sorted_months,
            "layer1_count": len(candidates),
            "layer2_count": len(final_products),
            "products": final_products,
        }, f, ensure_ascii=False, indent=2)
    log(f"结果已保存: {json_path}")

    return final_products


if __name__ == "__main__":
    main()
