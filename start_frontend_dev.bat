@echo off
chcp 65001 >nul
cd /d "%~dp0app\frontend"
echo [环评AI知识库智能审查系统] 启动前端开发服务器 http://localhost:5173
npm run dev
pause