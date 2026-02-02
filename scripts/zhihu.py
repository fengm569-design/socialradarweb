# -*- coding: utf-8 -*-
import os
import time
import random
import datetime
import logging
import re
from pathlib import Path
from typing import List, Dict
from urllib.parse import quote

import pandas as pd
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError


# =========================
# 日志配置
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =========================
# 配置区（支持环境变量覆盖）
# =========================
KEYWORDS = (
    os.getenv(
        "KEYWORDS",
        "自动化学会,王飞跃,杨孟飞,郑南宁,张楠,高会军,侯增广,孙彦广,辛景民,阳春华,袁利,张承慧,赵延龙,周杰,陈杰,戴琼海,桂卫华,郭雷,何友,蒋昌俊,李少远,钱锋",
    )
    .replace("，", ",")
    .split(",")
)

MAX_RESULTS = int(os.getenv("MAX_RESULTS_PER_KEYWORD", "30"))
DATA_DIR = os.getenv("DATA_DIR", "data")
DEBUG_DIR = os.getenv("DEBUG_DIR", "debug")

STORAGE_STATE_PATH = os.getenv("STORAGE_STATE_PATH", "storage_state.json")

HEADLESS = os.getenv("HEADLESS", "true").strip().lower() not in ("0", "false", "no")
GOTO_TIMEOUT_MS = int(os.getenv("GOTO_TIMEOUT_MS", "60000"))
GOTO_RETRIES = int(os.getenv("GOTO_RETRIES", "2"))

OUT_CSV = os.path.join(DATA_DIR, "zhihu_data.csv")
NEW_CSV = os.path.join(DATA_DIR, "zhihu_data_new.csv")

# 搜索结果可能出现的卡片选择器（可按需扩展）
CARD_SELECTOR = ".ContentItem, .SearchResult-Card, .List-item"
TITLE_LINK_SELECTOR = "a[href*='/question/'], a[href*='/p/'], a[href*='/zvideo/']"


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
# Debug：保存截图 + HTML + 诊断信息
# =========================
def _safe_name(s: str, max_len: int = 30) -> str:
    s = s.strip()
    if not s:
        return "empty"
    # 只保留字母数字中文和少量符号，避免文件名非法
    s2 = []
    for ch in s:
        if ch.isalnum() or ch in ("-", "_"):
            s2.append(ch)
        elif "\u4e00" <= ch <= "\u9fff":
            s2.append(ch)
    out = "".join(s2)[:max_len]
    return out or "kw"


def dump_debug(page: Page, keyword: str, reason: str):
    """把当前页面的截图/HTML/诊断信息落地到 debug/，用于在 Actions artifact 中下载查看"""
    try:
        Path(DEBUG_DIR).mkdir(parents=True, exist_ok=True)

        ts = time.strftime("%Y%m%d_%H%M%S")
        name = _safe_name(keyword)
        prefix = Path(DEBUG_DIR) / f"no_result_{name}_{ts}"

        png_path = str(prefix) + ".png"
        html_path = str(prefix) + ".html"
        txt_path = str(prefix) + ".txt"

        # 截图 + HTML
        page.screenshot(path=png_path, full_page=True)
        Path(html_path).write_text(page.content(), encoding="utf-8")

        # 诊断信息
        try:
            title = page.title()
        except Exception:
            title = "(title unavailable)"
        info = [
            f"reason: {reason}",
            f"keyword: {keyword}",
            f"url: {page.url}",
            f"title: {title}",
            f"time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        Path(txt_path).write_text("\n".join(info), encoding="utf-8")

        logger.warning(f"已保存 debug：{png_path} / {html_path} / {txt_path}")
    except Exception as e:
        logger.warning(f"保存 debug 失败：{e}")


def looks_like_blocked(page: Page) -> bool:
    """粗略判断是否进入登录/安全验证/风控页（仅用于提示，不做强依赖）"""
    try:
        t = (page.title() or "").strip()
    except Exception:
        t = ""
    u = (page.url or "").strip()

    suspect_words = ["安全验证", "验证", "登录", "异常", "风险", "captcha", "验证码"]
    if any(w in t for w in suspect_words):
        return True
    if any(x in u for x in ("sign_in", "signin", "login", "captcha", "security")):
        return True
    return False


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


def goto_with_retry(page: Page, url: str, wait_until: str = "domcontentloaded"):
    """带重试的 page.goto，避免偶发超时导致整轮关键词空掉"""
    last_err = None
    for i in range(max(GOTO_RETRIES, 1)):
        try:
            page.goto(url, wait_until=wait_until, timeout=GOTO_TIMEOUT_MS)
            return
        except PlaywrightTimeoutError as e:
            last_err = e
            logger.warning(f"goto 超时（{i+1}/{GOTO_RETRIES}）：{url}")
        except Exception as e:
            last_err = e
            logger.warning(f"goto 异常（{i+1}/{GOTO_RETRIES}）：{url} err={e}")
        time.sleep(random.uniform(1.5, 3.0))
    raise last_err if last_err else RuntimeError("goto_with_retry failed")


# =========================
# 关键词抓取
# =========================
def scrape_zhihu_keyword(page: Page, keyword: str) -> List[Dict]:
    results: List[Dict] = []
    logger.info(f"开始抓取关键词：{keyword}")

    # 构造搜索 URL
    search_url = f"https://www.zhihu.com/search?type=content&q={quote(keyword)}"

    try:
        goto_with_retry(page, search_url, wait_until="domcontentloaded")
    except Exception as e:
        logger.warning(f"关键词 {keyword} 打开搜索页失败：{e}")
        dump_debug(page, keyword, f"goto_failed: {e}")
        return []

    # 记录一下当前 url / title 便于诊断
    try:
        logger.info(f"page.url={page.url} title={page.title()}")
    except Exception:
        logger.info(f"page.url={page.url}")

    # 等待结果 DOM
    try:
        page.wait_for_selector(CARD_SELECTOR, timeout=15000)
    except Exception:
        msg = "未检测到搜索结果 DOM"
        if looks_like_blocked(page):
            msg += "（疑似登录/安全验证/风控页）"
        logger.warning(f"关键词 {keyword} {msg}")
        dump_debug(page, keyword, msg)
        return []

    # 模拟浏览行为（让懒加载有机会加载出来）
    time.sleep(random.uniform(1.5, 3.0))
    human_scroll(page, times=5)
    time.sleep(random.uniform(0.8, 1.6))

    # 获取所有卡片
    cards = page.query_selector_all(CARD_SELECTOR)
    logger.info(f"关键词「{keyword}」抓到 {len(cards)} 个卡片")

    # 如果卡片为 0，直接保存 debug（你现在遇到的就是这个情况）
    if len(cards) == 0:
        msg = "cards==0（选择器可能失效 / 风控 / 结果区未加载）"
        if looks_like_blocked(page):
            msg += "（疑似登录/安全验证/风控页）"
        dump_debug(page, keyword, msg)
        return []

    for card in cards[:MAX_RESULTS]:
        try:
            # 1. 提取标题和链接
            title_el = card.query_selector(TITLE_LINK_SELECTOR)
            if not title_el:
                continue

            title = (title_el.inner_text() or "").strip()
            url = title_el.get_attribute("href") or ""
            url = url.strip()

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

            # 4. 提取发布时间
            publish_time = extract_publish_time(card)

            results.append({
                "keyword": keyword,
                "title": title,
                "author": author,
                "url": url,
                "publish_time": publish_time,
                "excerpt": excerpt[:200],
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
    os.makedirs(DEBUG_DIR, exist_ok=True)

    all_data: List[Dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
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
        else:
            logger.warning("未找到 storage_state.json，可能会触发登录/风控")

        context = browser.new_context(**context_kwargs)

        # 注入反爬虫绕过脚本
        context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN','zh','en'] });
        """)

        page = context.new_page()
        page.set_default_timeout(GOTO_TIMEOUT_MS)

        # 打印最终生效的关键词数量（便于 Actions 日志确认）
        logger.info(f"KEYWORDS_COUNT={len([k for k in KEYWORDS if k.strip()])}")

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
        logger.warning("本次未抓取到任何数据（请下载 debug/ 里的截图和 HTML 查看原因）")
        return

    # 本次运行内部去重
    all_data = deduplicate_by_url(all_data)
    df_new = pd.DataFrame(all_data)

    # 打印预览
    print("\n抓取结果预览:")
    cols = [c for c in ["title", "publish_time", "author"] if c in df_new.columns]
    if cols:
        print(df_new[cols].head())
    else:
        print(df_new.head())

    # 与历史数据对比 (增量更新)
    if os.path.exists(OUT_CSV):
        try:
            df_old = pd.read_csv(OUT_CSV, encoding="utf-8-sig")
            old_urls = set(df_old.get("url", pd.Series([], dtype=str)).dropna().tolist())
            df_increment = df_new[~df_new["url"].isin(old_urls)]
        except Exception as e:
            logger.error(f"读取旧数据失败，将全量保存: {e}")
            df_increment = df_new
    else:
        df_increment = df_new

    # 保存新增数据
    if not df_increment.empty:
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
