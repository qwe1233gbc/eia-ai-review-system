# ===== 阶段1：构建前端 =====
FROM node:20-alpine AS fe
WORKDIR /fe
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm install
COPY app/frontend ./
RUN npm run build

# ===== 阶段2：Python 运行时 =====
FROM python:3.11-slim
WORKDIR /code

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app
COPY --from=fe /fe/dist ./app/frontend/dist

# 精简后的检索索引（3 文件，约 46MB）
ENV VECTOR_DB_PATH=/code/app/deploy/kb_slim

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]