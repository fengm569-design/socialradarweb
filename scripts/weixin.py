import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import os
import re
from datetime import datetime

# ================= 配置区 =================
KEYWORDS = ["自动化学会", "王飞跃", "杨孟飞", "郑南宁", "高会军", "张承慧", "戴琼海", "何友"]
MAX_PAGES = 3
COOKIE_FILE = "cookie.txt"  # 存放多个 Cookie 的文件，每行一个

# 数据保存位置：获取当前脚本所在目录的上一级目录，并拼接 'data' 文件夹
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "wechat_research_data.csv")


# ==========================================

class WeChatSpider:
    def __init__(self):
        self.session = requests.Session()
        self.cookies_list = []
        self.current_cookie_index = 0

        # 基础请求头
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://weixin.sogou.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        }

        self.ensure_dir_exists()
        self.load_cookies()

    def ensure_dir_exists(self):
        """确保上一级的 data 文件夹存在，不存在则自动创建"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            print(f"📁 已自动创建数据文件夹: {DATA_DIR}")

    def load_cookies(self):
        """从 txt 文件加载所有的 Cookie"""
        if os.path.exists(COOKIE_FILE):
            with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                # 读取所有行，去除首尾空格，并过滤掉空行
                self.cookies_list = [line.strip() for line in f if line.strip()]

            if not self.cookies_list:
                print(f"❌ {COOKIE_FILE} 文件内容为空，请填入 Cookie。")
                exit()

            print(f"✅ 成功加载 {len(self.cookies_list)} 个 Cookie 备用。")
            self.apply_current_cookie()
        else:
            print(f"❌ 找不到 {COOKIE_FILE}，请在当前目录创建并添加 Cookie（每行一个）。")
            exit()

    def apply_current_cookie(self):
        """将当前索引的 Cookie 应用到请求头"""
        if self.current_cookie_index < len(self.cookies_list):
            self.headers["Cookie"] = self.cookies_list[self.current_cookie_index]
            print(f"🔄 当前正在使用第 {self.current_cookie_index + 1} 个 Cookie。")

    def switch_to_next_cookie(self):
        """当遇到验证码时，切换到下一个 Cookie"""
        self.current_cookie_index += 1
        if self.current_cookie_index < len(self.cookies_list):
            print(f"\n⚠️ 触发反爬封锁！自动无缝切换至第 {self.current_cookie_index + 1} 个 Cookie...")
            self.apply_current_cookie()
            return True
        else:
            print("\n🚨 警报：所有的 Cookie 均已失效或被封禁！程序即将停止。")
            print("💡 建议：请开启手机热点更换电脑 IP，并重新获取一批新 Cookie 填入文档。")
            return False

    def save_data_immediately(self, data_list):
        """抓完即存，防止意外丢失"""
        if not data_list:
            return
        df = pd.DataFrame(data_list)
        file_exists = os.path.isfile(OUTPUT_FILE)
        df.to_csv(OUTPUT_FILE, mode='a', index=False, header=not file_exists, encoding="utf-8-sig")

    def run(self):
        # 每次全新运行前，自动清理上一次生成的旧数据，防止重复叠加
        if os.path.exists(OUTPUT_FILE):
            os.remove(OUTPUT_FILE)
            print(f"🗑️ 已清理旧数据文件: {OUTPUT_FILE}")

        for kw in KEYWORDS:
            print(f"\n🚀 正在检索关键词: 【{kw}】")

            page = 1
            while page <= MAX_PAGES:
                url = f"https://weixin.sogou.com/weixin?type=2&query={kw}&page={page}&ie=utf8"

                try:
                    # 模拟真人阅读停顿，非常关键
                    time.sleep(random.uniform(5, 10))

                    response = self.session.get(url, headers=self.headers, timeout=15)
                    response.encoding = 'utf-8'

                    # --- 核心：拦截验证码并切换 Cookie ---
                    if "antispider" in response.url or "验证码" in response.text:
                        if self.switch_to_next_cookie():
                            continue  # 切换成功，不增加 page，重试当前页！
                        else:
                            return  # 切换失败（Cookie用光），直接结束整个爬虫

                    soup = BeautifulSoup(response.text, 'html.parser')
                    items = soup.select('ul.news-list > li')

                    if not items:
                        print(f"   第 {page} 页没搜到内容，跳过该词。")
                        break  # 跳出 while，进入下一个关键词

                    current_page_data = []
                    for item in items:
                        title_tag = item.select_one('.txt-box h3 a')

                        # 解析文章临时链接
                        article_url = "N/A"
                        if title_tag and 'href' in title_tag.attrs:
                            article_url = "https://weixin.sogou.com" + title_tag['href']

                        # --- 核心修改：精准提取 Unix 时间戳并转换 ---
                        pub_date = "N/A"
                        time_script = item.select_one('.s2 script')
                        if time_script and time_script.string:
                            # 利用正则匹配 timeConvert('1650323334') 中的数字
                            match = re.search(r"timeConvert\('(\d+)'\)", time_script.string)
                            if match:
                                timestamp = int(match.group(1))
                                pub_date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

                        # 兜底：如果没找到精确时间戳，取相对时间文本
                        if pub_date == "N/A":
                            s2_tag = item.select_one('.s2')
                            if s2_tag:
                                pub_date = s2_tag.get_text(strip=True).replace("timeConvert", "").strip()

                        # 组装本页数据
                        current_page_data.append({
                            "关键词": kw,
                            "文章标题": title_tag.get_text(strip=True) if title_tag else "N/A",
                            "公众号": item.select_one('.account').get_text(strip=True) if item.select_one(
                                '.account') else "N/A",
                            "发布日期": pub_date,
                            "摘要": item.select_one('.txt-info').get_text(strip=True) if item.select_one(
                                '.txt-info') else "N/A",
                            "文章链接": article_url
                        })

                    self.save_data_immediately(current_page_data)
                    print(f"   ✅ 第 {page} 页抓取成功")

                    # 只有当前页成功抓取，才进入下一页
                    page += 1

                except Exception as e:
                    print(f"❌ 抓取 '{kw}' 第 {page} 页时出现网络异常: {e}")
                    # 如果网络异常报错，强制跳过当前页进入下一页，防止死循环
                    page += 1

        print("\n🎉 抓取任务圆满结束！")
        print(f"📂 最终数据存放路径: {os.path.abspath(OUTPUT_FILE)}")


if __name__ == "__main__":
    spider = WeChatSpider()
    spider.run()