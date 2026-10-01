@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [环评AI知识库智能审查系统] 启动后端 http://0.0.0.0:8000
python -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8000
pause