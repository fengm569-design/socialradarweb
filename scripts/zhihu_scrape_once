# -*- coding: utf-8 -*-
"""
GitHub Actions 版：知乎关键词抓取（一次运行即退出）
- 不使用 CDP 接管（你原脚本 connect_over_cdp 在 Actions 上不可用）
- 不使用 schedule 常驻循环（Actions 用 cron 触发）
- 输出到 data/zhihu_data.json 与 data/zhihu_data.csv
- 支持用 storage_state.json 复用登录态（可选）
"""

import os
import json
import time
import random
import datetime
import logging
from typing import List, Dict

import pandas as pd
from playwright.sync_api import sync_playwright, Page


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# ---------------- 配置（可用环境变量覆盖） ----------------
def _get_keywords() -> List[str]:
    """
    支持两种写法：
    1) KEYWORDS='["王飞跃","自动化学会"]'   （JSON 数组）
    2) KEYWORDS='王飞跃,自动化学会'         （逗号分隔）
    """
    raw = os.getenv("KEYWORDS", "王飞跃,自动化学会").strip()
    if raw.startswith("["):
        try:
            arr = json.loads(raw)
            return [str(x).strip() for x in arr if str(x).strip()]
        except Exception:
            pass
    return [x.strip() for x in raw.split(",") if x.strip()]


KEYWORDS = _get_keywords()
MAX_RESULTS_PER_KEYWORD = int(os.getenv("MAX_RESULTS_PER_KEYWORD", "50"))
MAX_WAIT_TIME = int(os.getenv("MAX_WAIT_TIME", "5"))
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("1", "true", "yes", "y")

DATA_DIR = os.getenv("DATA_DIR", "data")
OUT_JSON = os.path.join(DATA_DIR, os.getenv("OUT_JSON", "zhihu_data.json"))
OUT_CSV = os.path.join(DATA_DIR, os.getenv("OUT_CSV", "zhihu_data.csv"))
OUT_META = os.path.join(DATA_DIR, os.getenv("OUT_META", "meta.json"))

STORAGE_STATE_PATH = os.getenv("STORAGE_STATE_PATH", "storage_state.json")  # 可选：存在则加载


# ---------------- 工具函数 ----------------
def human_delay(min_s=1.0, max_s=3.0):
    time.sleep(random.uniform(min_s, max_s))


def safe_text(element) -> str:
    if not element:
        return ""
    try:
        return element.inner_text().strip()
    except Exception:
        return ""


def merge_by_url(old_rows: List[Dict], new_rows: List[Dict]) -> List[Dict]:
    """按 url 去重合并：新数据优先覆盖旧数据"""
    m = {}
    for r in old_rows:
        url = (r.get("url") or "").strip()
        if url:
            m[url] = r
    for r in new_rows:
        url = (r.get("url") or "").strip()
        if url:
            m[url] = r
    # 按 scraped_at 逆序（尽量把最新的放前面）
    def _key(x):
        return x.get("scraped_at") or ""
    return sorted(m.values(), key=_key, reverse=True)


def save_outputs(rows: List[Dict]):
    os.makedirs(DATA_DIR, exist_ok=True)

    # 合并旧 JSON（如果有）
    old = []
    if os.path.exists(OUT_JSON):
        try:
            with open(OUT_JSON, "r", encoding="utf-8") as f:
                old = json.load(f) or []
        except Exception:
            old = []

    merged = merge_by_url(old, rows)

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    # CSV 也同步生成（覆盖写，更利于网页/分析）
    df = pd.DataFrame(merged)
    cols = ["keyword", "title", "excerpt", "author", "upvotes", "comments", "url", "scraped_at"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    meta = {
        "updated_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "count": len(merged),
        "keywords": KEYWORDS,
    }
    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    logger.info(f"写入：{OUT_JSON} / {OUT_CSV} / {OUT_META}（共 {len(merged)} 条）")


# ---------------- 抓取逻辑（基本沿用你原来的选择器与流程） ----------------
def scrape_zhihu_keyword(page: Page, keyword: str) -> List[Dict]:
    results = []
    seen_urls = set()

    logger.info(f"搜索关键词: {keyword}")

    # 你原脚本也是直接拼搜索 URL：https://www.zhihu.com/search?type=content&q=...
    search_url = f"https://www.zhihu.com/search?type=content&q={keyword}"
    page.goto(search_url, timeout=60000)
    page.wait_for_load_state("domcontentloaded")
    human_delay(2, 4)

    scroll_count = 0
    max_scrolls = 15

    while len(results) < MAX_RESULTS_PER_KEYWORD and scroll_count < max_scrolls:
        cards = page.query_selector_all(".SearchResult-Card, .Card")

        new_items = 0
        for card in cards:
            if len(results) >= MAX_RESULTS_PER_KEYWORD:
                break

            try:
                title_el = card.query_selector("h2.ContentItem-title a, .ContentItem-title span")
                if not title_el:
                    continue

                link_el = card.query_selector("h2.ContentItem-title a")
                url = ""
                if link_el:
                    url = link_el.get_attribute("href") or ""
                    if url and not url.startswith("http"):
                        url = "https:" + url

                if not url or url in seen_urls:
                    continue

                title = safe_text(title_el)
                seen_urls.add(url)

                excerpt_el = card.query_selector(".RichContent-inner, .ContentItem-excerpt")
                excerpt = safe_text(excerpt_el)

                author_el = card.query_selector(".UserLink-link, .AuthorInfo-name")
                author = safe_text(author_el)

                upvote_el = card.query_selector(".VoteButton--up")
                upvotes = safe_text(upvote_el)

                comment_el = card.query_selector("button.ContentItem-action:has-text('评论')")
                comments = safe_text(comment_el)

                item = {
                    "keyword": keyword,
                    "title": title,
                    "excerpt": excerpt,
                    "author": author,
                    "upvotes": upvotes,
                    "comments": comments,
                    "url": url,
                    "scraped_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                results.append(item)
                new_items += 1
            except Exception:
                continue

        logger.info(f"已收集 {len(results)} 条（滚动 {scroll_count + 1}/{max_scrolls}）")

        page.evaluate("window.scrollBy(0, document.body.scrollHeight * 0.6)")
        scroll_count += 1
        human_delay(2, MAX_WAIT_TIME)

        if new_items == 0 and scroll_count > 2:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            human_delay(3, 5)

    return results


def main():
    logger.info(f"KEYWORDS={KEYWORDS} | headless={HEADLESS} | max={MAX_RESULTS_PER_KEYWORD}")

    all_data = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        # 可选：复用登录态（如果仓库根目录存在 storage_state.json）
        if os.path.exists(STORAGE_STATE_PATH):
            logger.info("检测到 storage_state.json，尝试加载登录态。")
            context = browser.new_context(storage_state=STORAGE_STATE_PATH)
        else:
            context = browser.new_context()

        page = context.new_page()

        for kw in KEYWORDS:
            try:
                data = scrape_zhihu_keyword(page, kw)
                all_data.extend(data)
                logger.info(f"关键词 {kw} 完成，休息 5 秒")
                time.sleep(5)
            except Exception as e:
                logger.error(f"关键词 {kw} 抓取失败：{e}")

        page.close()
        context.close()
        browser.close()

    save_outputs(all_data)


if __name__ == "__main__":
    main()
