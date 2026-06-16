from fastapi import APIRouter, HTTPException

from app.dao.user_dao import verify_login
from app.models.auth import LoginRequest, LoginResponse, UserInfo
from app.services.auth_service import create_access_token
from app.config import JWT_EXPIRE_HOURS

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    result = await verify_login(request.username, request.password)
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