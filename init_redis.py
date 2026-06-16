# -*- coding: utf-8 -*-
"""初始化 Redis 中 AgentScope 的默认记录。

使用方式:
    python3 init_redis.py
    
预填充的数据:
    - credential: 从 .env 读取 API key 创建
    - agent: 从 config/model_config.yml 读取配置创建
    - session: 绑定到 credential 和 agent 的默认会话
"""
import asyncio
import os
import sys
import yaml

from dotenv import load_dotenv

load_dotenv()

from agentscope.app.storage import RedisStorage
from agentscope.app.storage._model import (
    AgentRecord,
    AgentData,
    SessionConfig,
    ChatModelConfig,
)
from agentscope.agent import ContextConfig, ReActConfig
from agentscope.credential import OpenAICredential


MODEL_CONFIG_PATH = "config/model_config.yml"
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


async def init_defaults():
    """预填充默认的 credential、agent、session 记录到 Redis。"""
    storage = RedisStorage(host=REDIS_HOST, port=REDIS_PORT)
    await storage.__aenter__()
    try:
        # 检查是否已经初始化
        existing = await storage.list_agents("default")
        if existing:
            print("=> Redis already initialized, skipping.")
            return

        # 1. 在 model_config.yml 中配置的 API key 环境变量名
        with open(MODEL_CONFIG_PATH, encoding="utf-8") as f:
            model_config = yaml.safe_load(f)

        model_cfg = model_config.get("models", {}).get("default", {})
        agent_cfg = model_config.get("agent", {})

        # 2. 创建 credential 记录
        api_key_env = model_cfg.get("api_key_env", "OPENAI_API_KEY")
        api_key = os.getenv(api_key_env)
        if not api_key:
            print(
                f"ERROR: env var {api_key_env} not set. "
                f"Check .env file.",
            )
            sys.exit(1)

        credential = OpenAICredential(api_key=api_key)
        cred_id = await storage.upsert_credential("default", credential)
        print(f"  - credential: {cred_id}")

        # 3. 创建 agent 记录
        agent_record = AgentRecord(
            id="default_agent",
            user_id="default",
            data=AgentData(
                name=agent_cfg.get("name", "AI问答助手"),
                system_prompt=agent_cfg.get("system_prompt", ""),
                context_config=ContextConfig(),
                react_config=ReActConfig(max_iters=20),
            ),
        )
        await storage.upsert_agent("default", agent_record)
        print(f"  - agent: default_agent")

        # 4. 创建 session 记录，绑定模型配置到 credential
        session = await storage.upsert_session(
            user_id="default",
            agent_id="default_agent",
            config=SessionConfig(
                workspace_id="default",
                chat_model_config=ChatModelConfig(
                    type="openai_credential",
                    credential_id=cred_id,
                    model=model_cfg.get("model_name", "gpt-4o"),
                    parameters=model_cfg.get("parameters", {}),
                ),
            ),
        )
        print(f"  - session: {session.id}")

        print("\n=> Redis initialized successfully!")
        print("=> Use agent_id='default_agent' and the session_id above to chat.\n")

    finally:
        await storage.__aexit__(None, None, None)


if __name__ == "__main__":
    print("Initializing Redis with default AgentScope records...\n")
    asyncio.run(init_defaults())