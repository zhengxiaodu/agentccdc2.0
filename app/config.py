import os
from dotenv import load_dotenv

load_dotenv()

SKILL_CONFIG_PATH = "config/skill_config.yml"
MODEL_CONFIG_PATH = "config/model_config.yml"

JWT_ALGORITHM = "HS256"
JWT_SECRET = os.getenv("JWT_SECRET", "please-change-this-secret")
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "8"))

# Redis 配置
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_SESSION_TTL = int(os.getenv("REDIS_SESSION_TTL", "86400"))