# -*- coding: utf-8 -*-
"""基于 AgentScope 2.0 官方方式实现的 AI 问答服务."""
import os

import uvicorn
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Body
from pydantic import BaseModel
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

from agentscope.app import create_app
from agentscope.app.message_bus import RedisMessageBus
from agentscope.app.storage import RedisStorage
from agentscope.app.workspace_manager import LocalWorkspaceManager
from agentscope.tool import Toolkit, Bash
from agentscope.skill import LocalSkillLoader
from agentscope.agent import Agent
from agentscope.model import OpenAIChatModel
from agentscope.credential import OpenAICredential
from agentscope.message import UserMsg, Msg

# 技能配置路径
SKILL_CONFIG_PATH = "config/skill_config.yml"


def load_skills_from_config(config_path: str) -> dict:
    """从配置文件加载技能配置"""
    import yaml
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    tools = []
    skill_loaders = []
    
    for skill in config.get("skills", []):
        if "module" in skill and "function" in skill:
            import importlib
            module = importlib.import_module(skill["module"])
            func = getattr(module, skill["function"])
            tools.append(func)
        elif "directory" in skill:
            skill_loaders.append(skill["directory"])
    
    # 添加 Bash 工具（用于执行 curl 命令等）
    tools.append(Bash())
    
    return {
        "tools": tools,
        "skill_loaders": skill_loaders
    }


def create_custom_agent(toolkit: Toolkit):
    """创建自定义代理"""
    credential = OpenAICredential(api_key=os.getenv("OPENAI_API_KEY"))
    model = OpenAIChatModel(
        credential=credential,
        model="gpt-4o",
        stream=True,
        parameters=OpenAIChatModel.Parameters(temperature=0.3),
    )
    
    agent = Agent(
        name="AI问答助手",
        system_prompt="""你是一个智能助手，能够理解用户意图并调用相应的工具来完成任务。
        
        可用工具：
        1. bocha_search - 博查搜索：用于获取网上的最新知识和信息
        
        请根据用户的问题，判断是否需要调用工具：
        - 如果问题需要最新信息或实时数据，请调用搜索工具
        - 如果问题是常识性问题或不需要外部信息，可以直接回答
        
        请用自然、友好的语言回答用户的问题。""",
        model=model,
        toolkit=toolkit,
    )
    
    return agent


# 加载技能配置
skill_config = load_skills_from_config(SKILL_CONFIG_PATH)

# 创建 Toolkit
toolkit = Toolkit(
    tools=skill_config["tools"],
    skills_or_loaders=skill_config["skill_loaders"]
)

# 创建应用
app = create_app(
    # 使用 Redis 作为存储
    storage=RedisStorage(
        host="localhost",
        port=6379,
    ),
    message_bus=RedisMessageBus(
        host="localhost",
        port=6379,
    ),
    workspace_manager=LocalWorkspaceManager(
        basedir=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "workspaces",
        ),
    ),
    extra_middlewares=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        ),
    ],
)


# 定义请求模型
class ChatRequest(BaseModel):
    messages: list[dict] = []
    session_id: str = None
    user_id: str = None

# 添加自定义的 /chat 端点
@app.post("/chat")
async def chat(request: ChatRequest = Body(...)):
    """自定义聊天端点，支持流式响应"""
    messages = request.messages
    session_id = request.session_id
    user_id = request.user_id
    from fastapi.responses import StreamingResponse
    from typing import AsyncGenerator
    
    async def generate_response() -> AsyncGenerator[str, None]:
        agent = create_custom_agent(toolkit)
        
        msgs = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            
            if isinstance(content, list):
                text_content = "\n".join([c.get("text", "") for c in content if isinstance(c, dict)])
            else:
                text_content = str(content)
            
            if role == "user":
                msgs.append(UserMsg("用户", text_content))
            elif role == "assistant":
                msgs.append(Msg("AI问答助手", text_content, "assistant"))
        
        async for event in agent.reply_stream(msgs):
            if hasattr(event, 'text') and event.text:
                yield f"data: {event.text}\n\n"
            elif hasattr(event, 'content') and event.content:
                yield f"data: {event.content}\n\n"
        
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream"
    )


@app.get("/health")
async def health():
    """健康检查端点"""
    schemas = await toolkit.get_tool_schemas()
    return {"status": "healthy", "skills_loaded": len(schemas)}


@app.get("/skills")
async def list_skills():
    """列出已加载的技能"""
    schemas = await toolkit.get_tool_schemas()
    return {"skills": schemas}


if __name__ == "__main__":
    # 创建工作空间目录
    os.makedirs("workspaces", exist_ok=True)
    
    # 启动服务
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )