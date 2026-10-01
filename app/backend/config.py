"""应用配置：从 .env 读取，含 Mock 模式开关与安全默认值。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（app/ 的上一级，即"环评审核幻觉实验"）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 优先加载项目根的 .env
load_dotenv(PROJECT_ROOT / ".env")


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _bool(key: str, default: bool = False) -> bool:
    val = _get(key, "").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


class Settings:
    # ---- 运行模式 ----
    MOCK_MODE: bool = _bool("MOCK_MODE", True)

    # ---- 大模型（OpenAI 兼容 /chat/completions）----
    LLM_API_KEY: str = _get("LLM_API_KEY", _get("DASHSCOPE_API_KEY", ""))
    LLM_BASE_URL: str = _get(
        "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ).rstrip("/")
    LLM_MODEL: str = _get("LLM_MODEL", "qwen3-32b")

    # ---- Embedding ----
    EMBEDDING_API_KEY: str = _get("EMBEDDING_API_KEY", "") or LLM_API_KEY
    EMBEDDING_BASE_URL: str = _get("EMBEDDING_BASE_URL", LLM_BASE_URL).rstrip("/")
    EMBEDDING_MODEL: str = _get("EMBEDDING_MODEL", "text-embedding-v4")

    # ---- 向量库 / 检索索引 ----
    VECTOR_DB_PATH: str = _get(
        "VECTOR_DB_PATH",
        str(PROJECT_ROOT / "03_知识库" / "05_检索索引_六文件"),
    )

    # ---- 服务 ----
    BACKEND_PORT: int = int(_get("BACKEND_PORT", "8000") or "8000")
    FRONTEND_ORIGIN: str = _get("FRONTEND_ORIGIN", "*")

    # ---- 知识库（供检索命中后展示元数据，实际索引由 VECTOR_DB_PATH 提供）----
    KB_ROOT: str = str(PROJECT_ROOT / "03_知识库")

    # 可选数据库（当前未使用，预留）
    DATABASE_URL: str = _get("DATABASE_URL", "")

    @property
    def api_configured(self) -> bool:
        """判断是否已配置真实 API（否则强制走 Mock）。"""
        return bool(self.LLM_API_KEY)

    @property
    def effective_mode(self) -> bool:
        """是否实际启用 Mock：显式 MOCK_MODE=true 或未配置 API Key 时。"""
        return self.MOCK_MODE or not self.api_configured


settings = Settings()