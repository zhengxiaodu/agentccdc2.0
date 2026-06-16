from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.dependencies import current_user
from app.models.chat import ChatRequest
from app.services.chat_service import generate_response

router = APIRouter()


@router.post("/chat")
async def chat(request: Request, body: ChatRequest, user: dict = Depends(current_user)):
    try:
        return StreamingResponse(
            generate_response(
                toolkit=request.app.state.toolkit,
                model_config=request.app.state.model_config,
                messages=body.messages,
                session_id=body.session_id,
                user_id=user.get("user_id"),
            ),
            media_type="text/event-stream",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))