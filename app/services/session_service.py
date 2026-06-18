import uuid
from typing import Optional

from agentscope.state import AgentState

from app.dao.session_dao import SessionDAO
from app.models.session import SessionMeta, SessionMessage, SessionDetailResponse


class SessionService:
    """会话生命周期管理"""

    def __init__(self, dao: SessionDAO):
        self.dao = dao

    async def get_or_create_session(self, session_id: Optional[str], user_id: str) -> str:
        """获取已有 session_id 或创建新会话。"""
        if session_id and await self.dao.session_exists(session_id):
            return session_id
        return uuid.uuid4().hex

    async def load_agent_state(self, session_id: str) -> Optional[dict]:
        """从 Redis 加载 AgentState 原始数据。"""
        return await self.dao.load_agent_state(session_id)

    async def save_agent_state(self, session_id: str, user_id: str, state_dict: dict) -> None:
        """将 AgentState dict 持久化到 Redis。"""
        await self.dao.save_agent_state(session_id, user_id, state_dict)

    async def save_latest_trace_id(self, session_id: str, trace_id: str) -> None:
        """将最新 trace_id 保存到会话元信息。"""
        await self.dao.save_latest_trace_id(session_id, trace_id)

    async def list_user_sessions(self, user_id: str, limit: int = 15) -> list[SessionMeta]:
        """列出用户最近会话。"""
        raw_list = await self.dao.list_user_sessions(user_id, limit=limit)
        return [SessionMeta(**m) for m in raw_list]

    async def get_session_detail(
        self, session_id: str, user_id: str
    ) -> Optional[SessionDetailResponse]:
        """获取会话详情（含对话历史）。"""
        state = await self.dao.load_agent_state(session_id)
        if state is None:
            return None

        meta = await self.dao.get_session_meta(session_id)
        if meta is None:
            return None

        if meta.get("user_id") != user_id:
            raise PermissionError("会话不属于当前用户")

        raw_messages = self.dao.extract_messages_from_state(state)
        messages = [SessionMessage(**m) for m in raw_messages]

        return SessionDetailResponse(
            session_id=session_id,
            created_at=meta.get("created_at", ""),
            updated_at=meta.get("updated_at", ""),
            trace_id=meta.get("latest_trace_id"),
            messages=messages,
        )