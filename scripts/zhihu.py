# -*- coding: utf-8 -*-
import os
import time
import random
import datetime
import logging
from typing import List, Dict
from urllib.parse import quote

import pandas as pd
from playwright.sync_api import sync_playwright, Page

# =========================
# 日志配置
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# =========================
# 配置区
# =========================
KEYWORDS = os.getenv("KEYWORDS", "王飞跃,自动化学会").replace("，", ",").split(",")
MAX_RESULTS = int(os.getenv("MAX_RESULTS_PER_KEYWORD", "30"))
DATA_DIR = "data"
STORAGE_STATE_PATH = "storage_state.json"
MAIN_DATA_FILE = os.path.join(DATA_DIR, "zhihu_data.csv")  # 定义主文件路径


# =========================
# 行为模拟
# =========================
def human_scroll(page: Page, times: int = None):
    """模拟真人滚动"""
    if times is None:
        times = random.randint(3, 6)

    for _ in range(times):
        page.mouse.wheel(0, random.randint(500, 900))
        time.sleep(random.uniform(1.0, 2.5))


# =========================
# 关键词抓取
# =========================
def scrape_zhihu_keyword(page: Page, keyword: str) -> List[Dict]:
    results = []
    logger.info(f"开始抓取关键词：{keyword}")

    search_url = f"https://www.zhihu.com/search?type=content&q={quote(keyword)}"
    page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

    try:
        page.wait_for_selector(
            ".ContentItem, .SearchResult-Card, .List-item",
            timeout=15000
        )
    except:
        logger.warning("未检测到搜索结果 DOM，可能被限流")
        return []

    time.sleep(random.uniform(2, 4))
    human_scroll(page, times=5)

    cards = page.query_selector_all(
        ".ContentItem, .SearchResult-Card, .List-item"
    )
    logger.info(f"关键词「{keyword}」抓到 {len(cards)} 个卡片")

    for card in cards[:MAX_RESULTS]:
        try:
            title_el = card.query_selector("a[href*='/question/'], a[href*='/p/']")
            if not title_el:
                continue

            title = title_el.inner_text().strip()
            url = title_el.get_attribute("href")
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = "https://www.zhihu.com" + url

            author_el = card.query_selector(".AuthorInfo-name, .UserLink-link")
            author = author_el.inner_text().strip() if author_el else "未知"

            excerpt_el = card.query_selector(".RichContent-inner, .ContentItem-excerpt")
            excerpt = (
                excerpt_el.inner_text().replace("\n", " ").strip()
                if excerpt_el else ""
            )

            results.append({
                "keyword": keyword,
                "title": title,
                "author": author,
                "url": url,
                "excerpt": excerpt[:200],
                "scraped_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        except Exception:
            continue

    return results


# =========================
# 数据处理与去重 (新增函数)
# =========================
def process_and_save_data(new_scraped_data: List[Dict]):
    """
    处理新抓取的数据：去重、更新总表、保存增量文件
    """
    if not new_scraped_data:
        logger.warning("本次未抓取到任何数据，跳过保存。")
        return

    # 1. 将新抓取的数据转换为 DataFrame
    new_df = pd.DataFrame(new_scraped_data)

    # 2. 读取已有数据以获取历史 URL 集合
    existing_urls = set()
    if os.path.exists(MAIN_DATA_FILE):
        try:
            existing_df = pd.read_csv(MAIN_DATA_FILE)
            if "url" in existing_df.columns:
                existing_urls = set(existing_df["url"].tolist())
        except Exception as e:
            logger.error(f"读取旧数据文件失败: {e}，将视为首次运行。")

    # 3. 筛选新增数据 (基于 URL 去重)
    # 逻辑：如果 URL 不在 existing_urls 中，且在本次抓取中不重复（drop_duplicates）
    new_entries = new_df[~new_df["url"].isin(existing_urls)].drop_duplicates(subset=["url"])

    if new_entries.empty:
        logger.info("本次抓取数据在历史记录中已存在，无新增内容。")
        return

    logger.info(f"发现 {len(new_entries)} 条新增数据！")

    # 4. 保存新增数据到总表 (Append 模式)
    write_header = not os.path.exists(MAIN_DATA_FILE)
    new_entries.to_csv(
        MAIN_DATA_FILE,
        mode="a",
        index=False,
        encoding="utf-8-sig",
        header=write_header,
    )
    logger.info(f"已追加更新总表: {MAIN_DATA_FILE}")

    # 5. 单独保存新增数据文件
    # 格式示例：2025.12.23_103005新增.csv (添加时分秒防止同一天多次运行覆盖)
    current_time_str = datetime.datetime.now().strftime("%Y.%m.%d_%H%M%S")
    new_filename = f"{current_time_str}新增.csv"
    new_file_path = os.path.join(DATA_DIR, new_filename)

    new_entries.to_csv(
        new_file_path,
        index=False,
        encoding="utf-8-sig"
    )
    logger.info(f"已生成增量文件: {new_file_path}")


# =========================
# 主入口
# =========================
def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    all_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,  # 调试建议 False
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
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

        if os.path.exists(STORAGE_STATE_PATH):
            logger.info("加载已有登录态 storage_state.json")
            context_kwargs["storage_state"] = STORAGE_STATE_PATH

        context = browser.new_context(**context_kwargs)

        # 注入反检测
        context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en'],
        });
        """)

        page = context.new_page()

        # 简单的登录检查（可选）
        page.goto("https://www.zhihu.com", wait_until="domcontentloaded")
        if "登录" in page.title() or page.query_selector(".SignFlow"):
            logger.warning("检测到未登录，搜索可能受限，建议手动生成 storage_state.json")

        for kw in KEYWORDS:
            kw = kw.strip()
            if not kw:
                continue

            data = scrape_zhihu_keyword(page, kw)
            all_data.extend(data)
            time.sleep(random.uniform(4, 8))

        browser.close()

    # 调用新的数据处理函数
    process_and_save_data(all_data)


if __name__ == "__main__":
    main()