# weibo_incremental_crawl_with_keyword.py
# 依赖: pip install requests beautifulsoup4 lxml fake-useragent

import os
import time
import random
import logging
import csv
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Set
import requests
from requests.utils import cookiejar_from_dict
from bs4 import BeautifulSoup

# 配置日志
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# -------------- 配置区 --------------
KEYWORDS = ["范丽丽", "王飞跃"]

DATA_DIR = "data"
MAIN_CSV_PATH = os.path.join(DATA_DIR, "weibo_data.csv")  # 总数据库
NEW_CSV_PATH = os.path.join(DATA_DIR, "weibo_data_new.csv")  # 本次新增的数据

# 使用你提供的有效 COOKIE
COOKIE_STR = (
    "SCF=ApcIiOaFo4pU7vb6SNrlpHT6d3Ljzzkp1J61aznvfq_5zdIYA7Py1WL-fg0QNs6WTL5NOPOTYpYzrpGqbi4MW9Y.; "
    "XSRF-TOKEN=1hb0RX_NzQKoMTRwpfqOATOx; "
    "_s_tentry=weibo.com; "
    "Apache=1524760993846.74.1767574645747; "
    "SINAGLOBAL=1524760993846.74.1767574645747; "
    "ULV=1767574645773:1:1:1:1524760993846.74.1767574645747:; "
    "SUB=_2A25EX31fDeRhGeBP41sX-CnMwj-IHXVnFfCXrDV8PUNbmtAYLVPMkW9NRTTZFJB4Z0QxqarJU8aU2tjI68l3Pi69; "
    "SUBP=0033WrSXqPxfM725Ws9jqgMF55529P9D9W5LkKmjvy9XbGv7TM2fwwQV5NHD95QceKn4SonNeh.0Ws4DqcjMi--NiK.Xi-2Ri--ciKnRi-zNSo2R1KqRS054e7tt; "
    "ALF=02_1770166799; "
    "WBPSESS=Dt2hbAUaXfkVprjyrAZT_MxsSZUZJCWPHA8XjYW4miofgPitpWe7BOSKWGdtrD4U4GgDUrX2xxzjkXhCY03qFLIBFOxPOxOVBVuINEQBwM0GLeylfGPiG5SiXdWACxFjdwQPqMhu82Xl-cEOOuGiiXEDtikbtI3YVSk9knK1x3cFyb-ZM_1CV7WCxG5WTpmu65YkFt9xMy6C00mcqlYzSQ=="
)

MAX_PAGES_PER_KEYWORD = 5
DELAY_MIN = 2.0
DELAY_MAX = 4.0
USE_PROXY = False
PROXIES = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}


# ---------------- 工具函数 ----------------

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)


def load_existing_urls(filepath) -> Set[str]:
    urls = set()
    if not os.path.exists(filepath):
        return urls
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('url'):
                    urls.add(row['url'])
    except Exception as e:
        logger.warning(f"读取历史数据失败: {e}")
    return urls


def standardize_time(time_str: str) -> str:
    if not time_str: return ""
    now = datetime.now()
    try:
        if '分钟前' in time_str:
            m = int(re.search(r'(\d+)', time_str).group(1))
            return (now - timedelta(minutes=m)).strftime('%Y-%m-%d %H:%M:%S')
        if '小时前' in time_str:
            h = int(re.search(r'(\d+)', time_str).group(1))
            return (now - timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')
        if '昨天' in time_str:
            t = re.search(r'(\d{2}:\d{2})', time_str).group(1)
            return f"{(now - timedelta(days=1)).strftime('%Y-%m-%d')} {t}:00"
        if '今天' in time_str:
            t = re.search(r'(\d{2}:\d{2})', time_str).group(1)
            return f"{now.strftime('%Y-%m-%d')} {t}:00"
        if '月' in time_str and '日' in time_str:
            if '年' not in time_str:
                clean = time_str.replace('月', '-').replace('日', '').replace(' ', '-')
                return f"{now.year}-{clean}:00" if len(clean.split('-')) > 2 else f"{now.year}-{clean} 00:00:00"
        return time_str
    except:
        return time_str


# ---------------- 抓取逻辑 ----------------

def search_m_weibo(session: requests.Session, keyword: str, existing_urls: Set[str]) -> List[Dict]:
    rows = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36",
        "MWeibo-Pwa": "1", "X-Requested-With": "XMLHttpRequest"
    }
    logger.info(f"m.weibo.cn 搜索: {keyword}")

    for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
        url = "https://m.weibo.cn/api/container/getIndex"
        params = {"containerid": f"100103type=1&q={keyword}", "page_type": "searchall", "page": page}
        try:
            resp = session.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()
            if data.get("ok") != 1: break
            cards = data.get("data", {}).get("cards", [])
            for card in cards:
                for c in card.get("card_group", [card]):
                    mblog = c.get("mblog")
                    if not mblog: continue
                    p_url = f"https://m.weibo.cn/detail/{mblog.get('id')}"
                    if p_url in existing_urls: continue

                    # 提取链接
                    soup = BeautifulSoup(mblog.get("text", ""), "lxml")
                    links = [a['href'] for a in soup.find_all('a', href=True)]

                    rows.append({
                        "keyword": keyword,  # 新增关键字字段
                        "source": "m.weibo.cn",
                        "username": mblog.get("user", {}).get("screen_name"),
                        "created_at": standardize_time(mblog.get("created_at")),
                        "content_text": soup.get_text(strip=True),
                        "links": list(set(links)),
                        "url": p_url,
                        "scraped_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
        except:
            break
    return rows


def search_s_weibo(session: requests.Session, keyword: str, existing_urls: Set[str]) -> List[Dict]:
    rows = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    logger.info(f"s.weibo.com 搜索: {keyword}")

    for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
        url = f"https://s.weibo.com/weibo?q={requests.utils.quote(keyword)}&page={page}"
        try:
            resp = session.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, "lxml")
            items = soup.select('.card-wrap')
            for item in items:
                mid = item.get("mid")
                if not mid: continue
                p_url = f"https://weibo.com/detail/{mid}"
                if p_url in existing_urls: continue

                content_div = item.select_one(".content .txt")
                if not content_div: continue

                time_tag = item.select_one(".from a")
                rows.append({
                    "keyword": keyword,  # 新增关键字字段
                    "source": "s.weibo.com",
                    "username": item.select_one(".name").get_text(strip=True) if item.select_one(".name") else "",
                    "created_at": standardize_time(time_tag.get_text(strip=True) if time_tag else ""),
                    "content_text": content_div.get_text(strip=True),
                    "links": [a['href'] for a in content_div.find_all('a', href=True) if a['href'].startswith('http')],
                    "url": p_url,
                    "scraped_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
        except:
            break
    return rows


# ---------- 数据保存 ----------

def save_data(session: requests.Session, new_posts: List[Dict]):
    if not new_posts:
        logger.info("本轮无新数据更新。")
        return

    final_records = []
    for post in new_posts:
        # 1. 保存原微博
        base_record = post.copy()
        base_record['type'] = 'post'
        base_record['page_title'] = ""
        base_record['page_text_snippet'] = ""
        final_records.append(base_record)

        # 2. 保存外链详情
        for link in post.get('links', []):
            if any(d in link for d in ['weibo.cn', 'weibo.com', 'sina.cn']): continue
            logger.info(f"解析外链: {link}")
            try:
                r = session.get(link, timeout=10)
                s = BeautifulSoup(r.text, "lxml")
                final_records.append({
                    "keyword": post['keyword'],  # 外链也带上关键字
                    "source": "external_link",
                    "username": "",
                    "created_at": "",
                    "content_text": "",
                    "url": link,
                    "type": "link_content",
                    "page_title": s.title.string.strip() if s.title else "",
                    "page_text_snippet": " ".join([t.strip() for t in s.stripped_strings])[:200],
                    "links": [],
                    "scraped_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                time.sleep(1)
            except:
                continue

    # 字段顺序定义
    fields = ["keyword", "source", "username", "created_at", "content_text", "url", "type", "page_title",
              "page_text_snippet", "scraped_at"]

    # 保存总表
    file_exists = os.path.exists(MAIN_CSV_PATH)
    with open(MAIN_CSV_PATH, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        if not file_exists: writer.writeheader()
        writer.writerows(final_records)

    # 保存本次新表
    with open(NEW_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(final_records)

    logger.info(f"任务完成：总表已更新，本次新增 {len(final_records)} 条数据。")


def main():
    ensure_dir(DATA_DIR)
    session = requests.Session()
    session.cookies = cookiejar_from_dict(parse_cookie_string(COOKIE_STR))

    existing_urls = load_existing_urls(MAIN_CSV_PATH)
    current_session_urls = set()  # 防止同一轮抓取中多个关键字重复添加同一条微博

    all_new_found = []

    for kw in KEYWORDS:
        # 获取新帖子，同时排除总表已有的和本轮已抓的
        found = search_m_weibo(session, kw, existing_urls | current_session_urls)
        if not found:
            found = search_s_weibo(session, kw, existing_urls | current_session_urls)

        for f in found:
            current_session_urls.add(f['url'])
            all_new_found.append(f)

    save_data(session, all_new_found)


def parse_cookie_string(s):
    return {c.split('=')[0].strip(): c.split('=')[1].strip() for c in s.split(';') if '=' in c}


if __name__ == "__main__":
    main()