#!/usr/bin/env python3
"""
DrissionPage 版风向标接口探针。

目的：
1. 验证 `searchTopic` 在 DrissionPage listener 下是否也会出现大响应读取异常；
2. 作为正式采集链路的验证脚本保留，用于并行排查监听稳定性；
3. 重点关注第 2 页 / 第 1 页翻页后的响应体读取是否稳定。

默认策略：
- 进入首页；
- 悬浮“项目”；
- 点击二级菜单“风向标”；
- 保持默认“热门”页；
- 点击下一页拿第 2 页；
- 再点上一页拿第 1 页；
- 使用 DrissionPage `listen` 读取 `packet.response.body`。

可选环境变量：
- DP_BROWSER_PATH: 指定浏览器可执行文件路径
- DP_USER_DATA_PATH: 指定 Chromium user data 目录，默认使用仓库内持久目录
- DP_USE_SYSTEM_USER_PATH: 是否复用系统 Chromium 用户目录，默认 0
- DP_USER: profile 名称，默认 Default
- DP_LOCAL_PORT: 指定本地调试端口；使用持久 user data 时默认 9333
- DP_HEADLESS: 是否无头，1/true 表示启用，默认 0
"""

import json
import os
import random
import time
from datetime import datetime

from DrissionPage import ChromiumOptions, ChromiumPage


BASE_URL = "https://scys.com/"
FENXIANGBIAO_PAGE_URL = "https://scys.com/opportunity?filter=all"
SEARCH_TOPIC_API_URL = "https://scys.com/shengcai-web/client/homePage/searchTopic"
OUTPUT_DIR = os.path.expanduser("~/.hermes/skills/opportunity-radar/sources/shengcai/data")
DEFAULT_USER_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "browser_user_data"))


def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def human_pause(min_seconds=0.8, max_seconds=1.8):
    time.sleep(random.uniform(min_seconds, max_seconds))


def env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_int(name, default=0):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def create_page():
    opts = ChromiumOptions()
    opts.headless(env_flag("DP_HEADLESS", False))

    browser_path = os.getenv("DP_BROWSER_PATH")
    if browser_path:
        opts.set_browser_path(browser_path)

    user_data_path = os.getenv("DP_USER_DATA_PATH")
    if user_data_path:
        os.makedirs(user_data_path, exist_ok=True)
        opts.set_local_port(env_int("DP_LOCAL_PORT", 9333))
        opts.set_user_data_path(user_data_path)
        opts.set_user(os.getenv("DP_USER", "Default"))
    elif env_flag("DP_USE_SYSTEM_USER_PATH", False):
        opts.use_system_user_path(True)
        opts.set_user(os.getenv("DP_USER", "Default"))
        opts.auto_port(True)
    else:
        os.makedirs(DEFAULT_USER_DATA_DIR, exist_ok=True)
        opts.set_local_port(env_int("DP_LOCAL_PORT", 9333))
        opts.set_user_data_path(DEFAULT_USER_DATA_DIR)
        opts.set_user(os.getenv("DP_USER", "Default"))

    return ChromiumPage(opts)


def wait_until(page, predicate_js, timeout=15, interval=0.3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = page.run_js(predicate_js)
            if result:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def wait_for_ready(page, timeout=20):
    return wait_until(
        page,
        """
        return !!document.querySelector('ul.arco-pagination-list li');
        """,
        timeout=timeout,
    )


def wait_for_url_contains(page, text, timeout=15, interval=0.3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if text in (page.url or ""):
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def is_login_page(page):
    try:
        url = page.url or ""
    except Exception:
        url = ""
    if "login" in url:
        return True

    try:
        return bool(
            page.run_js(
                """
                return !!document.querySelector('input[type="password"], .login, [class*="login"]');
                """
            )
        )
    except Exception:
        return False


def wait_for_login(page, timeout=180, interval=2):
    if not is_login_page(page):
        return True

    print(f"[LOGIN] 检测到未登录，请扫码登录...（最多等待 {timeout} 秒）")
    deadline = time.time() + timeout
    last_report = 0

    while time.time() < deadline:
        if not is_login_page(page):
            print("[LOGIN] 检测到已登录，继续执行")
            human_pause(2.0, 3.5)
            return True

        waited = int(timeout - max(deadline - time.time(), 0))
        if waited - last_report >= 20:
            last_report = waited
            print(f"[LOGIN] 仍在等待扫码...（已等待 {waited} 秒）")

        time.sleep(interval)

    return False


def find_text_element(page, text, timeout=8):
    end_time = time.time() + timeout
    selectors = [
        f"text:{text}",
        f"xpath://*[normalize-space(text())='{text}']",
        f"xpath://*[contains(normalize-space(text()), '{text}')]",
    ]

    while time.time() < end_time:
        for selector in selectors:
            try:
                ele = page.ele(selector, timeout=1)
                if ele:
                    return ele
            except Exception:
                continue
        time.sleep(0.2)
    return None


def click_visible_text(page, text, exact=True):
    matcher = "=== targetText" if exact else ".includes(targetText)"
    script = f"""
    const targetText = arguments[0];
    const nodes = Array.from(document.querySelectorAll('body *'));
    for (const el of nodes) {{
        const txt = (el.textContent || '').trim();
        if (!txt || !(txt {matcher})) continue;
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (style.display === 'none' || style.visibility === 'hidden') continue;
        if (rect.width <= 0 || rect.height <= 0) continue;
        el.click();
        return true;
    }}
    return false;
    """
    return bool(page.run_js(script, text))


def navigate_to_fengxiangbiao(page):
    print("[STEP] 首页悬浮“项目”并点击“风向标”")
    page.get(BASE_URL)
    human_pause(2.0, 3.5)

    if not wait_for_login(page, timeout=180):
        raise RuntimeError("扫码登录超时，未能继续执行。")

    project_menu = find_text_element(page, "项目", timeout=10)
    if not project_menu:
        raise RuntimeError("首页未找到“项目”菜单")

    try:
        project_menu.hover()
    except Exception:
        page.actions.move_to(project_menu, duration=0.4)
    human_pause(0.8, 1.6)

    fengxiangbiao_menu = find_text_element(page, "风向标", timeout=10)
    clicked = False
    if fengxiangbiao_menu:
        try:
            fengxiangbiao_menu.click()
            clicked = True
        except Exception:
            try:
                fengxiangbiao_menu.click.left(by_js=True)
                clicked = True
            except Exception:
                clicked = False

    if not clicked:
        clicked = click_visible_text(page, "风向标", exact=True)

    if not clicked:
        clicked = click_visible_text(page, "风向标", exact=False)

    if not clicked:
        raise RuntimeError("悬浮后未找到可点击的“风向标”二级菜单")

    if not wait_for_url_contains(page, "/opportunity", timeout=15):
        raise RuntimeError("点击“风向标”后未成功跳转到目标页")

    human_pause(2.0, 3.5)
    if not wait_for_ready(page, timeout=20):
        raise RuntimeError("风向标页面未加载出分页控件")

    return True


def click_next_page(page):
    return bool(
        page.run_js(
            """
            const buttons = document.querySelectorAll('ul.arco-pagination-list > span');
            if (!buttons || buttons.length < 2) return false;
            const nextButton = buttons[1];
            if ((nextButton.className || '').includes('disabled')) return false;
            nextButton.click();
            return true;
            """
        )
    )


def click_prev_page(page):
    return bool(
        page.run_js(
            """
            const buttons = document.querySelectorAll('ul.arco-pagination-list > span');
            if (!buttons || buttons.length < 1) return false;
            const prevButton = buttons[0];
            if ((prevButton.className || '').includes('disabled')) return false;
            prevButton.click();
            return true;
            """
        )
    )


def wait_active_page(page, page_num, timeout=10):
    return wait_until(
        page,
        f"""
        const active = document.querySelector('.arco-pagination-item-active');
        return active ? active.textContent.trim() === '{page_num}' : false;
        """,
        timeout=timeout,
    )


def packet_to_payload(packet):
    response = packet.response
    body = response.body
    raw_body = response.raw_body or ""

    if isinstance(body, dict):
        payload = body
    elif isinstance(body, str):
        payload = json.loads(body)
    elif isinstance(raw_body, str):
        payload = json.loads(raw_body)
    else:
        raise RuntimeError(f"无法解析响应体，body 类型={type(body)}")

    return {
        "status": response.status,
        "content_type": response.headers.get("content-type"),
        "content_length": response.headers.get("content-length"),
        "raw_body_length": len(raw_body) if isinstance(raw_body, str) else None,
        "payload": payload,
    }


def capture_search_topic(page, trigger_action, action_name):
    page.listen.start(SEARCH_TOPIC_API_URL, method="POST")
    try:
        human_pause(0.2, 0.6)
        if trigger_action() is False:
            raise RuntimeError(f"{action_name} 触发动作失败")

        packet = page.listen.wait(timeout=20)
        if not packet:
            raise RuntimeError(f"{action_name} 未监听到 searchTopic 请求")

        payload_info = packet_to_payload(packet)
        payload = payload_info["payload"]
        items = payload.get("data", {}).get("items", [])
        print(
            f"[INFO] {action_name} status={payload_info['status']} "
            f"items={len(items)} raw_len={payload_info['raw_body_length']}"
        )
        return payload_info
    finally:
        page.listen.stop()


def extract_topics(raw_data):
    topics = []
    items = raw_data.get("data", {}).get("items", [])

    for item in items:
        topic = item.get("topicDTO", {})
        user = item.get("topicUserDTO", {})
        comments = item.get("topicCommentDTOList", [])
        tags = [m.get("value", "") for m in topic.get("menuList", [])]

        comment_texts = []
        for comment in comments:
            comment_texts.append(comment.get("content", ""))
            for reply in comment.get("replies") or []:
                comment_texts.append(reply.get("content", ""))

        topics.append(
            {
                "topic_id": topic.get("topicId", ""),
                "entity_id": topic.get("entityId", ""),
                "title": topic.get("showTitle", ""),
                "content": topic.get("articleContent", ""),
                "ai_summary": topic.get("aiSummaryContent", ""),
                "tags": tags,
                "author": user.get("name", ""),
                "author_level": user.get("createUserLevel", 0),
                "like_count": topic.get("likeCount", 0),
                "comment_count": topic.get("commentsCount", 0),
                "coin_count": topic.get("coinCount", 0),
                "favorite_count": topic.get("favoriteCount", 0),
                "reading_count": topic.get("readingCount", 0),
                "comments_text": comment_texts,
                "image_urls": topic.get("imageList", []),
                "mini_image_urls": topic.get("miniImageList", []),
                "created_at": topic.get("gmtCreate", 0),
                "type": topic.get("type", ""),
                "source_page_url": FENXIANGBIAO_PAGE_URL,
            }
        )

    return topics


def save_probe_result(page2_info=None, page1_info=None):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUTPUT_DIR, f"drissionpage_probe_{timestamp}.json")

    result = {
        "framework": "DrissionPage",
        "captured_at": datetime.now().isoformat(),
        "page2": None,
        "page1": None,
    }

    for key, info in (("page2", page2_info), ("page1", page1_info)):
        if not info:
            continue
        payload = info["payload"]
        result[key] = {
            "status": info["status"],
            "content_type": info["content_type"],
            "content_length": info["content_length"],
            "raw_body_length": info["raw_body_length"],
            "items_count": len(payload.get("data", {}).get("items", [])),
            "topics": extract_topics(payload),
        }

    with open(path, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)

    print(f"[SAVED] {path}")
    return path


def main():
    print("=" * 50)
    print(f"[START] DrissionPage 风向标探针 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    ensure_dirs()
    page = None
    page2_info = None
    page1_info = None

    try:
        page = create_page()
        navigate_to_fengxiangbiao(page)

        if not wait_for_ready(page, timeout=20):
            raise RuntimeError("未找到分页控件，页面可能未加载完成或未进入热门页。")

        print("[STEP] 采集第 2 页")
        page2_info = capture_search_topic(page, lambda: click_next_page(page), "第2页")
        wait_active_page(page, 2, timeout=10)
        human_pause(1.0, 2.0)

        print("[STEP] 采集第 1 页")
        page1_info = capture_search_topic(page, lambda: click_prev_page(page), "第1页")
        wait_active_page(page, 1, timeout=10)

        save_probe_result(page2_info, page1_info)
        print("[DONE] DrissionPage 探针完成")

    finally:
        if page:
            try:
                page.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
