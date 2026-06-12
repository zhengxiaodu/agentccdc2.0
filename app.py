import os
import yaml
import importlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, AsyncGenerator

from agentscope.agent import Agent
from agentscope.model import OpenAIChatModel
from agentscope.tool import Toolkit, FunctionTool
from agentscope.message import UserMsg, Msg

SKILL_CONFIG_PATH = "config/skill_config.yml"

class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    session_id: str = None
    user_id: str = None

class ChatResponse(BaseModel):
    role: str
    content: str
    session_id: str = None

def load_skills(config_path: str) -> Toolkit:
    tools = []
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    for skill in config.get("skills", []):
        module_name = skill["module"]
        function_name = skill["function"]
        
        module = importlib.import_module(module_name)
        func = getattr(module, function_name)
        
        tool = FunctionTool(
            func=func,
            name=skill.get("name", function_name),
            description=skill.get("description", ""),
        )
        tools.append(tool)
    
    return Toolkit(tools=tools)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.toolkit = load_skills(SKILL_CONFIG_PATH)
    print("Skills loaded successfully")
    yield

app = FastAPI(lifespan=lifespan)

async def generate_response(
    messages: List[Dict[str, Any]],
    session_id: str = None,
    user_id: str = None
) -> AsyncGenerator[str, None]:
    toolkit = app.state.toolkit
    
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")
    
    model = OpenAIChatModel(
        model_name="gpt-4o",
        api_key=os.getenv("OPENAI_API_KEY"),
        stream=True,
        generate_kwargs={"temperature": 0.3},
    )
    
    agent = Agent(
        name="AI问答助手",
        system_prompt="""你是一个智能助手，能够理解用户意图并调用相应的工具来完成任务。
        
        可用工具：
        1. bocha_search - 博查搜索：用于获取网上的最新知识和信息
        
        请根据用户的问题，判断是否需要调用工具：
        - 如果问题需要最新信息或实时数据，请调用搜索工具
        - 如果问题是常识性问题或不需要外部信息，可以直接回答
        
        请用自然、友好的语言回答用户的问题。""",
        model=model,
        toolkit=toolkit,
    )
    
    agent.set_console_output_enabled(False)
    
    msgs = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        
        if isinstance(content, list):
            text_content = "\n".join([c.get("text", "") for c in content if isinstance(c, dict)])
        else:
            text_content = str(content)
        
        if role == "user":
            msgs.append(UserMsg(text_content))
        elif role == "assistant":
            msgs.append(Msg("AI问答助手", text_content, "assistant"))
    
    async for response in agent(msgs):
        if hasattr(response, 'content') and response.content:
            for block in response.content:
                if hasattr(block, 'text') and block.text:
                    yield f"data: {block.text}\n\n"
    
    yield "data: [DONE]\n\n"

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        return StreamingResponse(
            generate_response(
                messages=request.messages,
                session_id=request.session_id,
                user_id=request.user_id
            ),
            media_type="text/event-stream"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    if hasattr(app.state, 'toolkit'):
        schemas = await app.state.toolkit.get_tool_schemas()
        return {"status": "healthy", "skills_loaded": len(schemas)}
    return {"status": "healthy", "skills_loaded": 0}

@app.get("/skills")
async def list_skills():
    if not hasattr(app.state, 'toolkit'):
        raise HTTPException(status_code=500, detail="Skills not loaded")
    
    schemas = await app.state.toolkit.get_tool_schemas()
    return {"skills": schemas}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)