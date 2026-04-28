#!/usr/bin/env python3
"""
生财有术 - 项目库采集脚本（DrissionPage 版）

采集路径：
首页 -> 悬浮“项目” -> 点击“项目库” -> 准备监听接口 -> 点击“热门” -> 保存接口响应 JSON

采集策略：
- 复用 Chromium 登录态；
- 使用 DrissionPage listener 监听 `projectLib/list`；
- 默认点击“热门”触发请求；
- 若“热门”已是激活态，则先切到备用 Tab（默认“最新”）再切回“热门”；
- 支持自动翻页到指定页，并等待卡片按累计模式增长；
- 支持按“页内索引”换算累计列表中的绝对索引来点击项目卡片；
- 点击卡片后自动监听项目详情接口并保存响应；
- 原样保存接口响应对象到本地 JSON。

可选环境变量：
- DP_BROWSER_PATH: 指定浏览器可执行文件路径
- DP_USER_DATA_PATH: 指定 Chromium user data 目录，默认使用仓库内持久目录
- DP_USE_SYSTEM_USER_PATH: 是否复用系统 Chromium 用户目录，默认 0
- DP_USER: Chromium profile 名称，默认 Default
- DP_LOCAL_PORT: 指定本地调试端口；使用持久 user data 时默认 9333
- DP_HEADLESS: 是否无头，默认 0
- PROJECTLIB_TARGET_TAB: 目标 Tab 文案，默认 “热门”
- PROJECTLIB_FALLBACK_TAB: 备用 Tab 文案，默认 “最新”
- PROJECTLIB_CARD_INDEX: 需要点击的页内卡片索引（1-based，默认不点击）
- PROJECTLIB_PAGE_INDEX: 当前已翻到的页码（1-based，默认 1）
- PROJECTLIB_PAGE_SIZE: 每页卡片数，默认 20
- PROJECTLIB_DETAIL_TIMEOUT: 卡片详情接口监听超时秒数，默认 20
"""

import json
import os
import random
import re
import time
from datetime import datetime

from DrissionPage import ChromiumOptions, ChromiumPage


OUTPUT_DIR = os.path.expanduser("~/.hermes/skills/opportunity-radar/sources/shengcai/data")
DEFAULT_USER_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "browser_user_data"))
BASE_URL = "https://scys.com/"
CLIENT_API_PREFIX = "https://scys.com/shengcai-web/client/"
PROJECTLIB_API_PREFIX = "https://scys.com/shengcai-web/client/projectLib/"
PROJECTLIB_API_URL = "https://scys.com/shengcai-web/client/projectLib/list"
TARGET_TAB_TEXT = os.getenv("PROJECTLIB_TARGET_TAB", "热门")
FALLBACK_TAB_TEXT = os.getenv("PROJECTLIB_FALLBACK_TAB", "最新")


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


def slugify(text, default="item"):
    value = str(text or "").strip()
    if not value:
        return default
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or default


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


def wait_for_url_change(page, old_url, timeout=15, interval=0.3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            current_url = page.url or ""
        except Exception:
            current_url = ""
        if current_url and current_url != (old_url or ""):
            return current_url
        time.sleep(interval)
    return ""


def get_page_url(page):
    try:
        return page.url or ""
    except Exception:
        return ""


def get_tab_ids(page):
    try:
        return list(page.tab_ids or [])
    except Exception:
        return []


def get_tab_by_id(page, tab_id):
    if not tab_id:
        return None

    try:
        return page.get_tab(tab_id)
    except Exception:
        return None


def get_latest_tab(page, exclude_tab_ids=None):
    exclude_set = set(exclude_tab_ids or [])

    try:
        tab = page.latest_tab
    except Exception:
        return None

    try:
        tab_id = tab.tab_id
    except Exception:
        tab_id = ""

    if tab and tab_id not in exclude_set:
        return tab
    return None


def wait_for_new_tab(page, before_tab_ids=None, timeout=10, interval=0.2):
    before_ids = list(before_tab_ids or [])
    before_set = set(before_ids)
    deadline = time.time() + timeout

    while time.time() < deadline:
        current_ids = get_tab_ids(page)
        new_ids = [tab_id for tab_id in current_ids if tab_id not in before_set]
        if new_ids:
            for tab_id in new_ids:
                tab = get_tab_by_id(page, tab_id)
                if tab:
                    return tab, new_ids

        if current_ids and len(current_ids) > len(before_ids):
            latest_tab = get_latest_tab(page, exclude_tab_ids=before_ids)
            if latest_tab:
                return latest_tab, [latest_tab.tab_id]

        time.sleep(interval)

    latest_tab = get_latest_tab(page, exclude_tab_ids=before_ids)
    if latest_tab:
        return latest_tab, [latest_tab.tab_id]

    return None, []


def wait_for_usable_url(page, previous_url="", timeout=10, interval=0.3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        current_url = get_page_url(page)
        if current_url and current_url != "about:blank":
            if not previous_url or current_url != previous_url:
                return current_url
        time.sleep(interval)

    current_url = get_page_url(page)
    if current_url and current_url != "about:blank":
        return current_url
    return ""


def wait_for_projectlib_ready(page, timeout=20):
    return wait_until(
        page,
        """
        const wantedTexts = ['项目库', '热门', '最新'];
        const nodes = Array.from(document.querySelectorAll('body *'));
        return nodes.some(el => {
            const txt = (el.textContent || '').trim();
            if (!txt) return false;
            const rect = el.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return false;
            return wantedTexts.includes(txt);
        });
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


def click_tab(page, text):
    script = """
    const targetText = arguments[0];
    const nodes = Array.from(document.querySelectorAll('body *'));

    function isVisible(el) {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
    }

    function score(el) {
        const role = el.getAttribute('role') || '';
        const className = String(el.className || '');
        const ariaSelected = el.getAttribute('aria-selected') || '';
        let value = 0;
        if (role === 'tab') value += 10;
        if (ariaSelected) value += 3;
        if (/tab|button|item/i.test(className)) value += 2;
        if (el.tagName === 'BUTTON') value += 2;
        return value;
    }

    let best = null;
    let bestScore = -1;
    for (const el of nodes) {
        const txt = (el.textContent || '').trim();
        if (txt !== targetText || !isVisible(el)) continue;

        let candidate = el;
        while (candidate && candidate !== document.body) {
            if (isVisible(candidate)) {
                const currentScore = score(candidate);
                if (currentScore > bestScore) {
                    best = candidate;
                    bestScore = currentScore;
                }
            }
            candidate = candidate.parentElement;
        }
    }

    if (!best) return false;
    best.click();
    return true;
    """
    return bool(page.run_js(script, text))


def get_project_cards(page):
    try:
        return page.eles("xpath://div[@class='project-grid']/div")
    except Exception:
        return []


def get_project_card_count(page):
    return len(get_project_cards(page))


def resolve_card_absolute_index(card_index, page_index, page_size):
    if card_index < 1:
        raise ValueError("卡片索引必须 >= 1")
    if page_index < 1:
        raise ValueError("页码必须 >= 1")
    if page_size < 1:
        raise ValueError("每页数量必须 >= 1")
    return (page_index - 1) * page_size + card_index


def required_card_count(page_index, page_size):
    return page_index * page_size


def wait_card_count(page, minimum_count, timeout=15, interval=0.3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        current_count = get_project_card_count(page)
        if current_count >= minimum_count:
            return True
        time.sleep(interval)
    return False


def get_active_page_num(page):
    try:
        result = page.run_js(
            """
            const selectors = [
                '.arco-pagination-item-active',
                '.ant-pagination-item-active',
                '[aria-current="page"]'
            ];
            for (const selector of selectors) {
                const active = document.querySelector(selector);
                if (!active) continue;
                const txt = (active.textContent || '').trim();
                if (/^\d+$/.test(txt)) return Number(txt);
            }
            return 0;
            """
        )
        return int(result or 0)
    except Exception:
        return 0


def wait_active_page(page, page_num, timeout=10):
    return wait_until(
        page,
        f"""
        const target = {int(page_num)};
        const selectors = [
            '.arco-pagination-item-active',
            '.ant-pagination-item-active',
            '[aria-current="page"]'
        ];
        for (const selector of selectors) {{
            const active = document.querySelector(selector);
            if (!active) continue;
            const txt = (active.textContent || '').trim();
            if (/^\\d+$/.test(txt) && Number(txt) === target) return true;
        }}
        return false;
        """,
        timeout=timeout,
    )


def click_next_page(page):
    script = """
    const candidates = [
        'ul.arco-pagination-list > span:last-of-type',
        '.arco-pagination-next',
        '.ant-pagination-next',
        '[aria-label*="next" i]',
        '[aria-label*="下一" i]'
    ];

    function isDisabled(el) {
        if (!el) return true;
        const className = String(el.className || '');
        return el.disabled ||
            el.getAttribute('aria-disabled') === 'true' ||
            /disabled/i.test(className);
    }

    for (const selector of candidates) {
        const el = document.querySelector(selector);
        if (!el || isDisabled(el)) continue;
        el.click();
        return true;
    }

    const spans = document.querySelectorAll('ul.arco-pagination-list > span');
    if (spans.length >= 2 && !isDisabled(spans[1])) {
        spans[1].click();
        return true;
    }

    return false;
    """
    return bool(page.run_js(script))


def trigger_projectlib_request(page, trigger_action, action_name, timeout=20):
    page.listen.start(PROJECTLIB_API_URL, method="POST")
    try:
        human_pause(0.2, 0.6)
        if trigger_action() is False:
            raise RuntimeError(f"{action_name} 触发失败")

        packet = page.listen.wait(timeout=timeout)
        if not packet:
            raise RuntimeError(f"{action_name} 未监听到 projectLib/list 请求")

        payload = packet_to_payload(packet)
        items = payload.get("data", {}).get("items", [])
        print(f"[INFO] {action_name} 监听成功，返回 {len(items)} 条")
        return payload
    finally:
        page.listen.stop()


def ensure_page_loaded(page, target_page_index, page_size=20):
    if target_page_index <= 1:
        wait_card_count(page, required_card_count(1, page_size), timeout=12)
        return None

    current_page = get_active_page_num(page) or 1
    target_count = required_card_count(target_page_index, page_size)
    last_payload = None

    if current_page >= target_page_index and get_project_card_count(page) >= target_count:
        return None

    print(f"[STEP] 准备翻到第 {target_page_index} 页")

    while current_page < target_page_index:
        next_page = current_page + 1
        last_payload = trigger_projectlib_request(page, lambda: click_next_page(page), f"翻到第 {next_page} 页")

        if not wait_active_page(page, next_page, timeout=10):
            print(f"[WARN] 未确认分页高亮切到第 {next_page} 页，继续等待卡片数量")

        expected_count = required_card_count(next_page, page_size)
        if not wait_card_count(page, expected_count, timeout=15):
            raise RuntimeError(
                f"翻到第 {next_page} 页后卡片数量不足："
                f"期望至少 {expected_count} 个，实际 {get_project_card_count(page)} 个"
            )

        current_page = max(get_active_page_num(page), next_page)
        print(f"[INFO] 当前已到第 {current_page} 页，累计 {get_project_card_count(page)} 个卡片")
        human_pause(0.8, 1.5)

    return last_payload


def click_card_by_index(page, card_index, page_index=1, page_size=20, timeout=10):
    absolute_index = resolve_card_absolute_index(card_index, page_index, page_size)
    deadline = time.time() + timeout

    while time.time() < deadline:
        cards = get_project_cards(page)
        if len(cards) >= absolute_index:
            card = cards[absolute_index - 1]
            try:
                card.click()
            except Exception:
                card.click.left(by_js=True)
            print(
                f"[INFO] 已点击第 {page_index} 页第 {card_index} 个卡片"
                f"（累计列表第 {absolute_index} 个，当前共 {len(cards)} 个）"
            )
            return card
        time.sleep(0.3)

    raise RuntimeError(
        f"卡片数量不足：需要累计列表第 {absolute_index} 个，"
        f"当前最多只有 {len(get_project_cards(page))} 个"
    )


def get_active_tab_text(page):
    try:
        result = page.run_js(
            """
            const selectors = [
                '.arco-tabs-tab-active',
                '.ant-tabs-tab-active',
                '[role="tab"][aria-selected="true"]',
                '.tab-active'
            ];
            for (const selector of selectors) {
                const active = document.querySelector(selector);
                if (active) {
                    const txt = (active.textContent || '').trim();
                    if (txt) return txt;
                }
            }
            return '';
            """
        )
        return str(result or "").strip()
    except Exception:
        return ""


def wait_active_tab(page, text, timeout=8):
    safe_text = json.dumps(text, ensure_ascii=False)
    return wait_until(
        page,
        f"""
        const targetText = {safe_text};
        const selectors = [
            '.arco-tabs-tab-active',
            '.ant-tabs-tab-active',
            '[role="tab"][aria-selected="true"]',
            '.tab-active'
        ];
        for (const selector of selectors) {{
            const active = document.querySelector(selector);
            if (!active) continue;
            const txt = (active.textContent || '').trim();
            if (txt === targetText) return true;
        }}
        return false;
        """,
        timeout=timeout,
    )


def navigate_to_projectlib(page):
    print("[STEP] 首页悬浮“项目”并点击“项目库”")
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

    projectlib_menu = find_text_element(page, "项目库", timeout=10)
    clicked = False

    if projectlib_menu:
        try:
            projectlib_menu.click()
            clicked = True
        except Exception:
            try:
                projectlib_menu.click.left(by_js=True)
                clicked = True
            except Exception:
                clicked = False

    if not clicked:
        clicked = click_visible_text(page, "项目库", exact=True)

    if not clicked:
        clicked = click_visible_text(page, "项目库", exact=False)

    if not clicked:
        raise RuntimeError("悬浮后未找到可点击的“项目库”二级菜单")

    wait_for_url_contains(page, "project", timeout=15)
    human_pause(2.0, 3.5)

    if not wait_for_projectlib_ready(page, timeout=20):
        raise RuntimeError("项目库页面未加载出可操作 Tab")

    print("[INFO] 已通过首页菜单进入项目库页面")
    return True


def ensure_target_tab_can_trigger(page, target_text, fallback_text):
    active_text = get_active_tab_text(page)
    if active_text != target_text:
        return

    if not fallback_text or fallback_text == target_text:
        print(f"[INFO] “{target_text}”已是激活态，将直接尝试点击触发请求")
        return

    print(f"[INFO] “{target_text}”已是激活态，先切到“{fallback_text}”再切回")
    if not click_tab(page, fallback_text):
        print(f"[WARN] 未找到备用 Tab “{fallback_text}”，继续直接点击“{target_text}”")
        return

    wait_active_tab(page, fallback_text, timeout=8)
    human_pause(1.0, 2.0)


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


def try_packet_to_payload(packet):
    try:
        return packet_to_payload(packet)
    except Exception:
        return None


def get_packet_url(packet):
    values = []

    for attr in ("url", "target"):
        try:
            value = getattr(packet, attr, None)
        except Exception:
            value = None
        if value:
            values.append(value)

    for obj_name in ("request", "response"):
        try:
            obj = getattr(packet, obj_name, None)
        except Exception:
            obj = None
        if not obj:
            continue

        for attr in ("url", "target"):
            try:
                value = getattr(obj, attr, None)
            except Exception:
                value = None
            if value:
                values.append(value)

    for value in values:
        if value:
            return str(value)

    return ""


def is_projectlib_detail_url(url):
    return bool(url) and PROJECTLIB_API_PREFIX in url and not url.rstrip("/").endswith("/list")


def get_page_item(page_payload, card_index):
    items = (page_payload or {}).get("data", {}).get("items", [])
    if 1 <= card_index <= len(items):
        return items[card_index - 1]
    return {}


def payload_contains_value(payload, target_value, depth=0, max_depth=6):
    if depth > max_depth or target_value in (None, ""):
        return False

    if isinstance(payload, dict):
        for value in payload.values():
            if payload_contains_value(value, target_value, depth + 1, max_depth=max_depth):
                return True
        return False

    if isinstance(payload, list):
        for item in payload:
            if payload_contains_value(item, target_value, depth + 1, max_depth=max_depth):
                return True
        return False

    return payload == target_value


def score_detail_candidate(url, payload, target_id=None):
    url = str(url or "")
    score = 0

    if CLIENT_API_PREFIX in url:
        score += 10
    if PROJECTLIB_API_PREFIX in url:
        score += 30
    if "project" in url.lower():
        score += 20
    if is_projectlib_detail_url(url):
        score += 50
    elif "detail" in url.lower() or "info" in url.lower():
        score += 30
    if url.rstrip("/").endswith("/list"):
        score -= 30
    else:
        score += 10

    if target_id not in (None, "") and payload_contains_value(payload, target_id):
        score += 100

    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        for key in ("id", "name", "summary", "resourceCount", "caseCount"):
            if key in data:
                score += 5

    return score


def collect_best_client_response(page, target_id=None, timeout=20, url_prefix=CLIENT_API_PREFIX, exclude_list=False):
    best_payload = None
    best_url = ""
    best_score = -1
    idle_deadline = None
    deadline = time.time() + timeout

    while time.time() < deadline:
        remaining = max(deadline - time.time(), 0.5)
        packet = page.listen.wait(timeout=min(2, remaining))
        if not packet:
            if best_payload is not None and idle_deadline and time.time() >= idle_deadline:
                break
            continue

        packet_url = get_packet_url(packet)
        payload = try_packet_to_payload(packet)
        if payload is None or url_prefix not in packet_url:
            continue
        if exclude_list and packet_url.rstrip("/").endswith("/list"):
            continue

        candidate_score = score_detail_candidate(packet_url, payload, target_id=target_id)
        if candidate_score > best_score:
            best_payload = payload
            best_url = packet_url
            best_score = candidate_score

        idle_deadline = min(deadline, time.time() + 1.5)

        if target_id not in (None, "") and candidate_score >= 120:
            break

    return best_payload, best_url, best_score


def collect_detail_response_from_tab(tab, target_id=None, timeout=20, action=None, action_name="详情页"):
    tab_id = getattr(tab, "tab_id", "")
    page_url = get_page_url(tab)
    print(f"[INFO] {action_name}监听开始，tab_id={tab_id}，page_url={page_url or 'N/A'}")

    tab.listen.start(PROJECTLIB_API_PREFIX)
    try:
        if action is not None:
            human_pause(0.2, 0.5)
            action()
        best_payload, best_url, best_score = collect_best_client_response(
            tab,
            target_id=target_id,
            timeout=timeout,
            url_prefix=PROJECTLIB_API_PREFIX,
            exclude_list=True,
        )
    finally:
        tab.listen.stop()

    return best_payload, best_url, best_score


def capture_projectlib(page, target_tab_text):
    return trigger_projectlib_request(
        page,
        lambda: click_tab(page, target_tab_text),
        f"点击“{target_tab_text}”",
    )


def tab_slug(text):
    mapping = {
        "热门": "hot",
        "最新": "latest",
    }
    return mapping.get(text, text.strip().replace(" ", "_") or "tab")


def save_payload(payload, tab_text):
    today = datetime.now().strftime("%Y%m%d")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tab_name = tab_slug(tab_text)
    filename = f"projectlib_{today}_{timestamp}_{tab_name}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    print(f"[SAVED] {filepath}")

    latest_path = os.path.join(OUTPUT_DIR, "projectlib_latest.json")
    with open(latest_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    items = payload.get("data", {}).get("items", [])
    print(f"[FINAL] projectlib_latest.json ({len(items)} 条)")
    return filepath


def save_detail_payload(payload, detail_url, page_item):
    today = datetime.now().strftime("%Y%m%d")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    item_id = page_item.get("id", "unknown")
    item_name = slugify(page_item.get("name"), default="card")
    filename = f"projectlib_detail_{item_id}_{today}_{timestamp}_{item_name}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    latest_path = os.path.join(OUTPUT_DIR, f"projectlib_detail_{item_id}_latest.json")
    with open(latest_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    print(f"[SAVED] {filepath}")
    print(f"[FINAL] projectlib_detail_{item_id}_latest.json")
    if detail_url:
        print(f"[INFO] 详情接口: {detail_url}")
    return filepath


def capture_project_detail_after_click(
    page,
    card_index,
    page_index=1,
    page_size=20,
    page_payload=None,
    timeout=20,
):
    action_name = f"点击第 {page_index} 页第 {card_index} 个卡片"
    page_item = get_page_item(page_payload, card_index)
    target_id = page_item.get("id")
    before_url = get_page_url(page)
    before_tab_ids = get_tab_ids(page)
    before_tab_id = getattr(page, "tab_id", "")
    same_tab_timeout = max(1.5, min(timeout, 4))

    print(
        f"[INFO] {action_name} 前标签页状态："
        f"tab_count={len(before_tab_ids)}，current_tab_id={before_tab_id}，tabs={before_tab_ids}"
    )

    page.listen.start(PROJECTLIB_API_PREFIX)
    try:
        human_pause(0.2, 0.6)
        click_card_by_index(page, card_index, page_index=page_index, page_size=page_size)
        best_payload, best_url, best_score = collect_best_client_response(
            page,
            target_id=target_id,
            timeout=same_tab_timeout,
            url_prefix=PROJECTLIB_API_PREFIX,
            exclude_list=True,
        )
    finally:
        page.listen.stop()

    if best_payload is not None:
        print(f"[INFO] {action_name} 后在当前标签页命中详情候选响应，tab_id={before_tab_id}，score={best_score}")
        return best_payload, best_url, page_item

    detail_tab, new_tab_ids = wait_for_new_tab(page, before_tab_ids=before_tab_ids, timeout=min(8, timeout))
    if detail_tab is not None:
        detail_tab_id = getattr(detail_tab, "tab_id", "")
        detail_page_url = wait_for_usable_url(detail_tab, timeout=10)
        print(
            f"[INFO] 检测到详情新标签页：new_tab_ids={new_tab_ids}，"
            f"listen_tab_id={detail_tab_id}，page_url={detail_page_url or 'N/A'}"
        )

        best_payload, best_url, best_score = collect_detail_response_from_tab(
            detail_tab,
            target_id=target_id,
            timeout=max(2, timeout // 2),
            action_name="详情新标签页",
        )
        if best_payload is not None:
            print(f"[INFO] 已在详情新标签页选中候选响应，tab_id={detail_tab_id}，score={best_score}")
            return best_payload, best_url, page_item

        if detail_page_url:
            print(f"[WARN] 详情新标签页首轮未抓到接口，执行刷新兜底：tab_id={detail_tab_id}，url={detail_page_url}")
            best_payload, best_url, best_score = collect_detail_response_from_tab(
                detail_tab,
                target_id=target_id,
                timeout=timeout,
                action=lambda: detail_tab.refresh(ignore_cache=True),
                action_name="详情新标签页刷新",
            )

            if best_payload is not None:
                print(f"[INFO] 详情新标签页刷新后已选中候选响应，tab_id={detail_tab_id}，score={best_score}")
                return best_payload, best_url, page_item

    detail_url = wait_for_url_change(page, before_url, timeout=6)
    if detail_url:
        print(f"[WARN] 当前标签页发生跳转但未抓到详情接口，执行当前页刷新兜底：tab_id={before_tab_id}，url={detail_url}")
        best_payload, best_url, best_score = collect_detail_response_from_tab(
            page,
            target_id=target_id,
            timeout=timeout,
            action=lambda: page.refresh(ignore_cache=True),
            action_name="当前标签页详情刷新",
        )

        if best_payload is not None:
            print(f"[INFO] 当前标签页刷新后已选中详情候选响应，tab_id={before_tab_id}，score={best_score}")
            return best_payload, best_url, page_item

    raise RuntimeError(
        f"{action_name} 后未监听到项目详情接口响应，"
        f"before_tab_id={before_tab_id}，before_tabs={before_tab_ids}，new_tab_ids={new_tab_ids}"
    )


def main():
    print("=" * 50)
    print(f"[START] 项目库采集 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    ensure_dirs()
    page = None
    target_card_index = env_int("PROJECTLIB_CARD_INDEX", 0)
    target_page_index = env_int("PROJECTLIB_PAGE_INDEX", 1)
    target_page_size = env_int("PROJECTLIB_PAGE_SIZE", 20)
    detail_timeout = env_int("PROJECTLIB_DETAIL_TIMEOUT", 20)

    try:
        page = create_page()

        if not navigate_to_projectlib(page):
            print("[EXIT] 未能进入项目库页面，退出")
            return

        ensure_target_tab_can_trigger(page, TARGET_TAB_TEXT, FALLBACK_TAB_TEXT)
        payload = capture_projectlib(page, TARGET_TAB_TEXT)
        save_payload(payload, TARGET_TAB_TEXT)

        if target_card_index > 0:
            human_pause(1.0, 1.8)
            page_payload = ensure_page_loaded(page, target_page_index, page_size=target_page_size) or payload
            detail_payload, detail_url, page_item = capture_project_detail_after_click(
                page,
                target_card_index,
                page_index=target_page_index,
                page_size=target_page_size,
                page_payload=page_payload,
                timeout=detail_timeout,
            )
            save_detail_payload(detail_payload, detail_url, page_item)

        print("\n[DONE] 项目库采集完成")

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
