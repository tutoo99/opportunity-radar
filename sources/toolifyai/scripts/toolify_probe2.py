#!/usr/bin/env python3
"""
Toolify.ai 探针脚本 v2

用 DrissionPage 的 listen 功能，拦截页面自身的网络请求，
找到真正的 API URL 和请求格式。
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


def main():
    global LOG_FILE
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_path = os.path.join(OUTPUT_DIR, "probe2.log")
    LOG_FILE = open(log_path, "w", encoding="utf-8")

    # 启动浏览器
    import tempfile
    opts = ChromiumOptions()
    opts.set_user_data_path(tempfile.mkdtemp(prefix="toolify_dp_"))
    opts.set_argument("--no-first-run")
    opts.set_argument("--disable-blink-features=AutomationControlled")
    opts.set_local_port(19233)

    log("启动浏览器...")
    page = ChromiumPage(opts)
    log("浏览器已启动")

    try:
        # 先设置 listen，拦截所有 month-top 请求
        log(f"设置 listen，拦截 month-top 请求...")
        page.listen.start("month-top")

        # 访问页面
        log(f"访问 {LANDING_URL}")
        page.get(LANDING_URL)

        # 等待 CF
        for i in range(30):
            time.sleep(2)
            title = page.title or ""
            if "Just a moment" not in title:
                log(f"CF 已通过: {title[:60]}")
                break
        else:
            log("CF 超时")
            return

        # 等待页面完全加载
        time.sleep(5)

        # 尝试滚动页面触发更多请求
        log("滚动页面...")
        for _ in range(3):
            page.scroll.down(500)
            time.sleep(2)

        # 尝试点击不同的月份标签
        log("查找月份选择器...")
        try:
            month_btns = page.eles("tag:button")
            for btn in month_btns:
                text = btn.text.strip()
                if text and len(text) < 20:
                    log(f"  找到按钮: {text}")
        except Exception as e:
            log(f"  查找按钮失败: {e}")

        # 等待捕获请求
        log("等待捕获 month-top 请求...")
        packets = []
        for i in range(15):
            pkt = page.listen.wait(timeout=5)
            if pkt:
                log(f"  捕获到请求: {pkt.url[:100]}")
                packets.append({
                    "url": pkt.url,
                    "method": pkt.method,
                    "response_status": pkt.response.status if pkt.response else None,
                })
                # 如果有 response，尝试读取 body
                if pkt.response:
                    try:
                        body_text = pkt.response.body[:2000]
                        packets[-1]["response_body_preview"] = body_text
                    except:
                        packets[-1]["response_body_preview"] = "(读取失败)"
            else:
                if len(packets) > 0:
                    break  # 已经有结果了，不再等
                log(f"  等待中... ({(i+1)*5}s)")

        page.listen.stop()

        if not packets:
            log("没有捕获到 month-top 请求！")
            # 尝试搜索所有请求
            log("尝试手动 fetch 原始 curl 的完整 URL...")
            full_url = (
                "https://www.toolify.ai/self-api/v1/top/month-top"
                "?page=1&per_page=5&date=2026-02-01&order_by=growth&direction=desc"
            )
            js = """
            (function() {
                var xhr = new XMLHttpRequest();
                xhr.open('GET', arguments[0], false);
                xhr.send();
                return JSON.stringify({status: xhr.status, body: xhr.responseText.substring(0, 1000)});
            })()
            """
            result = page.run_js(js, full_url, as_expr=True)
            log(f"手动 fetch 结果: {result[:500] if result else 'None'}")
        else:
            log(f"\n共捕获 {len(packets)} 个请求")
            for p in packets:
                log(f"\n--- 请求详情 ---")
                log(f"  URL: {p['url']}")
                log(f"  Method: {p['method']}")
                log(f"  Status: {p['response_status']}")
                if 'response_body_preview' in p:
                    log(f"  Body (前2000字): {p['response_body_preview'][:500]}")

            # 保存捕获结果
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(OUTPUT_DIR, f"probe2_packets_{timestamp}.json")
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(packets, f, ensure_ascii=False, indent=2)
            log(f"\n已保存: {save_path}")

    finally:
        page.quit()
        log("浏览器已关闭")
        LOG_FILE.close()


if __name__ == "__main__":
    main()
