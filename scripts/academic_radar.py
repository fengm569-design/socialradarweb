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
import re
import base64

ENCODED_GITHUB_TOKEN = "Z2hwX0s4dGdHZzViaW9qZXRWdHNaemtKdEpMUmVmQnRRejNtRmpqYg=="
ENCODED_SS_API_KEY = "aU9CMTQ5R2xjSzJpQzJRRnFXaG9ZNVdSa21YZjNSVksyZUlqTW5lRA=="

# 运行时自动解码为明文
try:
    GITHUB_TOKEN = base64.b64decode(ENCODED_GITHUB_TOKEN).decode('utf-8')
    SS_API_KEY = base64.b64decode(ENCODED_SS_API_KEY).decode('utf-8')
except Exception as e:
    print(f"⚠️ 解码 Token 失败，请检查编码格式: {e}")
    GITHUB_TOKEN = ""
    SS_API_KEY = ""

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

CURRENT_YEAR = datetime.now().year
YEARS_RANGE = [str(y) for y in range(CURRENT_YEAR - 4, CURRENT_YEAR + 1)]

# =====================================================================
# 🧠 核心强化：NLP 英文文献中文化映射与过滤词典
# =====================================================================
ACADEMIC_STOPWORDS = {
    "model", "data", "system", "paper", "propose", "method", "research", "result",
    "based", "approach", "performance", "show", "algorithm", "problem", "application",
    "study", "new", "time", "work", "information", "different", "state", "user",
    "feature", "task", "process", "design", "high", "low", "large", "small",
    "technology", "analysis", "environment", "development", "provide", "technique",
    "use", "using", "proposed", "models", "systems", "methods", "results", "networks"
}

ALLOWED_ACRONYMS = {"ai", "gpt", "llm", "aigc", "api", "vla", "rl", "cv", "nlp", "iot"}

ENG_TO_CN_MAP = {
    "learning": "深度学习", "network": "神经网络", "neural": "神经网络",
    "robot": "机器人技术", "control": "控制理论", "vision": "计算机视觉",
    "sensor": "多模态传感", "optimization": "优化算法", "detection": "目标检测",
    "autonomous": "自主导航", "tracking": "目标跟踪", "planning": "路径规划",
    "intelligence": "群体智能", "reinforcement": "强化学习", "cloud": "云边协同",
    "edge": "边缘计算", "security": "网络安全", "privacy": "数据隐私",
    "dataset": "开源数据集", "framework": "底层架构", "architecture": "系统架构",
    "deep": "深度学习", "machine": "机器学习", "image": "图像处理",
    "semantic": "语义分析", "graph": "图神经网络", "attention": "注意力机制",
    "transformer": "大模型基座", "generative": "生成式框架", "diffusion": "扩散模型"
}


def create_robust_session():
    session = requests.Session()
    retry_strategy = Retry(total=8, connect=5, read=5, backoff_factor=3, status_forcelist=[429, 500, 502, 503, 504],
                           allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


http_session = create_robust_session()


def fetch_semantic_scholar(keyword):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": keyword, "limit": 50, "fields": "year,abstract,citationCount"}
    headers = {"User-Agent": "Mozilla/5.0"}
    if SS_API_KEY: headers["x-api-key"] = SS_API_KEY
    try:
        res = http_session.get(url, params=params, headers=headers, timeout=(15, 60))
        if res.status_code == 200: return [d for d in res.json().get('data', []) if d.get('year') and d.get('abstract')]
    except:
        pass
    return []


def fetch_arxiv(keyword):
    url = "http://export.arxiv.org/api/query"
    params = {"search_query": f'all:"{keyword}"', "sortBy": "submittedDate", "sortOrder": "descending",
              "max_results": 50}
    headers = {"User-Agent": "Mozilla/5.0"}
    papers = []
    try:
        res = http_session.get(url, params=params, headers=headers, timeout=(15, 60))
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            for entry in root.findall('atom:entry', ns):
                pub = entry.find('atom:published', ns)
                summ = entry.find('atom:summary', ns)
                if pub is not None and summ is not None: papers.append(
                    {"year": pub.text[:4], "abstract": summ.text.replace('\n', ' ')})
    except:
        pass
    return papers


def fetch_github(keyword):
    url = "https://api.github.com/search/repositories"
    params = {"q": f'"{keyword}"', "sort": "stars", "order": "desc", "per_page": 30}
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN: headers["Authorization"] = f"token {GITHUB_TOKEN}"
    repos = []
    try:
        res = http_session.get(url, params=params, headers=headers, timeout=(10, 30))
        if res.status_code == 200:
            for item in res.json().get('items', []): repos.append(
                {"year": item.get('created_at', '')[:4], "abstract": item.get('description', '') or ''})
    except:
        pass
    return repos


def extract_nlp_wordcloud(corpus_text, top_k=50):
    if not corpus_text.strip(): return [{"name": "暂无数据", "value": 10}]

    keywords_with_weight = jieba.analyse.extract_tags(corpus_text, topK=250, withWeight=True)
    word_cloud_dict = {}

    for word, weight in keywords_with_weight:
        word_lower = word.lower()
        mapped_value = int(weight * 500)
        if len(word) <= 1 or word.isnumeric() or word_lower in ACADEMIC_STOPWORDS: continue
        if re.match(r'^[a-zA-Z0-9]+$', word):
            if word_lower in ENG_TO_CN_MAP:
                cn_word = ENG_TO_CN_MAP[word_lower]
                word_cloud_dict[cn_word] = word_cloud_dict.get(cn_word, 0) + mapped_value
            elif word_lower in ALLOWED_ACRONYMS:
                word_cloud_dict[word.upper()] = word_cloud_dict.get(word.upper(), 0) + mapped_value
            continue
        word_cloud_dict[word] = word_cloud_dict.get(word, 0) + mapped_value

    wc_data = [{"name": k, "value": max(10, v)} for k, v in word_cloud_dict.items()]
    wc_data = sorted(wc_data, key=lambda x: x['value'], reverse=True)[:top_k]
    for cn_name in OFFICIAL_HOT_TOPICS.keys(): wc_data.append({"name": cn_name, "value": 85})
    return wc_data


def main():
    print("🚀 [启动] 学术热点雷达 - 平台全维解构引擎 ")

    corpuses = {"total": "", "ss": "", "ar": "", "gh": ""}

    trend_data = {
        "years": YEARS_RANGE,
        "total": [],
        "semantic_scholar": [],
        "arxiv": [],
        "github": []
    }

    for cn_name, en_query in OFFICIAL_HOT_TOPICS.items():
        print(f"\n⏳ 正在分析: [{cn_name}]")
        ss_data = fetch_semantic_scholar(en_query)
        ar_data = fetch_arxiv(en_query)
        gh_data = fetch_github(en_query)

        print(f"   ├─ 命中数据: 论文 {len(ss_data) + len(ar_data)} 篇, 开源库 {len(gh_data)} 个")

        heat_total = {y: 0 for y in YEARS_RANGE}
        heat_ss = {y: 0 for y in YEARS_RANGE}
        heat_ar = {y: 0 for y in YEARS_RANGE}
        heat_gh = {y: 0 for y in YEARS_RANGE}

        for item in ss_data:
            year = str(item.get('year'))
            text = str(item.get('abstract') or '') + " "
            if year in heat_ss:
                heat_ss[year] += 1
                heat_total[year] += 1
            corpuses["ss"] += text
            corpuses["total"] += text

        for item in ar_data:
            year = str(item.get('year'))
            text = str(item.get('abstract') or '') + " "
            if year in heat_ar:
                heat_ar[year] += 1
                heat_total[year] += 1
            corpuses["ar"] += text
            corpuses["total"] += text

        for item in gh_data:
            year = str(item.get('year'))
            text = str(item.get('abstract') or '') + " "
            if year in heat_gh:
                heat_gh[year] += 1
                heat_total[year] += 1
            corpuses["gh"] += text
            corpuses["total"] += text

        trend_data["total"].append({"name": cn_name, "data": [heat_total[y] for y in YEARS_RANGE]})
        trend_data["semantic_scholar"].append({"name": cn_name, "data": [heat_ss[y] for y in YEARS_RANGE]})
        trend_data["arxiv"].append({"name": cn_name, "data": [heat_ar[y] for y in YEARS_RANGE]})
        trend_data["github"].append({"name": cn_name, "data": [heat_gh[y] for y in YEARS_RANGE]})

        time.sleep(random.uniform(3, 6))

    print("\n🧠 正在运行 NLP 分平台提取深层语义图谱...")

    final_output = {
        "wordClouds": {
            "total": extract_nlp_wordcloud(corpuses["total"], top_k=60),
            "semantic_scholar": extract_nlp_wordcloud(corpuses["ss"], top_k=40),
            "arxiv": extract_nlp_wordcloud(corpuses["ar"], top_k=40),
            "github": extract_nlp_wordcloud(corpuses["gh"], top_k=40)
        },
        "trendData": trend_data
    }

    os.makedirs('../data', exist_ok=True)
    output_path = '../data/academic_summary.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 平台独立数据构建完成！JSON 已保存至: {output_path}")


if __name__ == "__main__":
    main()