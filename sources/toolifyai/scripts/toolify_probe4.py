#!/usr/bin/env python3
"""
Toolify.ai 探针脚本 v4

1. 加载榜单页面
2. 找到月份切换按钮，点击触发 month-top API
3. 拦截真实请求 URL，确认参数格式
4. 保存完整响应结构
"""

import json
import os
import sys
import time
from datetime import datetime

from DrissionPage import ChromiumOptions, ChromiumPage

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

OUTPUT_DIR = os.path.expanduser(
    "~/.hermes/skills/opportunity-radar/sources/toolifyai/data"
)
LANDING_URL = "https://www.toolify.ai/zh/Best-trending-AI-Tools"
LOG_FILE = None


def log(msg):
    print(msg, flush=True)
    if LOG_FILE:
        LOG_FILE.write(msg + "\n")
        LOG_FILE.flush()


def find_month_elements(page):
    """在页面上找月份相关的可点击元素"""
    candidates = []
    # 找所有包含日期/月份文字的元素
    selectors = [
        'tag:button',
        'tag:a',
        'tag:span',
        'css:.month',
        'css:[class*="month"]',
        'css:[class*="date"]',
        'css:[class*="tab"]',
        'css:[class*="filter"]',
        'css:[class*="period"]',
        'css:[class*="calendar"]',
        'css:select',
    ]
    for sel in selectors:
        try:
            eles = page.eles(sel)
            for el in eles:
                text = el.text.strip()
                if not text or len(text) > 50:
                    continue
                # 匹配月份关键词
                month_keywords = [
                    "2025", "2026", "1月", "2月", "3月", "4月", "5月", "6月",
                    "7月", "8月", "9月", "10月", "11月", "12月",
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December",
                    "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
                    "Trending", "Best", "Growth", "Popular",
                    "增长", "趋势", "热门", "排行", "榜单",
                ]
                matched = [kw for kw in month_keywords if kw.lower() in text.lower()]
                if matched:
                    candidates.append({
                        "text": text,
                        "tag": el.tag,
                        "class": el.attr("class") or "",
                        "matched_keywords": matched,
                        "element": el,
                    })
        except Exception as e:
            pass

    # 去重
    seen = set()
    unique = []
    for c in candidates:
        key = c["text"] + "|" + c["class"]
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def dump_page_structure(page, log_func):
    """导出页面关键区域的 HTML 结构"""
    # 尝试找页面导航/筛选区域的 HTML
    for sel in ['css:nav', 'css:[class*="header"]', 'css:[class*="toolbar"]',
                'css:[class*="filter"]', 'css:[class*="tab"]', 'css:[class*="sidebar"]']:
        try:
            eles = page.eles(sel)
            for el in eles[:2]:
                html = el.html[:3000]
                if html and len(html) > 50:
                    log_func(f"\n--- {sel} HTML (前3000字) ---")
                    log_func(html)
        except:
            pass


def main():
    global LOG_FILE
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_path = os.path.join(OUTPUT_DIR, "probe4.log")
    LOG_FILE = open(log_path, "w", encoding="utf-8")

    import tempfile
    opts = ChromiumOptions()
    opts.set_user_data_path(tempfile.mkdtemp(prefix="toolify_dp_"))
    opts.set_argument("--no-first-run")
    opts.set_argument("--disable-blink-features=AutomationControlled")
    opts.set_local_port(19255)

    log("启动浏览器...")
    page = ChromiumPage(opts)
    log("浏览器已启动")

    try:
        # 监听所有 API 请求（不限定关键词，全抓）
        log("设置 listen，拦截所有 self-api 请求...")
        page.listen.start("self-api")

        log(f"访问 {LANDING_URL}")
        page.get(LANDING_URL)

        # 等 CF
        for i in range(30):
            time.sleep(2)
            title = page.title or ""
            if "Just a moment" not in title and "安全验证" not in title:
                log(f"CF 已通过: {title[:80]}")
                break
        else:
            log("CF 超时")
            return

        time.sleep(5)

        # 清空之前的请求（简单的等待，不依赖 steps）
        log("清空已捕获的请求...")
        try:
            for _ in range(5):
                page.listen.wait(timeout=1)
        except Exception as e:
            log(f"  清空时异常(可忽略): {e}")

        # Step 1: 找月份相关元素
        log("\n=== Step 1: 搜索页面上的月份相关元素 ===")
        month_els = find_month_elements(page)
        log(f"找到 {len(month_els)} 个候选元素:")
        for i, m in enumerate(month_els):
            log(f"  [{i}] text='{m['text']}' tag={m['tag']} class='{m['class']}' "
                f"matched={m['matched_keywords']}")

        # Step 2: 导出页面筛选区域结构
        log("\n=== Step 2: 导出页面导航/筛选区域 ===")
        dump_page_structure(page, log)

        # Step 3: 尝试点击月份按钮触发 API
        log("\n=== Step 3: 点击候选元素触发 API ===")
        for i, m in enumerate(month_els):
            log(f"\n点击 [{i}] '{m['text']}'...")
            try:
                el = m["element"]
                # 先滚到元素可见
                el.scroll.to_see()
                time.sleep(0.5)
                el.click()
                time.sleep(3)

                # 检查是否触发了新请求
                new_requests = []
                while page.listen.steps() > 0:
                    pkt = page.listen.wait(timeout=2)
                    if pkt:
                        new_requests.append({
                            "url": pkt.url,
                            "method": pkt.method,
                            "status": pkt.response.status if pkt.response else None,
                        })

                if new_requests:
                    log(f"  -> 触发了 {len(new_requests)} 个请求:")
                    for r in new_requests:
                        log(f"     [{r['method']}] {r['url'][:150]} (status={r['status']})")
                        # 特别关注 month-top
                        if "month-top" in r["url"] or "top" in r["url"] or "trending" in r["url"]:
                            log(f"     *** 这是榜单接口！***")
                            # 读响应体
                            if pkt and pkt.response:
                                try:
                                    body = pkt.response.body
                                    log(f"     响应体前500字: {body[:500]}")
                                except:
                                    pass
                else:
                    log(f"  -> 没有触发新请求")

                # 截图
                ss_path = os.path.join(OUTPUT_DIR, f"probe4_click_{i}_{m['text'][:10]}.png")
                try:
                    page.get_screenshot(path=ss_path, full_page=False)
                    log(f"  截图: {ss_path}")
                except:
                    pass

            except Exception as e:
                log(f"  点击失败: {e}")

            # 如果已经找到了 month-top，就不再继续
            if any("month-top" in str(r.get("url", "")) for r in new_requests):
                break

            # 回退或等待
            time.sleep(1)

        # 最终收集
        page.listen.stop()
        log("\n=== 完成 ===")

    finally:
        page.quit()
        log("浏览器已关闭")
        if LOG_FILE:
            LOG_FILE.close()


if __name__ == "__main__":
    main()
