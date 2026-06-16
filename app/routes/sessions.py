from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import current_user

router = APIRouter()


def _get_session_service(request: Request):
    return request.app.state.session_service


@router.get("/sessions")
async def list_sessions(
    request: Request,
    user: dict = Depends(current_user),
):
    service = _get_session_service(request)
    sessions = await service.list_user_sessions(user.get("user_id"), limit=15)
    return {"sessions": [s.model_dump(mode="json") for s in sessions]}


@router.get("/sessions/{session_id}")
async def get_session_detail(
    session_id: str,
    request: Request,
    user: dict = Depends(current_user),
):
    service = _get_session_service(request)
    try:
        detail = await service.get_session_detail(session_id, user.get("user_id"))
    except PermissionError:
        raise HTTPException(status_code=403, detail="会话不属于当前用户")

    if detail is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    return detail.model_dump(mode="json")