import os
from dotenv import load_dotenv

load_dotenv()

SKILL_CONFIG_PATH = "config/skill_config.yml"
MODEL_CONFIG_PATH = "config/model_config.yml"

JWT_ALGORITHM = "HS256"
JWT_SECRET = os.getenv("JWT_SECRET", "please-change-this-secret")
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "8"))