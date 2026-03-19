import os
import pandas as pd
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'data'))

OUTPUT_FILE = os.path.join(DATA_DIR, 'academic_summary.json')

INPUT_FILES = [
    os.path.join(DATA_DIR, 'xiaohongshu_data.csv'),
    os.path.join(DATA_DIR, 'zhihu_data.csv')
]

print(f"当前寻找的数据文件夹绝对路径是: {DATA_DIR}")

ACADEMIC_KEYWORDS = [
    "具身智能", "大语言模型", "无人系统", "强化学习", "智能控制",
    "机器视觉", "工业互联网", "自动驾驶", "脑机接口", "数字孪生"
]


def load_data():
    """读取所有CSV文件并合并（适配知乎和小红书格式）"""
    dfs = []
    for file in INPUT_FILES:
        if os.path.exists(file):
            print(f"✅ 找到文件: {file}，正在读取...")
            try:
                df = pd.read_csv(file, encoding='utf-8')
                print(f"   -> 成功读取，包含 {len(df)} 行数据。")
                possible_text_cols = ['excerpt', 'title', 'text', 'desc', '正文']
                for col in possible_text_cols:
                    if col in df.columns and 'content' not in df.columns:
                        df.rename(columns={col: 'content'}, inplace=True)
                        print(f"   -> 已将文本列 '{col}' 重命名为 'content'")
                        break

                possible_time_cols = ['publish_time', 'created_at', 'time', 'date']
                for col in possible_time_cols:
                    if col in df.columns and 'publish_time' not in df.columns:
                        df.rename(columns={col: 'publish_time'}, inplace=True)
                        print(f"   -> 已将时间列 '{col}' 重命名为 'publish_time'")
                        break

                dfs.append(df)
            except Exception as e:
                print(f"❌ 读取文件 {file} 失败，报错: {e}")
        else:
            print(f"❌ 警告: 在该路径下找不到文件 {file}")

    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def generate_report():
    df = load_data()


    if df.empty or 'content' not in df.columns:
        print("未找到有效数据，生成默认演示数据...")
        mock_data = {
            "wordCloud": [{"name": k, "value": (1000 - i * 80)} for i, k in enumerate(ACADEMIC_KEYWORDS)],
            "trendData": {
                "years": ["2021", "2022", "2023", "2024", "2025"],
                "series": [
                    {"name": "具身智能", "data": [80, 150, 420, 850, 1200]},
                    {"name": "大语言模型", "data": [180, 260, 950, 1100, 1150]},
                    {"name": "智能控制", "data": [620, 650, 640, 660, 670]}
                ]
            }
        }
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(mock_data, f, ensure_ascii=False, indent=2)
        return

    print("开始分析真实数据...")

    # 1. 统计词云数据 (全局词频)
    word_counts = {word: 0 for word in ACADEMIC_KEYWORDS}

    # 2. 统计趋势数据 (按年/月统计)
    # 尝试转换时间列
    if 'publish_time' in df.columns:
        df['publish_time'] = pd.to_datetime(df['publish_time'], errors='coerce')
        df['year'] = df['publish_time'].dt.strftime('%Y').fillna('未知')
    else:
        df['year'] = '2024'  # 默认值

    years = sorted([y for y in df['year'].unique() if y != '未知'])
    if not years:
        years = ['2023', '2024', '2025']

    trend_counts = {word: {year: 0 for year in years} for word in ["具身智能", "大语言模型", "智能控制"]}

    # 遍历文本进行精确统计
    for index, row in df.iterrows():
        text = str(row['content'])
        year = str(row['year'])

        for word in ACADEMIC_KEYWORDS:
            count = text.count(word)
            if count > 0:
                word_counts[word] += count
                if word in trend_counts and year in years:
                    trend_counts[word][year] += count

    # 组装词云输出格式
    wordcloud_data = [{"name": k, "value": v} for k, v in word_counts.items() if v > 0]
    # 如果没匹配到，给点保底数据
    if not wordcloud_data:
        wordcloud_data = [{"name": "暂无匹配数据", "value": 1}]

    # 组装趋势图输出格式
    series_data = []
    for word, year_dict in trend_counts.items():
        series_data.append({
            "name": word,
            "data": [year_dict[y] for y in years]
        })

    final_report = {
        "wordCloud": wordcloud_data,
        "trendData": {
            "years": years,
            "series": series_data
        }
    }

    # 写入 JSON 文件
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2)
    print(f"分析完成！报告已生成至: {OUTPUT_FILE}")


if __name__ == "__main__":
    generate_report()