from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    toolkit = getattr(request.app.state, "toolkit", None)
    if toolkit:
        schemas = await toolkit.get_tool_schemas()
        return {"status": "healthy", "skills_loaded": len(schemas)}
    return {"status": "healthy", "skills_loaded": 0}


@router.get("/skills")
async def list_skills(request: Request):
    toolkit = getattr(request.app.state, "toolkit", None)
    if not toolkit:
        raise HTTPException(status_code=500, detail="Skills not loaded")

    schemas = await toolkit.get_tool_schemas()
    return {"skills": schemas}