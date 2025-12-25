# -*- coding: utf-8 -*-
import os
import time
import random
import datetime
import logging
from pathlib import Path
from typing import List, Dict
from urllib.parse import quote

import pandas as pd
from playwright.sync_api import (
    sync_playwright,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

# -------------------------
# Logging
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("zhihu")

# -------------------------
# Paths (repo-root stable)
# scripts/zhihu.py -> repo root = parents[1]
# -------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent

DATA_DIR = ROOT_DIR / "data"
DEBUG_DIR = ROOT_DIR / "debug"

DATA_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# 登录态：优先用 repo root 的 storage_state.json；若不存在再用 scripts/storage_state.json
STATE_ROOT = ROOT_DIR / "storage_state.json"
STATE_SCRIPTS = SCRIPT_DIR / "storage_state.json"

MAIN_DATA_FILE = DATA_DIR / "zhihu_data.csv"

# -------------------------
# Config via env
# -------------------------
KEYWORDS = os.getenv("KEYWORDS", "王飞跃,自动化学会").replace("，", ",").split(",")
MAX_RESULTS = int(os.getenv("MAX_RESULTS_PER_KEYWORD", "30"))
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

# Playwright timeouts / retries
GOTO_TIMEOUT_MS = int(os.getenv("GOTO_TIMEOUT_MS", "180000"))  # 3分钟
GOTO_RETRIES = int(os.getenv("GOTO_RETRIES", "3"))


# -------------------------
# Helpers
# -------------------------
def safe_name(s: str, max_len: int = 20) -> str:
    s2 = "".join([c for c in s if c.isalnum()])[:max_len]
    return s2 or "kw"


def save_debug(page: Page, prefix: str, reason: str = ""):
    """保存截图 + HTML，方便定位是否风控/验证码/未登录/DOM变动"""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{prefix}_{ts}"
    png_path = DEBUG_DIR / f"{base}.png"
    html_path = DEBUG_DIR / f"{base}.html"

    try:
        page.screenshot(path=str(png_path), full_page=True)
    except Exception as e:
        logger.warning(f"[DEBUG] screenshot failed: {e}")

    try:
        html = page.content()
        html_path.write_text(html, encoding="utf-8")
    except Exception as e:
        logger.warning(f"[DEBUG] save html failed: {e}")

    logger.warning(f"[DEBUG] Saved debug files: {png_path.name}, {html_path.name}. {reason}")


def looks_like_verification_or_login(page: Page) -> bool:
    """粗略判断：是否遇到登录页/安全验证/验证码/异常访问"""
    try:
        title = (page.title() or "").strip()
    except Exception:
        title = ""

    try:
        html = page.content()
    except Exception:
        html = ""

    red_flags = [
        "安全验证",
        "验证码",
        "验证",
        "异常访问",
        "风险",
        "robot",
        "SignFlow",
        "登录",
        "signin",
    ]
    text = f"{title}\n{html}"
    return any(flag in text for flag in red_flags)


def human_scroll(page: Page, times: int = None):
    if times is None:
        times = random.randint(3, 6)
    for _ in range(times):
        page.mouse.wheel(0, random.randint(500, 900))
        time.sleep(random.uniform(1.0, 2.5))


def load_storage_state_path() -> Path | None:
    if STATE_ROOT.exists():
        return STATE_ROOT
    if STATE_SCRIPTS.exists():
        return STATE_SCRIPTS
    return None


def goto_with_retry(page: Page, url: str, wait_until: str = "domcontentloaded", prefix: str = "goto") -> bool:
    """带重试的 goto。最终失败会保存 debug，但不抛异常"""
    for attempt in range(1, GOTO_RETRIES + 1):
        try:
            page.goto(url, wait_until=wait_until, timeout=GOTO_TIMEOUT_MS)
            return True
        except PlaywrightTimeoutError:
            logger.warning(f"[GOTO] Timeout (attempt {attempt}/{GOTO_RETRIES}): {url}")
            if attempt == GOTO_RETRIES:
                save_debug(page, f"{prefix}_timeout", reason=f"Final timeout for {url}")
                return False
            time.sleep(5 * attempt)
        except Exception as e:
            logger.warning(f"[GOTO] Error (attempt {attempt}/{GOTO_RETRIES}): {url} err={e}")
            if attempt == GOTO_RETRIES:
                save_debug(page, f"{prefix}_error", reason=f"Final error for {url}: {e}")
                return False
            time.sleep(3 * attempt)
    return False


# -------------------------
# Scrape
# -------------------------
def scrape_zhihu_keyword(page: Page, keyword: str) -> List[Dict]:
    results: List[Dict] = []
    kw = keyword.strip()
    if not kw:
        return results

    prefix = safe_name(kw)
    logger.info(f"开始抓取关键词：{kw}")

    search_url = f"https://www.zhihu.com/search?type=content&q={quote(kw)}"
    ok = goto_with_retry(page, search_url, wait_until="domcontentloaded", prefix=f"{prefix}_search")
    if not ok:
        logger.warning("搜索页无法打开（超时/错误），跳过该关键词。")
        return []

    time.sleep(2.0)
    logger.info(f"[DEBUG] search.title={page.title()!r}")
    logger.info(f"[DEBUG] search.url={page.url!r}")

    # 保存打开后的页面（用于判断风控/验证/结构变化）
    save_debug(page, f"{prefix}_open", reason="After opening search page")

    # 若明显是验证/登录页，直接返回空（debug 已保存）
    if looks_like_verification_or_login(page):
        logger.warning("疑似遇到风控/验证码/未登录页面（见 debug/ 截图与HTML）")
        return []

    # 等待结果 DOM
    try:
        page.wait_for_selector(".ContentItem, .SearchResult-Card, .List-item", timeout=15000)
    except Exception:
        logger.warning("未检测到搜索结果 DOM（可能DOM变动/被限流），已保存 debug。")
        save_debug(page, f"{prefix}_noresult", reason="No result DOM found")
        return []

    time.sleep(random.uniform(2, 4))
    human_scroll(page, times=4)

    cards = page.query_selector_all(".ContentItem, .SearchResult-Card, .List-item")
    logger.info(f"关键词「{kw}」抓到 {len(cards)} 个卡片")

    if not cards:
        save_debug(page, f"{prefix}_emptycards", reason="Selector matched but no cards")
        return []

    for card in cards[:MAX_RESULTS]:
        try:
            title_el = card.query_selector("a[href*='/question/'], a[href*='/p/'], a[href]")
            if not title_el:
                continue

            title = (title_el.inner_text() or "").strip()
            url = title_el.get_attribute("href") or ""
            if not title or not url:
                continue

            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = "https://www.zhihu.com" + url

            author_el = card.query_selector(".AuthorInfo-name, .UserLink-link")
            author = (author_el.inner_text() or "").strip() if author_el else "未知"

            excerpt_el = card.query_selector(".RichContent-inner, .ContentItem-excerpt")
            excerpt = (excerpt_el.inner_text() or "").replace("\n", " ").strip() if excerpt_el else ""

            results.append(
                {
                    "keyword": kw,
                    "title": title,
                    "author": author,
                    "url": url,
                    "excerpt": excerpt[:200],
                    "scraped_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        except Exception:
            continue

    return results


# -------------------------
# Save (dedupe)
# -------------------------
def process_and_save_data(new_scraped_data: List[Dict]):
    if not new_scraped_data:
        logger.warning("本次未抓取到任何数据，跳过保存。")
        return

    new_df = pd.DataFrame(new_scraped_data)

    existing_urls = set()
    if MAIN_DATA_FILE.exists():
        try:
            existing_df = pd.read_csv(MAIN_DATA_FILE)
            if "url" in existing_df.columns:
                existing_urls = set(existing_df["url"].dropna().tolist())
        except Exception as e:
            logger.error(f"读取旧数据失败：{e}（将视为首次运行）")

    new_entries = new_df[~new_df["url"].isin(existing_urls)].drop_duplicates(subset=["url"])

    if new_entries.empty:
        logger.info("无新增内容（或全部重复）。")
        return

    write_header = not MAIN_DATA_FILE.exists()
    new_entries.to_csv(
        MAIN_DATA_FILE,
        mode="a",
        index=False,
        encoding="utf-8-sig",
        header=write_header,
    )
    logger.info(f"已更新总表：{MAIN_DATA_FILE}")

    current_time_str = datetime.datetime.now().strftime("%Y.%m.%d_%H%M%S")
    inc_file = DATA_DIR / f"{current_time_str}新增.csv"
    new_entries.to_csv(inc_file, index=False, encoding="utf-8-sig")
    logger.info(f"已生成增量：{inc_file}")


# -------------------------
# Main
# -------------------------
def main():
    all_data: List[Dict] = []

    storage_path = load_storage_state_path()
    if storage_path:
        logger.info(f"将使用登录态：{storage_path}")
    else:
        logger.warning("未找到 storage_state.json（可能导致未登录/受限）")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )

        context_kwargs = {
            "viewport": {"width": 1280, "height": 800},
            "locale": "zh-CN",
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/119.0.0.0 Safari/537.36"
            ),
        }
        if storage_path:
            context_kwargs["storage_state"] = str(storage_path)

        context = browser.new_context(**context_kwargs)

        # 反检测（不保证绕过风控，但能降低直接识别概率）
        context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            """
        )

        page = context.new_page()

        # 访问首页做一次诊断：超时不退出
        home_url = "https://www.zhihu.com"
        ok_home = goto_with_retry(page, home_url, wait_until="domcontentloaded", prefix="home")
        if ok_home:
            time.sleep(2)
            save_debug(page, "home_open", reason="Home page check")
            if looks_like_verification_or_login(page):
                logger.warning("首页疑似出现登录/验证/风控（见 debug/）。后续搜索很可能无数据。")
        else:
            logger.warning("知乎首页在 runner 上无法加载（超时/错误），仍尝试直接抓取搜索页。")

        # 逐关键词抓取
        for kw in KEYWORDS:
            kw = kw.strip()
            if not kw:
                continue
            data = scrape_zhihu_keyword(page, kw)
            all_data.extend(data)
            time.sleep(random.uniform(4, 8))

        browser.close()

    process_and_save_data(all_data)
    logger.info(f"本次抓取完成，条目数：{len(all_data)}")
    logger.info("如无数据，请下载 artifacts 中的 debug/ 查看返回页面是否为安全验证/登录页。")


if __name__ == "__main__":
    main()
