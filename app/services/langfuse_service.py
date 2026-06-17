import logging
from typing import Any, Optional

from app.config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

logger = logging.getLogger(__name__)


class LangfuseService:
    def __init__(self) -> None:
        self._enabled = False
        self._client = None

        if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
            self._try_init()

    def _try_init(self) -> None:
        try:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=LANGFUSE_PUBLIC_KEY,
                secret_key=LANGFUSE_SECRET_KEY,
                host=LANGFUSE_HOST,
            )
            self._enabled = True
            logger.info("Langfuse client initialized (host: %s)", LANGFUSE_HOST)
        except Exception as e:
            logger.warning("Failed to initialize Langfuse client: %s", e)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def create_trace(
        self,
        name: str = "chat-response",
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        input: Any = None,
    ):
        if not self._enabled or not self._client:
            return None
        try:
            return self._client.trace(
                name=name,
                session_id=session_id,
                user_id=user_id,
                input=input,
            )
        except Exception as e:
            logger.warning("Langfuse create_trace failed: %s", e)
            self._enabled = False
            return None

    def update_trace(
        self,
        trace,
        output: Any = None,
        input: Any = None,
    ) -> None:
        if not self._enabled or not trace:
            return
        try:
            trace.update(output=output, input=input)
        except Exception as e:
            logger.warning("Langfuse update_trace failed: %s", e)

    def flush(self) -> None:
        if not self._enabled or not self._client:
            return
        try:
            self._client.flush()
        except Exception as e:
            logger.warning("Langfuse flush failed: %s", e)