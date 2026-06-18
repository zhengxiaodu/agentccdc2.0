import json
import os
import yaml

from agentscope.agent import Agent
from agentscope.model import OpenAIChatModel
from agentscope.credential import OpenAICredential
from agentscope.message import UserMsg, AssistantMsg, TextBlock, DataBlock
from agentscope.event import AgentEvent, ReplyStartEvent, ReplyEndEvent
from agentscope.workspace import LocalWorkspace
from agentscope.state import AgentState
from agentscope.permission import PermissionContext, PermissionMode
from agentscope.tool import Toolkit

from app.config import SKILL_CONFIG_PATH, MODEL_CONFIG_PATH
from app.services.langfuse_service import LangfuseService
from fastapi import HTTPException
from typing import List, Dict, Any, AsyncGenerator


def load_model_config(config_path: str = MODEL_CONFIG_PATH) -> dict:
    """加载模型配置"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def load_skills(config_path: str = SKILL_CONFIG_PATH) -> Toolkit:
    """加载技能配置, 初始化 Toolkit"""
    skill_loaders = []

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    for skill in config.get("skills", []):
        skill_loaders.append(skill["directory"])

    workspace = LocalWorkspace(
        workdir="./my-workspace",
        default_mcps=[],
        skill_paths=skill_loaders,
    )
    await workspace.initialize()

    return Toolkit(tools=await workspace.list_tools(), skills_or_loaders=await workspace.list_skills())


def create_model_from_config(model_config: dict):
    """根据配置创建模型实例"""
    provider = model_config.get("provider", "openai")
    base_url = model_config.get("base_url", "https://api.deepseek.com/v1")
    model_name = model_config.get("model_name", "deepseek-chat")
    api_key = model_config.get("api_key", "OPENAI_API_KEY")
    parameters = model_config.get("parameters", {})

    if not api_key:
        raise ValueError(f"环境变量未设置")

    if provider == "openai":
        credential = OpenAICredential(api_key=api_key, base_url=base_url)
        model = OpenAIChatModel(
            credential=credential,
            model=model_name,
            stream=True,
            parameters=OpenAIChatModel.Parameters(**parameters),
        )
    else:
        raise ValueError(f"不支持的 provider: {provider}")

    return model


async def generate_response(
    toolkit: Toolkit,
    model_config: dict,
    messages: List[Dict[str, Any]],
    session_id: str = None,
    user_id: str = None,
    session_service=None,
    langfuse_service: LangfuseService = None,
) -> AsyncGenerator[str, None]:
    """根据消息列表生成流式回复，集成 session 状态管理和 Langfuse 追踪。"""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")

    model_cfg = model_config.get("models", {}).get("default", {})
    agent_cfg = model_config.get("agent", {})
    model = create_model_from_config(model_cfg)

    # 从 Redis 恢复 AgentState（若存在）
    agent_state = AgentState(
        session_id=session_id,
        permission_context=PermissionContext(mode=PermissionMode.BYPASS),
    )
    if session_service and session_id:
        loaded = await session_service.load_agent_state(session_id)
        if loaded:
            # 用加载的状态重建 AgentState（会覆盖 session_id, context, summary 等）
            agent_state = AgentState(**loaded)

    agent = Agent(
        name=agent_cfg.get("name", "AI问答助手"),
        system_prompt=agent_cfg.get("system_prompt", ""),
        model=model,
        toolkit=toolkit,
        state=agent_state,
    )

    # 创建 Langfuse trace（若已启用）
    trace = None
    if langfuse_service and langfuse_service.enabled:
        trace = langfuse_service.create_trace(
            session_id=session_id,
            user_id=user_id,
            input={
                "messages": messages,
                "session_id": session_id,
                "user_id": user_id,
            },
        )

    apply = None
    for msg in messages:
        content = msg.get("content", "")

        if isinstance(content, list):
            blocks = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    blocks.append(TextBlock(text=block.get("text", "")))
                elif block_type == "data":
                    blocks.append(DataBlock.model_validate(block))
            user_msg = UserMsg(name="user", content=blocks)
        else:
            user_msg = UserMsg("user", str(content))

        async for event in agent.reply_stream(user_msg):
            if isinstance(event, ReplyStartEvent):
                apply = AssistantMsg(name=event.name, content=[], id=event.reply_id)
            elif isinstance(event, ReplyEndEvent):
                print(apply)

            if isinstance(event, AgentEvent):
                apply.append_event(event)
                yield f"data: {event.model_dump_json()}\n\n"

    # 流结束后持久化状态
    if session_service and session_id and user_id:
        state_data = agent.state.model_dump(mode="json")
        await session_service.save_agent_state(session_id, user_id, state_data)

    # 更新 Langfuse trace 并发送 TRACE_READY 事件
    if trace and langfuse_service:
        try:
            tool_calls = []
            if apply:
                for block in apply.content:
                    if block.type == "tool_call":
                        tool_calls.append({
                            "name": block.name,
                            "input": block.input,
                            "state": str(block.state),
                        })

            trace_output = {
                "reply": apply.model_dump(mode="json") if apply else None,
                "tool_calls": tool_calls,
                "token_usage": apply.usage.model_dump() if apply and apply.usage else None,
            }
            langfuse_service.update_trace(trace, output=trace_output)
            langfuse_service.flush()
        except Exception:
            pass

        trace_id = str(trace.id) if trace.id else None
    else:
        trace_id = None

    trace_event = json.dumps({"type": "trace_ready", "trace_id": trace_id})
    yield f"data: {trace_event}\n\n"