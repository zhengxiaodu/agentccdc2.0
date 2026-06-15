# -*- coding: utf-8 -*-
"""基于 AgentScope 2.0 官方方式实现的 AI 问答服务."""
import os
import yaml

import uvicorn
from fastapi import FastAPI, Body, HTTPException, Header
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

from agentscope.app import create_app
from agentscope.app.message_bus import RedisMessageBus
from agentscope.app.storage import RedisStorage
from agentscope.app.workspace_manager import LocalWorkspaceManager
from agentscope.tool import Toolkit, Bash
from agentscope.agent import Agent
from agentscope.model import OpenAIChatModel, DashScopeChatModel
from agentscope.credential import OpenAICredential, DashScopeCredential
from agentscope.message import UserMsg, Msg
from agentscope.event import AgentEvent

# 配置文件路径
MODEL_CONFIG_PATH = "config/model_config.yml"
SKILL_CONFIG_PATH = "config/skill_config.yml"


def load_model_config(config_path: str) -> dict:
    """加载模型配置"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_skills_from_config(config_path: str) -> dict:
    """从配置文件加载技能配置"""
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


def create_model_from_config(model_config: dict):
    """根据配置创建模型实例"""
    provider = model_config.get("provider", "openai")
    model_name = model_config.get("model_name", "gpt-4o")
    api_key_env = model_config.get("api_key_env", "OPENAI_API_KEY")
    parameters = model_config.get("parameters", {})
    
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise ValueError(f"环境变量 {api_key_env} 未设置")
    
    if provider == "openai":
        credential = OpenAICredential(api_key=api_key)
        model = OpenAIChatModel(
            credential=credential,
            model=model_name,
            stream=True,
            parameters=OpenAIChatModel.Parameters(**parameters),
        )
    elif provider == "dashscope":
        credential = DashScopeCredential(api_key=api_key)
        model = DashScopeChatModel(
            credential=credential,
            model=model_name,
            stream=True,
            parameters=DashScopeChatModel.Parameters(**parameters),
        )
    else:
        raise ValueError(f"不支持的 provider: {provider}")
    
    return model


# 加载配置
model_config = load_model_config(MODEL_CONFIG_PATH)
skill_config = load_skills_from_config(SKILL_CONFIG_PATH)

# 创建 Toolkit
toolkit = Toolkit(
    tools=skill_config["tools"],
    skills_or_loaders=skill_config["skill_loaders"]
)

# 创建应用（使用官方方式）
app = create_app(
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


# 定义请求模型（复用官方 chat 接口格式）
class ChatInput(BaseModel):
    """用户输入消息"""
    name: str = "用户"
    role: str = "user"
    content: list[dict]


class ChatRequest(BaseModel):
    """Chat 请求模型（复用官方格式）"""
    agent_id: str = "default_agent"
    session_id: str = None
    input: ChatInput


@app.post("/chat")
async def chat(
    request: ChatRequest = Body(...),
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """
    触发一次 chat 运行（复用官方接口格式）
    模型和技能均从配置文件获取，不通过接口配置
    """
    # 获取默认模型配置
    model_cfg = model_config.get("models", {}).get("default", {})
    agent_cfg = model_config.get("agent", {})
    
    # 创建模型实例
    model = create_model_from_config(model_cfg)
    
    # 创建 Agent
    agent = Agent(
        name=agent_cfg.get("name", "AI问答助手"),
        system_prompt=agent_cfg.get("system_prompt", ""),
        model=model,
        toolkit=toolkit,
    )
    
    # 解析用户输入
    user_input = request.input
    content_text = ""
    for item in user_input.content:
        if isinstance(item, dict) and item.get("type") == "text":
            content_text += item.get("text", "") + "\n"
    
    # 构建消息
    msgs = [UserMsg(user_input.name, content_text.strip())]
    
    # 流式响应生成
    async def generate_response():
        async for event in agent.reply_stream(msgs):
            if isinstance(event, AgentEvent):
                # 输出 AgentEvent 格式（与官方一致）
                yield f"data: {event.model_dump_json()}\n\n"
            elif hasattr(event, 'text') and event.text:
                # 兼容旧格式
                event_dict = {"type": "message", "text": event.text}
                yield f"data: {yaml.dump(event_dict)}\n\n"
            elif hasattr(event, 'content') and event.content:
                event_dict = {"type": "message", "text": str(event.content)}
                yield f"data: {yaml.dump(event_dict)}\n\n"
        
        # 发送结束标记
        yield "data: {\"type\": \"end\"}\n\n"
    
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


@app.get("/config/model")
async def get_model_config():
    """获取当前模型配置（只读，不允许修改）"""
    return model_config


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