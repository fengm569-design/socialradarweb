import os
import json
import csv
import re
import time
# 导入官方 SDK
from cozepy import Coze, TokenAuth, Stream, WorkflowEvent, WorkflowEventType, COZE_CN_BASE_URL

# ================= 配置区 =================
COZE_API_TOKEN = 'cztei_hLO8RsmuBFu94A3ksz3gYDQIRxak4qtqUSktwb9e0Bsimb4nz9brynEZpbKRUeIB4'
WORKFLOW_ID = '7603685878149660718'

INPUT_KEYWORDS = [
    "自动化学会", "王飞跃", "杨孟飞", "郑南宁",
    "高会军", "张承慧", "戴琼海",  "何友"
]

CSV_FILENAME = "xiaohongshu_data.csv"
# =========================================

coze = Coze(auth=TokenAuth(token=COZE_API_TOKEN), base_url=COZE_CN_BASE_URL)
final_results = []


def handle_workflow_iterator(stream: Stream[WorkflowEvent]):
    global final_results
    print("🌊 正在接收事件流...")

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

            print("✅ 捕获到输出数据，正在清洗并解析...")

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

                # =============== 核心容错与修复逻辑 ===============
                try:
                    parsed_list = json.loads(cleaned_str)
                    if isinstance(parsed_list, list):
                        final_results.extend(parsed_list)
                        print(f"   - 🟢 成功提取 {len(parsed_list)} 条新数据")

                except json.JSONDecodeError as e:
                    print(f"   ⚠️ 遇到不规范的 JSON，正在尝试自动修复...")
                    try:
                        fixed_str = re.sub(r',\s*([\]}])', r'\1', cleaned_str)
                        fixed_str = fixed_str.replace("'", '"')

                        parsed_list = json.loads(fixed_str)
                        if isinstance(parsed_list, list):
                            final_results.extend(parsed_list)
                            print(f"   - 🔧 自动修复成功！救回 {len(parsed_list)} 条数据")
                    except Exception as e2:
                        print(f"   ❌ 自动修复失败，此批次数据已损坏。")

                        # 定位报错位置
                        err_pos = getattr(e, 'pos', 0)
                        start = max(0, err_pos - 40)
                        end = min(len(cleaned_str), err_pos + 40)
                        print(f"   🔍 案发现场片段: \n>>> ...{cleaned_str[start:end]}... <<<")

                        # === 新增：保存完整的坏死数据，方便人工排查 ===
                        try:
                            with open("error_dump.txt", "a", encoding="utf-8") as ef:
                                ef.write(f"\n\n--- Error Timestamp: {time.strftime('%X')} ---\n")
                                ef.write(cleaned_str)
                            print(f"   💾 已将损坏的完整 JSON 文本保存到同目录下的 error_dump.txt 文件中。")
                        except:
                            pass
                # ===================================================

            elif isinstance(output_data, list):
                final_results.extend(output_data)
                print(f"   - 🟢 成功提取 {len(output_data)} 条新数据")

        elif event.event == WorkflowEventType.ERROR:
            print(f"❌ 工作流报错: {event.error}")

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
    print(f"🚀 [SDK] 启动批量处理模式，共 {len(INPUT_KEYWORDS)} 个关键词...")

    # ================= 修改点 =================
    # 将 BATCH_SIZE 改为 1，确保每次处理的数据量极小，绝不会触发 AI 输出截断
    BATCH_SIZE = 1
    # =========================================

    for i in range(0, len(INPUT_KEYWORDS), BATCH_SIZE):
        batch_keywords = INPUT_KEYWORDS[i: i + BATCH_SIZE]
        print("\n" + "-" * 50)
        print(f"📦 正在处理第 {i // BATCH_SIZE + 1}/{len(INPUT_KEYWORDS)} 批次: {batch_keywords}")
        print("-" * 50)

        try:
            handle_workflow_iterator(
                coze.workflows.runs.stream(
                    workflow_id=WORKFLOW_ID,
                    parameters={"input": batch_keywords}
                )
            )
        except Exception as e:
            print(f"❌ 本批次运行发生异常: {e}")

        # 增加休眠时间到 3 秒，防止扣子 API 判定请求过快 (Rate Limit)
        print("⏳ 休息 3 秒后继续...")
        time.sleep(3)

        # === 保存数据到 CSV ===
    if final_results:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(current_dir, '..', 'data')
        if not os.path.exists(data_dir):
            data_dir = current_dir

        full_path = os.path.join(data_dir, CSV_FILENAME)

        try:
            if isinstance(final_results[0], dict):
                headers = final_results[0].keys()
                with open(full_path, "w", newline='', encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(final_results)

                print("\n" + "=" * 50)
                print(f"🎉 全部批次任务圆满完成！")
                print(f"📊 累计获取过滤后的有效数据: {len(final_results)} 条")
                print(f"💾 文件已保存至: {full_path}")
                print("=" * 50)
            else:
                print("❌ 数据格式异常，无法保存为 CSV")
        except Exception as e:
            print(f"❌ 保存文件失败: {e}")
    else:
        print("\n⚠️ 所有流程结束，未提取到有效数据 (final_results 为空)。")


if __name__ == "__main__":
    main()
