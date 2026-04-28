#!/usr/bin/env python3
"""
生财有术 - 风向标采集脚本（DrissionPage 版）

采集路径：
首页 -> 悬浮“项目” -> 点击“风向标” -> 默认热门页 -> 下一页/上一页触发 `searchTopic`

采集策略：
- 使用 DrissionPage listener 监听 `searchTopic`
- 在热门页通过真实分页点击触发接口
- 保留现有提取字段与 JSON 输出格式

可选环境变量：
- DP_BROWSER_PATH: 指定浏览器可执行文件路径
- DP_USER_DATA_PATH: 指定 Chromium user data 目录，默认使用仓库内持久目录
- DP_USE_SYSTEM_USER_PATH: 是否复用系统 Chromium 用户目录，默认 0
- DP_USER: Chromium profile 名称，默认 Default
- DP_LOCAL_PORT: 指定本地调试端口；使用持久 user data 时默认 9333
- DP_HEADLESS: 是否无头，默认 0
"""

import json
import os
import random
import time
from datetime import datetime

from DrissionPage import ChromiumOptions, ChromiumPage

# ============ 配置 ============
OUTPUT_DIR = os.path.expanduser("~/.hermes/skills/opportunity-radar/sources/shengcai/data")
DEFAULT_USER_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "browser_user_data"))
BASE_URL = "https://scys.com/"
FENXIANGBIAO_PAGE_URL = "https://scys.com/opportunity?filter=all"
SEARCH_TOPIC_API_URL = "https://scys.com/shengcai-web/client/homePage/searchTopic"
# ==============================


def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


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


def human_pause(min_seconds=0.8, max_seconds=2.0):
    time.sleep(random.uniform(min_seconds, max_seconds))


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
            if page.run_js(predicate_js):
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


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


def wait_for_ready(page, timeout=20):
    return wait_until(
        page,
        """
        return !!document.querySelector('ul.arco-pagination-list li');
        """,
        timeout=timeout,
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

    print("[INFO] 已通过首页菜单进入风向标热门页")
    return True


def is_hot_tab_active(page):
    try:
        result = page.run_js(
            """
            const active = document.querySelector(
                '.arco-tabs-tab-active, .ant-tabs-tab-active, .tab-active, [aria-selected="true"]'
            );
            return active ? active.textContent.trim() : '';
            """
        )
        text = str(result or "").strip()
        return text == "" or "热门" in text
    except Exception:
        return True


def click_next_page(page):
    clicked = bool(
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
    if clicked:
        wait_active_page(page, 2, timeout=10)
        human_pause(1.0, 2.0)
    return clicked


def click_prev_page(page):
    clicked = bool(
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
    if clicked:
        wait_active_page(page, 1, timeout=10)
        human_pause(1.0, 2.0)
    return clicked


def packet_to_payload(packet):
    response = packet.response
    body = response.body
    raw_body = response.raw_body or ""

    if isinstance(body, dict):
        return body
    if isinstance(body, str):
        return json.loads(body)
    if isinstance(raw_body, str):
        return json.loads(raw_body)

    raise RuntimeError(f"无法解析响应体，body 类型={type(body)}")


def capture_search_topic(page, trigger_action, action_name, retries=1):
    last_error = None

    for attempt in range(retries + 1):
        page.listen.start(SEARCH_TOPIC_API_URL, method="POST")
        try:
            human_pause(0.2, 0.6)
            if trigger_action() is False:
                raise RuntimeError("触发动作失败")

            packet = page.listen.wait(timeout=20)
            if not packet:
                raise RuntimeError("未监听到 searchTopic 请求")

            payload = packet_to_payload(packet)
            items = payload.get("data", {}).get("items", [])
            print(f"[INFO] {action_name} 监听成功，捕获 {len(items)} 条")
            return payload
        except Exception as exc:
            last_error = exc
            print(f"[WARN] {action_name} 第 {attempt + 1} 次监听失败: {exc}")
            if attempt < retries:
                human_pause(1.2, 2.5)
        finally:
            page.listen.stop()

    raise RuntimeError(f"{action_name} 监听失败：{last_error}")


def extract_topics(raw_data):
    topics = []
    items = raw_data.get("data", {}).get("items", [])

    for item in items:
        topic = item.get("topicDTO", {})
        user = item.get("topicUserDTO", {})
        comments = item.get("topicCommentDTOList", [])

        tags = [menu.get("value", "") for menu in topic.get("menuList", [])]
        is_bid_winning = "中标" in tags

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
                "is_bid_winning": is_bid_winning,
                "source_page_url": FENXIANGBIAO_PAGE_URL,
                "detail_url": item.get("detailUrl"),
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
            }
        )

    return topics


def save_data(topics, page_num=1):
    today = datetime.now().strftime("%Y%m%d")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"fengxiangbiao_{today}_{timestamp}_p{page_num}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(topics, file, ensure_ascii=False, indent=2)

    print(f"[SAVED] {filepath} ({len(topics)} 条)")
    return filepath


def merge_and_save(all_topics):
    today = datetime.now().strftime("%Y%m%d")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"fengxiangbiao_{today}_{timestamp}_all.json"
    filepath = os.path.join(OUTPUT_DIR, filename)

    seen = set()
    unique_topics = []
    for topic in all_topics:
        topic_id = topic["topic_id"]
        if topic_id and topic_id not in seen:
            seen.add(topic_id)
            unique_topics.append(topic)

    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(unique_topics, file, ensure_ascii=False, indent=2)
    print(f"[FINAL] {filepath} ({len(unique_topics)} 条去重后)")

    prefixed_latest_path = os.path.join(OUTPUT_DIR, "fengxiangbiao_latest.json")
    with open(prefixed_latest_path, "w", encoding="utf-8") as file:
        json.dump(unique_topics, file, ensure_ascii=False, indent=2)
    print(f"[FINAL] fengxiangbiao_latest.json ({len(unique_topics)} 条)")

    latest_path = os.path.join(OUTPUT_DIR, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as file:
        json.dump(unique_topics, file, ensure_ascii=False, indent=2)
    print(f"[FINAL] latest.json ({len(unique_topics)} 条，兼容别名)")

    return filepath


def main():
    print("=" * 50)
    print(f"[START] 风向标采集 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    ensure_dirs()
    page = None

    try:
        page = create_page()

        if not navigate_to_fengxiangbiao(page):
            print("[EXIT] 未能进入风向标页面，退出")
            return

        if is_hot_tab_active(page):
            print("[INFO] 当前停留在默认“热门”页")
        else:
            print("[WARN] 当前不在明显的“热门”页，但仍尝试点击分页采集")

        all_topics = []

        print("\n[COLLECT] 第2页...")
        try:
            raw2 = capture_search_topic(page, lambda: click_next_page(page), "第2页", retries=1)
            topics_page2 = extract_topics(raw2)
            save_data(topics_page2, page_num=2)
            all_topics.extend(topics_page2)
        except Exception as exc:
            print(f"[WARN] 第2页采集失败: {exc}")

        human_pause(1.5, 3.0)

        print("\n[COLLECT] 第1页...")
        try:
            raw1 = capture_search_topic(page, lambda: click_prev_page(page), "第1页", retries=1)
            topics_page1 = extract_topics(raw1)
            save_data(topics_page1, page_num=1)
            all_topics.extend(topics_page1)
        except Exception as exc:
            print(f"[WARN] 第1页采集失败: {exc}")

        print(f"\n[SUMMARY] 共采集 {len(all_topics)} 条")
        merge_and_save(all_topics)
        print("\n[DONE] 风向标采集完成")

    except Exception as exc:
        print(f"[ERROR] 采集异常: {exc}")
        import traceback
        traceback.print_exc()

    finally:
        if page:
            try:
                page.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
