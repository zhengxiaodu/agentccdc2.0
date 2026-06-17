import json
import time
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from app.config import REDIS_SESSION_TTL


class SessionDAO:
    """Redis 会话持久化数据访问层"""

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.ttl = REDIS_SESSION_TTL

    # ---- Key helpers ----

    @staticmethod
    def _state_key(session_id: str) -> str:
        return f"session:{session_id}"

    @staticmethod
    def _meta_key(session_id: str) -> str:
        return f"session_meta:{session_id}"

    @staticmethod
    def _user_sessions_key(user_id: str) -> str:
        return f"user_sessions:{user_id}"

    # ---- Agent state ----

    async def save_agent_state(self, session_id: str, user_id: str, state_dict: dict) -> None:
        """保存 agent state 到 Redis，并更新元信息和用户会话有序集合。"""
        now = datetime.now(timezone.utc)
        now_ts = int(now.timestamp())
        now_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # 1) 保存 agent state
        state_json = json.dumps(state_dict, ensure_ascii=False, default=str)
        await self.redis.setex(self._state_key(session_id), self.ttl, state_json)

        # 2) 从当前 state 中提取消息数量
        current_msgs = self.extract_messages_from_state(state_dict)
        message_count = len(current_msgs)

        # 3) 更新元信息（created_at 仅在首次设值）
        existed = await self.redis.get(self._meta_key(session_id))
        if existed:
            existed_meta = json.loads(existed)
            created_at = existed_meta.get("created_at", now_str)
        else:
            created_at = now_str

        meta = {
            "user_id": user_id,
            "created_at": created_at,
            "updated_at": now_str,
            "message_count": message_count,
        }

        await self.redis.setex(self._meta_key(session_id), self.ttl, json.dumps(meta, ensure_ascii=False))

        # 4) 更新用户会话有序集合（按更新时间排序）
        await self.redis.zadd(self._user_sessions_key(user_id), {session_id: now_ts})
        await self.redis.expire(self._user_sessions_key(user_id), self.ttl)

    async def load_agent_state(self, session_id: str) -> Optional[dict]:
        """从 Redis 加载 agent state dict。"""
        raw = await self.redis.get(self._state_key(session_id))
        if raw is None:
            return None
        return json.loads(raw)

    # ---- Session meta ----

    async def session_exists(self, session_id: str) -> bool:
        """检查 session 是否存在。"""
        return await self.redis.exists(self._state_key(session_id)) > 0

    async def get_session_meta(self, session_id: str) -> Optional[dict]:
        """获取会话元信息。"""
        raw = await self.redis.get(self._meta_key(session_id))
        if raw is None:
            return None
        meta = json.loads(raw)
        meta["session_id"] = session_id
        # 从 state 中提取消息数量补充 message_count
        if "message_count" not in meta or meta.get("message_count", 0) == 0:
            state = await self.load_agent_state(session_id)
            if state:
                msgs = self.extract_messages_from_state(state)
                meta["message_count"] = len(msgs)
        return meta

    async def list_user_sessions(self, user_id: str, limit: int = 15) -> list[dict]:
        """获取用户最近 N 条会话列表。"""
        session_ids = await self.redis.zrevrange(
            self._user_sessions_key(user_id),
            0,
            limit - 1,
        )
        results = []
        for sid in session_ids:
            sid_str = sid.decode("utf-8") if isinstance(sid, bytes) else sid
            meta = await self.get_session_meta(sid_str)
            if meta:
                results.append(meta)
        return results

    # ---- Conversation history ----

    @staticmethod
    def extract_messages_from_state(state_dict: dict) -> list[dict]:
        """从 agent state dict（AgentState.model_dump()）中提取对话消息列表。

        AgentState 结构:
            { session_id, summary, context: [Msg_dict, ...],
              reply_id, cur_iter, permission_context, tool_context, tasks_context }

        Msg_dict 结构:
            { name, content: [block, ...], role, id, metadata, created_at, finished_at, usage }

        返回 [{"role": "user"/"assistant", "content": str, "timestamp": str}, ...]
        """
        messages = []
        try:
            context = state_dict.get("context", [])
            for msg in context:
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role", "")
                raw_content = msg.get("content", "")
                ts = msg.get("created_at", "")

                # 提取文本内容（content 可能是 string 或 list of blocks）
                if isinstance(raw_content, list):
                    text_parts = []
                    for block in raw_content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_part = block.get("text", "")
                            if text_part:
                                text_parts.append(text_part)
                    content_text = "\n".join(text_parts)
                else:
                    content_text = str(raw_content)

                if role in ("user", "assistant") and content_text:
                    messages.append({
                        "role": role,
                        "content": content_text,
                        "timestamp": ts,
                    })
        except Exception as e:
            print(f"[session_dao] extract_messages error: {e}")
        return messages