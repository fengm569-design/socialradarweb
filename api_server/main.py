from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from cozepy import Coze, TokenAuth, Message, ChatEventType, COZE_CN_BASE_URL

# ================= 配置区 =================
# 使用你最新生成的国内版扣子令牌 (务必是 cztei_ 开头)
COZE_API_TOKEN = 'cztei_qg1hVwCgcnFfuSpP3MZLpwE8TpAtCRaf0rcr4BEyv67wPI05zSH6iPrdKHMj7LDAV'
BOT_ID = '7595410513413586950'

coze = Coze(auth=TokenAuth(token=COZE_API_TOKEN), base_url=COZE_CN_BASE_URL)
# =========================================

# 初始化 FastAPI 应用
app = FastAPI(title="Social Radar Agent API")

# 允许跨域请求（必须加，否则前端 HTML 无法调用本地端口）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 定义前端传过来的数据格式
class ChatRequest(BaseModel):
    user_message: str
    user_id: str = "web_user_001"


# 核心聊天接口
@app.post("/api/chat")
def chat_with_bot(request: ChatRequest):
    print(f"📡 收到用户消息: {request.user_message}")
    try:
        bot_reply = ""
        # 调用扣子流式接口
        for event in coze.chat.stream(
                bot_id=BOT_ID,
                user_id=request.user_id,
                additional_messages=[
                    Message.build_user_question_text(request.user_message),
                ],
        ):
            # 拼接机器人回复的内容
            if event.event == ChatEventType.CONVERSATION_MESSAGE_DELTA:
                bot_reply += event.message.content

        print(f"🤖 呆呆回复完成, 长度: {len(bot_reply)}")
        return {
            "status": "success",
            "reply": bot_reply
        }

    except Exception as e:
        print(f"❌ 请求扣子 API 发生错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # 启动服务器在 8000 端口
    uvicorn.run(app, host="0.0.0.0", port=8000)