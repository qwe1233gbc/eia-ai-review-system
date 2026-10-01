@echo off
chcp 65001 >nul
cd /d "%~dp0app\frontend"
echo [环评AI知识库智能审查系统] 构建前端（产物输出到 app\frontend\dist）
if not exist node_modules (
  echo 首次构建，先安装依赖...
  call npm install
)
call npm run build
echo 构建完成。之后只需启动后端 start_backend.bat，即可通过单端口 http://localhost:8000 访问。
pause