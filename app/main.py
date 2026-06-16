import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import SKILL_CONFIG_PATH, MODEL_CONFIG_PATH
from app.services.chat_service import load_skills, load_model_config
from app.routes import auth, chat, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.toolkit = await load_skills(SKILL_CONFIG_PATH)
    app.state.model_config = load_model_config(MODEL_CONFIG_PATH)
    print("Skills & model_cfg loaded successfully")
    yield


app = FastAPI(lifespan=lifespan)

app.include_router(auth.router, tags=["auth"])
app.include_router(chat.router, tags=["chat"])
app.include_router(health.router, tags=["health"])

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)