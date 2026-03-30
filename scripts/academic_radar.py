import requests
import json
import time
import random
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import jieba
import jieba.analyse

# =====================================================================
# ⚙️ 配置区 (仅需修改这里)
# =====================================================================

# 【配置 1】: GitHub Token (防限流)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "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")

# 【配置 2】: 官方权威热词来源 (例如：中国科协、中国自动化学会发布的年度前沿)
OFFICIAL_HOT_TOPICS = {
    "具身智能": "Embodied AI",
    "脑机接口": "Brain-Computer Interface",
    "大语言模型": "Large Language Models",
    "无人系统": "Autonomous Unmanned Systems",
    "类脑计算": "Brain-inspired Computing",
    "生成式AI": "Generative AI",
    "智能控制": "Intelligent Control",
    "工业互联网": "Industrial Internet"
}

# 统计分析的时间跨度 (近5年)
CURRENT_YEAR = datetime.now().year
YEARS_RANGE = [str(y) for y in range(CURRENT_YEAR - 4, CURRENT_YEAR + 1)]

# =====================================================================
# 🛡️ 核心强化：构建自动重试的请求会话
# =====================================================================
def create_robust_session():
    """创建一个带有指数退避重试机制的会话，专治 429 限流和 50x 服务器崩溃"""
    session = requests.Session()
    retry_strategy = Retry(
        total=5,               # 最多重试 5 次
        backoff_factor=2,      # 每次重试等待时间指数增加: 2s, 4s, 8s, 16s...
        status_forcelist=[429, 500, 502, 503, 504], # 遇到这些状态码强制重试
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

# 全局复用这一个强化版的 Session
http_session = create_robust_session()

# =====================================================================

def fetch_semantic_scholar(keyword):
    """获取 Semantic Scholar 论文摘要和年份 (增强版)"""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": keyword,
        "limit": 50,
        "fields": "year,abstract,citationCount"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        # 使用 http_session 替代 requests，并增加超时时间
        res = http_session.get(url, params=params, headers=headers, timeout=30)
        if res.status_code == 200:
            data = res.json().get('data', [])
            valid_data = [d for d in data if d.get('year') and d.get('abstract')]
            return valid_data
        else:
            print(f"      [❌ 报错] Semantic Scholar 异常: 状态码 {res.status_code}")
    except Exception as e:
        print(f"      [❌ 崩溃] Semantic Scholar 请求失败: {str(e)[:100]}")

    return []


def fetch_arxiv(keyword):
    """获取 arXiv 预印本趋势和摘要 (增强版)"""
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f'all:"{keyword}"',
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": 50
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    papers = []
    try:
        # arXiv 服务器在国外，响应较慢，设置超时 40 秒
        res = http_session.get(url, params=params, headers=headers, timeout=40)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            for entry in root.findall('atom:entry', ns):
                published_node = entry.find('atom:published', ns)
                summary_node = entry.find('atom:summary', ns)

                if published_node is not None and summary_node is not None:
                    papers.append({
                        "year": published_node.text[:4],
                        "abstract": summary_node.text.replace('\n', ' ')
                    })
        else:
            print(f"      [❌ 报错] arXiv 异常: 状态码 {res.status_code}")
    except Exception as e:
        print(f"      [❌ 崩溃] arXiv 请求超时或网络断开: {str(e)[:100]}")

    return papers


def fetch_github(keyword):
    """获取 GitHub 开源项目趋势和描述"""
    url = "https://api.github.com/search/repositories"
    params = {"q": keyword, "sort": "stars", "order": "desc", "per_page": 30}
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN and not GITHUB_TOKEN.startswith("ghp_请替换"):
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    repos = []
    try:
        res = http_session.get(url, params=params, headers=headers, timeout=20)
        if res.status_code == 200:
            items = res.json().get('items', [])
            for item in items:
                created_at = item.get('created_at', '')[:4]
                desc = item.get('description', '')
                repos.append({"year": created_at, "abstract": desc})
    except Exception as e:
        print(f"      [❌ 崩溃] GitHub 请求失败: {str(e)[:100]}")
    return repos


def main():
    print("🚀 [启动] 学术热点雷达 - 官方数据抓取聚合引擎")

    trend_series = []
    all_text_corpus = ""

    for cn_name, en_query in OFFICIAL_HOT_TOPICS.items():
        print(f"\n⏳ 正在分析权威方向: [{cn_name}] ({en_query})")

        yearly_heat = {year: 0 for year in YEARS_RANGE}

        # 1. 抓取数据
        ss_data = fetch_semantic_scholar(en_query)
        ar_data = fetch_arxiv(en_query)
        gh_data = fetch_github(en_query)

        print(f"   ├─ Semantic Scholar: {len(ss_data)} 篇核心论文")
        print(f"   ├─ arXiv: {len(ar_data)} 篇前沿预印本")
        print(f"   └─ GitHub: {len(gh_data)} 个高星开源工程")

        # 2. 聚合文本与热度
        all_sources = ss_data + ar_data + gh_data
        for item in all_sources:
            year = str(item.get('year'))
            text = str(item.get('abstract') or '')

            if year in yearly_heat:
                yearly_heat[year] += 1

            all_text_corpus += text + " "

        trend_series.append({
            "name": cn_name,
            "data": [yearly_heat[y] for y in YEARS_RANGE]
        })

        # 🛡️ 核心强化：随机休眠时间 (7~15秒)，极大降低被 Semantic Scholar 判断为机器人的概率
        sleep_time = random.uniform(7, 15)
        print(f"   💤 为防止限流，随机休眠 {sleep_time:.1f} 秒...")
        time.sleep(sleep_time)

    print("\n🧠 正在运行 NLP (结巴 TF-IDF) 提取深层语义图谱...")
    for cn_name in OFFICIAL_HOT_TOPICS.keys():
        jieba.add_word(cn_name)

    keywords_with_weight = jieba.analyse.extract_tags(all_text_corpus, topK=60, withWeight=True)

    word_cloud_data = []
    for word, weight in keywords_with_weight:
        if len(word) > 1 and not word.isnumeric():
            mapped_value = int(weight * 500)
            word_cloud_data.append({"name": word, "value": max(10, mapped_value)})

    for cn_name in OFFICIAL_HOT_TOPICS.keys():
        word_cloud_data.append({"name": cn_name, "value": 85})

    final_output = {
        "wordCloud": word_cloud_data,
        "trendData": {
            "years": YEARS_RANGE,
            "series": trend_series
        }
    }

    os.makedirs('../data', exist_ok=True)
    output_path = '../data/academic_summary.json'

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 聚合完成！数据已完美格式化并保存至: {output_path}")

if __name__ == "__main__":
    main()