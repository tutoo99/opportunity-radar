#!/usr/bin/env python3
"""
Toolify.ai 探针脚本

目标：
1. 用 DrissionPage 过 Cloudflare
2. 调用榜单 API，查看响应结构
3. 保存第一个产品的完整字段到 data/ 目录

用法：python3 toolify_probe.py
"""

import json
import os
import sys
import time
from datetime import datetime

from DrissionPage import ChromiumOptions, ChromiumPage

# 强制 unbuffered
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# ============ 配置 ============
OUTPUT_DIR = os.path.expanduser(
    "~/.hermes/skills/opportunity-radar/sources/toolifyai/data"
)
LANDING_URL = "https://www.toolify.ai/zh/Best-trending-AI-Tools"
# 2026年4月 -> 看3月榜单。date 参数需要试：可能是 2026-03-01
# 原始 curl 用的是 2026-02-01，但那个 curl 是什么时候抓的？
# 先试几个可能的 date
TEST_DATES = [
    "2026-03-01",  # 如果 date 代表「查看哪个月」
    "2026-02-01",  # 原始 curl 的值
    "2025-03-01",  # 可能是年月错位
]
# ==============================


def env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def build_options():
    opts = ChromiumOptions()
    if env_flag("DP_HEADLESS"):
        opts.headless()
    # 使用独立的 user data 目录，避免和已打开的 Chrome 冲突
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="toolify_dp_")
    opts.set_user_data_path(tmp_dir)
    opts.set_argument("--no-first-run")
    opts.set_argument("--disable-blink-features=AutomationControlled")
    # 明确指定端口
    opts.set_local_port(19222)
    return opts


def create_page():
    opts = build_options()
    page = ChromiumPage(opts)
    return page


def pass_cloudflare(page):
    """访问落地页，等待 Cloudflare 验证通过"""
    log(f"[1] 访问 {LANDING_URL}")
    page.get(LANDING_URL)

    # 等待 Cloudflare 挑战完成（最多等 60 秒）
    log("[2] 等待 Cloudflare 验证...")
    for i in range(30):
        time.sleep(2)
        title = page.title or ""
        if "Just a moment" not in title:
            log(f"   Cloudflare 已通过 (title: {title})")
            return True
        if i % 5 == 4:
            log(f"   还在等待... ({(i+1)*2}s)")
    log("   超时，Cloudflare 未通过")
    return False


def fetch_api_via_browser(page, api_url):
    """通过浏览器的 fetch API 调用接口，绕过 CF"""
    log(f"[3] 通过浏览器调用 API...")
    # DrissionPage run_js 需要用同步 XHR + as_expr=True 才能拿到返回值
    # 或者用 run_js_loaded 返回 Promise
    js_code = """
    (function() {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', arguments[0], false);  // 同步
        xhr.withCredentials = true;
        xhr.setRequestHeader('accept', 'application/json, text/plain, */*');
        xhr.setRequestHeader('locale', 'zh');
        xhr.setRequestHeader('timezone', 'Asia/Shanghai');
        xhr.send();
        if (xhr.status === 200) {
            return JSON.stringify({
                status: xhr.status,
                ok: true,
                body: xhr.responseText.substring(0, 200000)
            });
        } else {
            return JSON.stringify({
                status: xhr.status,
                ok: false,
                body: xhr.responseText.substring(0, 2000)
            });
        }
    })()
    """
    result = page.run_js(js_code, api_url, as_expr=True)
    if result:
        try:
            return json.loads(result)
        except (json.JSONDecodeError, TypeError):
            log(f"   JS 返回值解析失败: {str(result)[:200]}")
            return None
    log("   run_js 返回 None")
    return None


def log(msg):
    """同时写 stdout 和日志文件"""
    print(msg, flush=True)
    LOG_FILE and LOG_FILE.write(msg + "\n") and LOG_FILE.flush()


LOG_FILE = None
def open_log():
    global LOG_FILE
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_path = os.path.join(OUTPUT_DIR, "probe.log")
    LOG_FILE = open(log_path, "a", encoding="utf-8")
    return log_path


def main():
    log_path = open_log()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    page = create_page()
    try:
        print(f"   浏览器已启动", flush=True)
        # Step 1: 过 CF
        if not pass_cloudflare(page):
            log("无法通过 Cloudflare，退出")
            return

        # Step 2: 尝试不同 date 调 API
        base_api = "https://www.toolify.ai/self-api/v1/top/month-top"
        for date_val in TEST_DATES:
            api_url = f"{base_api}?page=1&per_page=5&date={date_val}&order_by=growth&direction=desc"
            log(f"[3] 尝试 date={date_val}")
            api_result = fetch_api_via_browser(page, api_url)
            if not api_result:
                log(f"   无返回，跳过")
                continue

            if not api_result["ok"]:
                log(f"   HTTP {api_result['status']}，跳过")
                continue

            log(f"   成功！HTTP 200")
            # 解析响应
            body = json.loads(api_result["body"])
            log(f"[4] 响应结构分析 (date={date_val}):")

            if isinstance(body, dict):
                log(f"   顶层 keys: {list(body.keys())}")
                if "data" in body:
                    items = body["data"]
                    if isinstance(items, list):
                        log(f"   data 是列表, 共 {len(items)} 条")
                        if len(items) > 0:
                            first = items[0]
                            log(f"\n   --- 第1个产品的所有字段 ---")
                            log(json.dumps(first, indent=2, ensure_ascii=False))
                    else:
                        log(f"   data 类型: {type(items)}")
                        log(f"   data 内容: {json.dumps(items, indent=2, ensure_ascii=False)[:2000]}")
                else:
                    log(f"   无 data 字段，完整响应:")
                    log(json.dumps(body, indent=2, ensure_ascii=False)[:3000])
            elif isinstance(body, list):
                log(f"   响应是列表, 共 {len(body)} 条")
                if len(body) > 0:
                    log(f"\n   --- 第1个产品的所有字段 ---")
                    log(json.dumps(body[0], indent=2, ensure_ascii=False))
            else:
                log(f"   响应类型: {type(body)}")
                log(f"   内容: {str(body)[:2000]}")

            # 保存完整探针结果
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            probe_path = os.path.join(OUTPUT_DIR, f"probe_{timestamp}.json")
            with open(probe_path, "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": timestamp,
                    "date_param": date_val,
                    "api_url": api_url,
                    "http_status": api_result["status"],
                    "response": body
                }, f, ensure_ascii=False, indent=2)
            log(f"\n[5] 探针结果已保存: {probe_path}")
            break  # 第一个成功的 date 就退出

    finally:
        page.quit()
        log("[6] 浏览器已关闭")


if __name__ == "__main__":
    main()
