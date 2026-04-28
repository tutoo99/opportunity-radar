#!/usr/bin/env python3
"""
Toolify.ai 探针脚本 v3

监听页面所有 API 请求，找到真正的榜单接口。
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
    log_path = os.path.join(OUTPUT_DIR, "probe3.log")
    LOG_FILE = open(log_path, "w", encoding="utf-8")

    import tempfile
    opts = ChromiumOptions()
    opts.set_user_data_path(tempfile.mkdtemp(prefix="toolify_dp_"))
    opts.set_argument("--no-first-run")
    opts.set_argument("--disable-blink-features=AutomationControlled")
    opts.set_local_port(19244)

    log("启动浏览器...")
    page = ChromiumPage(opts)
    log("浏览器已启动")

    try:
        # 监听所有 api 请求
        log("设置 listen，拦截所有 self-api 请求...")
        page.listen.start("self-api")

        log(f"访问 {LANDING_URL}")
        page.get(LANDING_URL)

        # 等 CF
        for i in range(30):
            time.sleep(2)
            title = page.title or ""
            if "Just a moment" not in title:
                log(f"CF 已通过: {title[:60]}")
                break
        else:
            log("CF 超时")
            return

        time.sleep(8)

        # 收集所有已捕获的请求
        log("\n收集所有 self-api 请求...")
        api_requests = []
        # listen 步进收集
        for i in range(10):
            pkt = page.listen.wait(timeout=3)
            if pkt:
                url = pkt.url
                log(f"  [{pkt.method}] {url[:120]}")
                api_requests.append({
                    "url": url,
                    "method": pkt.method,
                    "status": pkt.response.status if pkt.response else None,
                })
                # 读响应
                if pkt.response:
                    try:
                        body = pkt.response.body[:3000]
                        api_requests[-1]["body_preview"] = body
                        # 解析 JSON
                        try:
                            j = json.loads(body)
                            if isinstance(j, dict):
                                api_requests[-1]["json_keys"] = list(j.keys())
                                if "data" in j and isinstance(j["data"], list):
                                    api_requests[-1]["data_count"] = len(j["data"])
                                    if len(j["data"]) > 0:
                                        api_requests[-1]["first_item_keys"] = list(j["data"][0].keys())
                            elif isinstance(j, list):
                                api_requests[-1]["data_count"] = len(j)
                                if len(j) > 0:
                                    api_requests[-1]["first_item_keys"] = list(j[0].keys())
                        except:
                            pass
                    except:
                        pass
            else:
                break

        page.listen.stop()

        log(f"\n共捕获 {len(api_requests)} 个 self-api 请求")
        log("=" * 60)
        for r in api_requests:
            log(f"\n[{r['method']}] {r['url'][:150]}")
            log(f"  Status: {r['status']}")
            if "json_keys" in r:
                log(f"  JSON keys: {r['json_keys']}")
            if "data_count" in r:
                log(f"  Data items: {r['data_count']}")
            if "first_item_keys" in r:
                log(f"  First item keys: {r['first_item_keys']}")

        # 保存
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = os.path.join(OUTPUT_DIR, f"probe3_{timestamp}.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(api_requests, f, ensure_ascii=False, indent=2)
        log(f"\n已保存: {save_path}")

    finally:
        page.quit()
        log("浏览器已关闭")
        if LOG_FILE:
            LOG_FILE.close()


if __name__ == "__main__":
    main()
