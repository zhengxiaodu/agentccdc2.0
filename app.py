import os
import yaml
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, AsyncGenerator

import jwt
import aiohttp

from agentscope.agent import Agent
from agentscope.model import OpenAIChatModel
from agentscope.credential import OpenAICredential
from agentscope.message import AssistantMsg, UserMsg
from agentscope.event import AgentEvent
from agentscope.workspace import LocalWorkspace
from agentscope.state import AgentState
from agentscope.permission import PermissionContext, PermissionMode
from agentscope.tool import Toolkit
from agentscope.event import (
    ReplyStartEvent,
    ReplyEndEvent
)

# 加载.env文件中的环境变量
load_dotenv()
SKILL_CONFIG_PATH = "config/skill_config.yml"
MODEL_CONFIG_PATH = "config/model_config.yml"

JWT_ALGORITHM = "HS256"
JWT_SECRET = os.getenv("JWT_SECRET", "please-change-this-secret")
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "8"))


class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    role: str
    content: str
    session_id: str = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    user_id: str
    user_name: str
    department: str
    role: str


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_in: int
    user_info: UserInfo
    agent_access: List[str]
    skills_blacklist: List[str]


# 模拟账号数据,生产环境应改为调用第三方管理系统的真实接口
_MOCK_USERS = {
    "zhangsan": {
        "password": "123456",
        "verification": True,
        "user_info": {"user_id": "123", "user_name": "小张", "department": "后勤部", "role": "普通用户"},
        "agent_access": ["制度问答"],
        "skills_blacklist": ["google"],
    },
    "admin": {
        "password": "123456",
        "verification": True,
        "user_info": {"user_id": "1", "user_name": "管理员", "department": "管理部", "role": "管理员"},
        "agent_access": ["制度问答", "通用问答"],
        "skills_blacklist": [],
    },
}


async def verify_login_with_external(username: str, password: str) -> dict:
    """调用第三方管理系统验证登录凭据。

    当 AUTH_MOCK=true 时使用内置模拟数据;否则请求 .env 中的 AUTH_API_URL。
    返回结构须为:
        {
            "verification": bool,
            "user_info": {"user_id", "user_name", "department", "role"},
            "agent_access": [...],
            "skills_blacklist": [...],
        }
    验证失败时仅返回 {"verification": False}。
    """
    if os.getenv("AUTH_MOCK", "true").lower() == "true":
        user = _MOCK_USERS.get(username)
        if user and user["password"] == password:
            return {
                "verification": True,
                "user_info": user["user_info"],
                "agent_access": user["agent_access"],
                "skills_blacklist": user["skills_blacklist"],
            }
        return {"verification": False}

    api_url = os.getenv("AUTH_API_URL")
    api_key = os.getenv("AUTH_API_KEY")
    if not api_url:
        return {"verification": False}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                json={"username": username, "password": password},
                headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"verification": False}
    except Exception as e:
        print(f"[auth] 调用第三方认证服务失败: {e}")
        return {"verification": False}


def create_access_token(payload: dict, expire_hours: int = JWT_EXPIRE_HOURS) -> str:
    """生成 JWT,默认按 .env 中 JWT_EXPIRE_HOURS 过期。"""
    now = datetime.now(timezone.utc)
    body = payload.copy()
    body["iat"] = int(now.timestamp())
    body["exp"] = int((now + timedelta(hours=expire_hours)).timestamp())
    return jwt.encode(body, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """解析 JWT;过期或签名错误时抛出 jwt 异常。"""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


async def current_user(authorization: Optional[str] = Header(None)) -> dict:
    """FastAPI 依赖:从 Authorization: Bearer <token> 解析当前用户。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少或无效的 Authorization 头")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期,请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="登录凭证无效")


def load_model_config(config_path: str) -> dict:
    """加载模型配置"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def load_skills(config_path: str) -> Toolkit:
    """加载技能配置，初始化Toolkit"""
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.toolkit = await load_skills(SKILL_CONFIG_PATH)
    app.state.model = load_model_config(MODEL_CONFIG_PATH)
    print("Skills & model_cfg loaded successfully")
    yield


app = FastAPI(lifespan=lifespan)


async def generate_response(
        messages: List[Dict[str, Any]],
        session_id: str = None,
        user_id: str = None
) -> AsyncGenerator[str, None]:
    toolkit = app.state.toolkit
    model_config = app.state.model

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")

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
        state=AgentState(
            permission_context=PermissionContext(
                mode=PermissionMode.BYPASS,
            )
        )

    )

    apply = None
    for msg in messages:
        content = msg.get("content", "")

        if isinstance(content, list):
            text_content = "\n".join([c.get("text", "") for c in content if isinstance(c, dict)])
        else:
            text_content = str(content)

        async for event in agent.reply_stream(UserMsg("user", text_content)):
            # 始终将事件追加到消息中
            if isinstance(event, ReplyStartEvent):
                apply = AssistantMsg(name=event.name, content=[], id=event.reply_id)
            elif isinstance(event, ReplyEndEvent):
                print(apply)

            if isinstance(event, AgentEvent):
                # 输出 AgentEvent 格式（与官方一致）
                apply.append_event(event)
                yield f"data: {event.model_dump_json()}\n\n"


@app.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    result = await verify_login_with_external(request.username, request.password)
    if not result.get("verification"):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user_info = result["user_info"]
    agent_access = result.get("agent_access", [])
    skills_blacklist = result.get("skills_blacklist", [])

    token_payload = {
        "user_id": user_info["user_id"],
        "user_name": user_info["user_name"],
        "department": user_info["department"],
        "role": user_info["role"],
        "agent_access": agent_access,
        "skills_blacklist": skills_blacklist,
    }
    token = create_access_token(token_payload)

    return LoginResponse(
        token=token,
        token_type="bearer",
        expires_in=JWT_EXPIRE_HOURS * 3600,
        user_info=user_info,
        agent_access=agent_access,
        skills_blacklist=skills_blacklist,
    )


@app.post("/chat")
async def chat(request: ChatRequest, user: dict = Depends(current_user)):
    try:
        return StreamingResponse(
            generate_response(
                messages=request.messages,
                session_id=request.session_id,
                user_id=user.get("user_id"),
            ),
            media_type="text/event-stream"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    if hasattr(app.state, 'toolkit'):
        schemas = await app.state.toolkit.get_tool_schemas()
        return {"status": "healthy", "skills_loaded": len(schemas)}
    return {"status": "healthy", "skills_loaded": 0}


@app.get("/skills")
async def list_skills():
    if not hasattr(app.state, 'toolkit'):
        raise HTTPException(status_code=500, detail="Skills not loaded")

    schemas = await app.state.toolkit.get_tool_schemas()
    return {"skills": schemas}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
