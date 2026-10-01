"""FastAPI 入口：审核接口 + 前端静态托管。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .audit_service import TOPIC_LABELS, audit
from .config import PROJECT_ROOT, settings
from .parsers import SUPPORTED_EXT, extract_text
from .schemas import AuditRequest, AuditResult

app = FastAPI(title="环评AI知识库智能审查系统", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.FRONTEND_ORIGIN == "*" else [settings.FRONTEND_ORIGIN],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mock_mode": settings.effective_mode,
        "api_configured": settings.api_configured,
        "model": settings.LLM_MODEL,
        "embedding_model": settings.EMBEDDING_MODEL,
    }


@app.get("/api/topics")
def topics():
    return [{"key": k, "label": v} for k, v in TOPIC_LABELS.items()]


@app.post("/api/audit", response_model=AuditResult)
def audit_text(req: AuditRequest):
    text = (req.text or "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"detail": "文本为空"})
    return audit(text, req.topic, req.top_k)


@app.post("/api/audit/upload", response_model=AuditResult)
async def audit_upload(
    file: UploadFile = File(...),
    topic: str = Form("emission_standards"),
    top_k: int = Form(5),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXT:
        return JSONResponse(
            status_code=400,
            content={"detail": f"不支持的文件类型 {suffix}，仅支持: {', '.join(sorted(SUPPORTED_EXT))}"},
        )
    data = await file.read()
    text = extract_text(file.filename, data)
    if not text.strip():
        return JSONResponse(status_code=400, content={"detail": "未能从文件中提取到文本"})
    return audit(text, topic, top_k)


# 前端静态托管（若已构建）
_DIST = PROJECT_ROOT / "app" / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.BACKEND_PORT, reload=False)