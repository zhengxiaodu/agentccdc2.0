from fastapi import APIRouter, HTTPException
import httpx

from app.config import MNG_URL

router = APIRouter()


@router.get("/ui/presentation/cards")
async def proxy_card_configs():
    if not MNG_URL:
        raise HTTPException(status_code=500, detail="MNG_URL not configured")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{MNG_URL}/ui/presentation/cards")
        return resp.json()


@router.get("/ui/presentation/custom-components")
async def proxy_custom_component_configs():
    if not MNG_URL:
        raise HTTPException(status_code=500, detail="MNG_URL not configured")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{MNG_URL}/ui/presentation/custom-components")
        return resp.json()