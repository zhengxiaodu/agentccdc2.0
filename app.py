# -*- coding: utf-8 -*-
"""基于 AgentScope 2.0 官方的 agent_service 实现的 AI 问答服务。

核心原则：
1. 复用官方 create_app 的所有内置路由（chat、session、agent、credential 等）
2. 大模型配置从 config/model_config.yml 读取（不通过 API 配置）
3. 博查 skill 从 config/skill_config.yml 读取（不通过 API 配置）
4. Redis 存储数据结构与官方完全一致
"""
import os

import yaml
import uvicorn
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request, HTTPException
from dotenv import load_dotenv

load_dotenv()

from agentscope.app import create_app
from agentscope.app.storage import RedisStorage
from agentscope.app.message_bus import RedisMessageBus
from agentscope.app.workspace_manager import LocalWorkspaceManager
from agentscope.tool import ToolBase

# ---------------------------------------------------------------------------
# 配置路径
# ---------------------------------------------------------------------------
MODEL_CONFIG_PATH = "config/model_config.yml"
SKILL_CONFIG_PATH = "config/skill_config.yml"

# ---------------------------------------------------------------------------
# 加载配置文件
# ---------------------------------------------------------------------------
with open(MODEL_CONFIG_PATH, encoding="utf-8") as f:
    model_config = yaml.safe_load(f)

with open(SKILL_CONFIG_PATH, encoding="utf-8") as f:
    skill_config = yaml.safe_load(f)

# ---------------------------------------------------------------------------
# 从 skill_config.yml 构建工具列表
# ---------------------------------------------------------------------------
_skill_tools: list[ToolBase] = []

for skill in skill_config.get("skills", []):
    name = skill.get("name", "")
    # 方式1: module/function 格式
    if "module" in skill and "function" in skill:
        import importlib

        module = importlib.import_module(skill["module"])
        func = getattr(module, skill["function"])
        if isinstance(func, ToolBase):
            _skill_tools.append(func)
        elif hasattr(func, "__call__"):
            _skill_tools.append(func)
    # 方式2: directory 格式 —— 从目录中的 .py 文件加载 ToolBase 实例
    elif "directory" in skill:
        import importlib.util

        skill_dir = skill["directory"]
        if not os.path.isabs(skill_dir):
            skill_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                skill_dir,
            )
        for fname in sorted(os.listdir(skill_dir)):
            if fname.endswith(".py") and not fname.startswith("__"):
                mod_path = os.path.join(skill_dir, fname)
                mod_name = f"skill_{name}_{fname[:-3]}"
                spec = importlib.util.spec_from_file_location(
                    mod_name,
                    mod_path,
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    # 收集模块中所有 ToolBase 实例
                    for attr_name in dir(mod):
                        attr = getattr(mod, attr_name)
                        if isinstance(attr, ToolBase):
                            _skill_tools.append(attr)
    else:
        print(f"  [WARN] skill '{name}' has unknown format (neither module/function nor directory), skipped.")


async def extra_agent_tools_factory(
    user_id: str,
    agent_id: str,
    session_id: str,
) -> list[ToolBase]:
    """每次组装智能体时被调用，返回需要注入的额外工具。"""
    return _skill_tools


# ---------------------------------------------------------------------------
# 基础设施 —— 存储、消息总线、工作区管理器
# ---------------------------------------------------------------------------
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

storage = RedisStorage(host=REDIS_HOST, port=REDIS_PORT)
message_bus = RedisMessageBus(host=REDIS_HOST, port=REDIS_PORT)
workspace_manager = LocalWorkspaceManager(
    basedir=os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "workspaces",
    ),
)

# ---------------------------------------------------------------------------
# 创建 FastAPI 应用（使用官方 create_app）
# 包含所有内置路由：
#   POST /chat         触发一次 chat 运行
#   GET  /sessions/{id}/stream  SSE 事件流
#   GET/POST/PATCH/DELETE /agent, /sessions, /credential, /schedule, ...
# ---------------------------------------------------------------------------
app = create_app(
    storage=storage,
    message_bus=message_bus,
    workspace_manager=workspace_manager,
    extra_agent_tools=extra_agent_tools_factory,
    extra_middlewares=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        ),
    ],
)


# ---------------------------------------------------------------------------
# 自定义端点：健康检查
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    """健康检查。"""
    return {"status": "healthy"}


# ---------------------------------------------------------------------------
# 自定义端点：查看当前配置（只读）
# ---------------------------------------------------------------------------
@app.get("/config")
async def get_config():
    """返回当前模型配置和技能配置（只读，不能通过 API 修改）。"""
    return {
        "model": model_config,
        "skills": skill_config,
    }


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    os.makedirs("workspaces", exist_ok=True)

    print(
        "=" * 60,
        "AI 问答服务 - AgentScope 2.0",
        "=" * 60,
        sep="\n",
    )
    print()
    print("服务端 API 端点：")
    print("  POST /chat              触发聊天会话")
    print("  GET  /sessions/{id}/stream  SSE 事件流")
    print("  GET  /health            健康检查")
    print("  GET  /config            查看配置")
    print()
    print("使用前请先运行:  python3 init_redis.py")
    print()

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )