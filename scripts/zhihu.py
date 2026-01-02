# -*- coding: utf-8 -*-
import os
import time
import random
import datetime
import logging
import re
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
# 关键词设置，支持环境变量或默认值
KEYWORDS = os.getenv("KEYWORDS", "王飞跃,自动化学会,杨孟飞,陈虹,高会军,侯增广,孙彦广,辛景民,阳春华,袁利,张承慧,赵延龙,周杰,陈杰,戴琼海,桂卫华,郭雷,何友,蒋昌俊,李少远,钱锋").replace("，", ",").split(",")
MAX_RESULTS = int(os.getenv("MAX_RESULTS_PER_KEYWORD", "30"))
DATA_DIR = "data"
STORAGE_STATE_PATH = "storage_state.json"

OUT_CSV = os.path.join(DATA_DIR, "zhihu_data.csv")
NEW_CSV = os.path.join(DATA_DIR, "zhihu_data_new.csv")


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
# 工具函数
# =========================
def deduplicate_by_url(data: List[Dict]) -> List[Dict]:
    """根据URL去重"""
    seen = set()
    unique_data = []

    for item in data:
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        unique_data.append(item)

    return unique_data


def extract_publish_time(card) -> str:

    time_str = ""

    try:

        time_el = card.query_selector(".ContentItem-time")
        if time_el:
            text = time_el.inner_text().strip()
            if text:
                time_str = text


        if not time_str:
            tooltip_el = card.query_selector("span[data-tooltip]")
            if tooltip_el:
                tooltip = tooltip_el.get_attribute("data-tooltip")
                if tooltip:
                    time_str = tooltip


        if not time_str:
            action_el = card.query_selector(".ContentItem-action")
            if action_el:
                text = action_el.inner_text()

                match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
                if match:
                    time_str = match.group(1)

    except Exception as e:
        logger.debug(f"提取时间出错: {e}")


    if time_str:
        time_str = time_str.replace("发布于", "").replace("编辑于", "").strip()

    return time_str


# =========================
# 关键词抓取
# =========================
def scrape_zhihu_keyword(page: Page, keyword: str) -> List[Dict]:
    results = []
    logger.info(f"开始抓取关键词：{keyword}")

    # 构造搜索 URL
    search_url = f"https://www.zhihu.com/search?type=content&q={quote(keyword)}"
    page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

    try:
        # 等待内容加载
        page.wait_for_selector(
            ".ContentItem, .SearchResult-Card, .List-item",
            timeout=15000
        )
    except:
        logger.warning(f"关键词 {keyword} 未检测到搜索结果 DOM，可能无结果或被限流")
        return []

    # 模拟浏览行为
    time.sleep(random.uniform(2, 4))
    human_scroll(page, times=5)

    # 获取所有卡片
    cards = page.query_selector_all(
        ".ContentItem, .SearchResult-Card, .List-item"
    )
    logger.info(f"关键词「{keyword}」抓到 {len(cards)} 个卡片")

    for card in cards[:MAX_RESULTS]:
        try:
            # 1. 提取标题和链接
            title_el = card.query_selector("a[href*='/question/'], a[href*='/p/'], a[href*='/zvideo/']")
            if not title_el:
                # 有些是专栏或话题，结构不同，跳过
                continue

            title = title_el.inner_text().strip()
            url = title_el.get_attribute("href")

            # 补全 URL
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = "https://www.zhihu.com" + url

            # 2. 提取作者
            author_el = card.query_selector(".AuthorInfo-name, .UserLink-link")
            author = author_el.inner_text().strip() if author_el else "未知"

            # 3. 提取摘要
            excerpt_el = card.query_selector(".RichContent-inner, .ContentItem-excerpt")
            excerpt = (
                excerpt_el.inner_text().replace("\n", " ").strip()
                if excerpt_el else ""
            )

            # 4. 提取发布时间 (本次修改的核心)
            publish_time = extract_publish_time(card)

            results.append({
                "keyword": keyword,
                "title": title,
                "author": author,
                "url": url,
                "publish_time": publish_time,  # 新增字段
                "excerpt": excerpt[:200],  # 截取摘要前200字
                "scraped_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        except Exception as e:
            logger.debug(f"解析卡片失败：{e}")
            continue

    return results


# =========================
# 主入口
# =========================
def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    all_data = []

    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(
            headless=True,  # 如果需要看浏览器操作，改为 False
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

        # 如果有登录状态文件，加载它
        if os.path.exists(STORAGE_STATE_PATH):
            logger.info("加载已有登录态 storage_state.json")
            context_kwargs["storage_state"] = STORAGE_STATE_PATH

        context = browser.new_context(**context_kwargs)

        # 注入反爬虫绕过脚本
        context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN','zh','en'] });
        """)

        page = context.new_page()

        for kw in KEYWORDS:
            kw = kw.strip()
            if not kw:
                continue

            data = scrape_zhihu_keyword(page, kw)
            all_data.extend(data)
            # 关键词之间随机等待，防止触发风控
            time.sleep(random.uniform(4, 8))

        browser.close()

    if not all_data:
        logger.warning("本次未抓取到任何数据")
        return

    # 本次运行内部去重
    all_data = deduplicate_by_url(all_data)
    df_new = pd.DataFrame(all_data)

    # 打印预览
    print("\n抓取结果预览:")
    print(df_new[['title', 'publish_time', 'author']].head())

    # 与历史数据对比 (增量更新)
    if os.path.exists(OUT_CSV):
        try:
            df_old = pd.read_csv(OUT_CSV, encoding="utf-8-sig")
            old_urls = set(df_old["url"].dropna().tolist())
            df_increment = df_new[~df_new["url"].isin(old_urls)]
        except Exception as e:
            logger.error(f"读取旧数据失败，将全量保存: {e}")
            df_increment = df_new
    else:
        df_increment = df_new

    # 保存新增数据
    if not df_increment.empty:
        # 保存本次新增的
        df_increment.to_csv(
            NEW_CSV,
            index=False,
            encoding="utf-8-sig",
        )
        logger.info(f"新增 {len(df_increment)} 条数据 → {NEW_CSV}")

        # 追加写入总表
        df_increment.to_csv(
            OUT_CSV,
            mode="a",
            index=False,
            encoding="utf-8-sig",
            header=not os.path.exists(OUT_CSV),
        )
        logger.info(f"已追加到总表 → {OUT_CSV}")
    else:
        logger.info("没有发现新增数据")


if __name__ == "__main__":
    main()
