from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import json
import re
import uvicorn
# 导入官方 SDK
from cozepy import Coze, TokenAuth, Stream, WorkflowEvent, WorkflowEventType, COZE_CN_BASE_URL

# ================= 配置区 =================
COZE_API_TOKEN = 'cztei_huOzAFPbqHv2tPhCpVlFE3ooBtS0jUvzt2DzMfmwBcNUkbWxyxAeEDLjb3dMlTMdW'
WORKFLOW_ID = '7603685878149660718'

coze = Coze(auth=TokenAuth(token=COZE_API_TOKEN), base_url=COZE_CN_BASE_URL)
# =========================================

# 1. 初始化 FastAPI 应用
app = FastAPI(
    title="Social Radar 舆情插件",
    description="供 Agent 调用的实时数据抓取接口"
)


# 2. 定义智能体传给插件的参数格式
class RadarRequest(BaseModel):
    keywords: List[str]  # 接收智能体提取的关键词，例如 ["自动化学会", "大模型"]
    platform: str = "xiaohongshu"


# 3. 核心抓取与清洗函数
def fetch_and_clean_data(keywords: List[str]):
    final_results = []

    # 为了避免截断，保持 batch size = 1 的安全策略
    for kw in keywords:
        print(f"📦 正在通过 Coze 节点处理关键词: {kw}")
        try:
            stream = coze.workflows.runs.stream(
                workflow_id=WORKFLOW_ID,
                parameters={"input": [kw]}
            )

            for event in stream:
                if event.event == WorkflowEventType.MESSAGE:
                    msg = event.message
                    if not msg.content:
                        continue

                    try:
                        content_json = json.loads(msg.content)
                    except json.JSONDecodeError:
                        continue

                    output_data = content_json.get("output") or content_json.get("data")
                    if not output_data:
                        continue

                    if isinstance(output_data, str):
                        cleaned_str = output_data.strip()
                        # 剥去 Markdown 外壳
                        if cleaned_str.startswith("```json"):
                            cleaned_str = cleaned_str[7:]
                        elif cleaned_str.startswith("```"):
                            cleaned_str = cleaned_str[3:]
                        if cleaned_str.endswith("```"):
                            cleaned_str = cleaned_str[:-3]
                        cleaned_str = cleaned_str.strip()

                        try:
                            parsed_list = json.loads(cleaned_str)
                            if isinstance(parsed_list, list):
                                final_results.extend(parsed_list)
                        except json.JSONDecodeError:
                            # 尝试自动修复 JSON
                            try:
                                fixed_str = re.sub(r',\s*([\]}])', r'\1', cleaned_str)
                                fixed_str = fixed_str.replace("'", '"')
                                parsed_list = json.loads(fixed_str)
                                if isinstance(parsed_list, list):
                                    final_results.extend(parsed_list)
                            except Exception:
                                pass  # 修复失败则跳过

                    elif isinstance(output_data, list):
                        final_results.extend(output_data)

        except Exception as e:
            print(f"❌ 运行发生异常: {e}")

    # 执行数据净化：剔除特定的作者数据，确保语料库的专注度
    purified_results = []
    for item in final_results:
        # 兼容不同的键名（如 author 或 作者）
        author_name = str(item.get("author", "")) + str(item.get("作者", ""))

        # 净化逻辑
        if "王飞跃" not in author_name:
            purified_results.append(item)

    return purified_results


# 4. 定义暴露给智能体的接口路由
@app.post("/api/run_spider")
def run_spider(request: RadarRequest):
    print(f"📡 接收到智能体指令: 在 {request.platform} 追踪关键词 {request.keywords}")

    if not request.keywords:
        raise HTTPException(status_code=400, detail="关键词不能为空")

    # 调用上面的抓取逻辑
    data = fetch_and_clean_data(request.keywords)

    # 返回标准的 JSON 格式给智能体
    return {
        "status": "success",
        "message": f"成功在 {request.platform} 获取并清洗了数据",
        "total_records": len(data),
        "data": data
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)