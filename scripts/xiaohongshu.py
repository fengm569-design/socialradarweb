import os
import json
import csv
import time
# 导入官方 SDK
from cozepy import Coze, TokenAuth, Stream, WorkflowEvent, WorkflowEventType, COZE_CN_BASE_URL

# ================= 配置区 =================
# 1. 您的新 Token
COZE_API_TOKEN = 'cztei_h8iJmS2fEHmXbRZHuqMuQs1vv1GAWMdN6dttpON1e70vpPSATJMcHhavYMAVINIr3'

# 2. 您的工作流 ID
WORKFLOW_ID = '7603685878149660718'

# 3. 搜索关键词列表
INPUT_KEYWORDS = [
    "自动化学会", "王飞跃", "杨孟飞", "郑南宁", "张楠",
    "高会军", "侯增广", "孙彦广", "辛景民", "阳春华", "袁利",
    "张承慧", "赵延龙", "周杰", "陈杰", "戴琼海", "桂卫华",
    "郭雷", "何友", "蒋昌俊", "李少远", "钱锋"
]

# 4. 保存的文件名
CSV_FILENAME = "xiaohongshu_data.csv"
# =========================================

# 初始化 SDK 客户端 (指定使用国内域名 COZE_CN_BASE_URL)
coze = Coze(auth=TokenAuth(token=COZE_API_TOKEN), base_url=COZE_CN_BASE_URL)

# 用于存储所有结果的全局列表
final_results = []


def handle_workflow_iterator(stream: Stream[WorkflowEvent]):
    """处理工作流事件流的回调函数"""
    global final_results

    print("🌊 正在接收事件流...")

    for event in stream:
        # 1. 处理消息事件
        if event.event == WorkflowEventType.MESSAGE:
            msg = event.message

            # --- 🛠️ 智能识别逻辑 (不依赖 node_type，防止报错) ---
            content_json = {}
            try:
                # 尝试解析内容 JSON
                if msg.content:
                    content_json = json.loads(msg.content)
            except:
                pass

                # 检查特征：是一个字典，且包含 'output' 或 'data' 列表
            raw_list = None
            if isinstance(content_json, dict):
                # 优先找 output，其次找 data
                raw_list = content_json.get("output") or content_json.get("data")

            # 如果提取到了列表，说明这是结果节点
            if raw_list and isinstance(raw_list, list):
                # 安全获取节点名称 (仅用于显示日志)
                node_title = getattr(msg, 'node_title', '结果节点')
                print(f"✅ 在 [{node_title}] 中捕获到数据，正在解析...")

                # --- 二次反序列化 (关键步骤) ---
                # 列表里的每一项是 JSON 字符串，需要解包
                count_new = 0
                for item in raw_list:
                    # 情况 A: 它是字符串 (被 JSON.stringify 过的)
                    if isinstance(item, str):
                        try:
                            real_data = json.loads(item)
                            if isinstance(real_data, list):
                                final_results.extend(real_data)
                                count_new += len(real_data)
                        except:
                            pass
                    # 情况 B: 它是字典或列表 (未被 stringify)
                    elif isinstance(item, (dict, list)):
                        if isinstance(item, list):
                            final_results.extend(item)
                            count_new += len(item)
                        else:
                            final_results.append(item)
                            count_new += 1

                print(f"   - 成功提取 {count_new} 条新数据")

        # 2. 处理错误事件
        elif event.event == WorkflowEventType.ERROR:
            print(f"❌ 工作流报错: {event.error}")

        # 3. 处理中断事件
        elif event.event == WorkflowEventType.INTERRUPT:
            print("⏸️ 工作流中断，尝试恢复...")
            handle_workflow_iterator(
                coze.workflows.runs.resume(
                    workflow_id=WORKFLOW_ID,
                    event_id=event.interrupt.interrupt_data.event_id,
                    resume_data="hey",
                    interrupt_type=event.interrupt.interrupt_data.type,
                )
            )


def main():
    print(f"🚀 [SDK] 启动工作流，处理 {len(INPUT_KEYWORDS)} 个关键词...")

    # 调用流式运行接口
    try:
        handle_workflow_iterator(
            coze.workflows.runs.stream(
                workflow_id=WORKFLOW_ID,
                parameters={"input": INPUT_KEYWORDS}
            )
        )
    except Exception as e:
        print(f"❌ 运行过程中发生异常: {e}")

    # === 保存数据到 CSV ===
    if final_results:
        # 自动定位保存路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 尝试存到同级 data 目录，没有则存当前目录
        data_dir = os.path.join(current_dir, '..', 'data')
        if not os.path.exists(data_dir):
            data_dir = current_dir

        full_path = os.path.join(data_dir, CSV_FILENAME)

        try:
            # 获取表头
            headers = final_results[0].keys()

            with open(full_path, "w", newline='', encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(final_results)

            print("\n" + "=" * 40)
            print(f"🎉 任务完成！")
            print(f"📊 总共获取数据: {len(final_results)} 条")
            print(f"💾 文件已保存至: {full_path}")
            print("=" * 40)

        except Exception as e:
            print(f"❌ 保存文件失败: {e}")
    else:
        print("\n⚠️ 流程结束，未提取到有效数据 (final_results 为空)。")


if __name__ == "__main__":
    main()