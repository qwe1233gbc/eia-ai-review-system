# 环评AI知识库智能审查系统 · 应用说明

> 基于本地已有实验资产（知识库 + FAISS/BM25 检索索引 + 大模型调用经验）新建的前后端分离应用。
> 起步主题：**排放标准准确性**（污染物排放控制标准核查）。

## 一、架构

```
浏览器(Vue3)
   │  HTTP
   ▼
FastAPI 后端 (app/backend)
   ├─ parsers.py     文本解析（TXT/MD/DOCX/PDF）
   ├─ retrieval.py   FAISS(余弦) + BM25 融合检索（复用已冻结的"检索索引_六文件"）
   ├─ llm_client.py  OpenAI 兼容接口（LLM function calling + text-embedding-v4 向量化）
   ├─ audit_service.py  审核编排：报告 → 检索 → LLM → 结构化结果
   └─ main.py        路由 / 静态托管（前端构建产物）
```

核心流程：**上传报告 → 解析 → 检索知识库 → 调用大模型 → 结构化审查结果（问题/依据/风险等级/修改建议）→ 前端展示**。

## 二、目录

| 路径 | 说明 |
|---|---|
| `app/backend/` | 后端源码 |
| `app/frontend/` | Vue3 + Vite 前端源码 |
| `app/frontend/dist/` | 前端构建产物（build 后生成，被后端托管） |
| `03_知识库/05_检索索引_六文件/` | 已有检索索引（FAISS+BM25，6824 文档，本应用直接复用） |
| `.env` | 本地配置（含密钥，已 gitignore） |
| `.env.example` | 配置模板（占位符，可提交） |
| `requirements.txt` | 后端依赖 |
| `scripts/e2e_test.py` | 端到端冒烟测试 |
| `build_frontend.bat` / `start_backend.bat` / `start_frontend_dev.bat` | 启动脚本 |

原实验目录 `00_`~`07_` 与本应用**相互独立**，应用只读引用 `03_知识库/05_检索索引_六文件`，不修改、不覆盖实验数据。

## 三、快速开始

### 方式 A：演示 / 分享链接（推荐，单端口）

```bat
:: 1. 首次需构建前端（已构建过可跳过）
build_frontend.bat

:: 2. 启动后端（自动托管前端，单端口 8000，host 0.0.0.0 可供局域网访问）
start_backend.bat
```

访问 `http://localhost:8000`（本机）或 `http://<本机IP>:8000`（给他人演示的链接）。

### 方式 B：开发模式（前后端分离，热更新）

```bat
:: 终端1：后端
start_backend.bat

:: 终端2：前端 dev server（http://localhost:5173，已代理 /api 到 8000）
start_frontend_dev.bat
```

## 四、配置（.env）

| 变量 | 说明 | 默认 |
|---|---|---|
| `MOCK_MODE` | true=离线示例（无需 API）；false=真实调用 | false |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 大模型（OpenAI 兼容） | DashScope + qwen3-32b |
| `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` | 向量化接口 | text-embedding-v4 |
| `VECTOR_DB_PATH` | 检索索引目录 | 自动定位到 `03_知识库/05_检索索引_六文件` |
| `BACKEND_PORT` | 后端端口 | 8000 |
| `FRONTEND_ORIGIN` | CORS 允许来源 | `*` |

**未配置 API Key 时系统自动回退 Mock 模式**（无需联网即可演示界面）。首次运行请复制 `.env.example` 为 `.env` 并填入真实值。

## 五、API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查（含 mock/live 状态、模型） |
| GET | `/api/topics` | 可用审核主题 |
| POST | `/api/audit` | JSON 文本审核（`{"text": "...", "topic": "..."}`） |
| POST | `/api/audit/upload` | 上传文件审核（multipart：`file` + `topic`，支持 txt/md/docx/pdf） |

## 六、审核输出契约（排放标准准确性）

```json
{
  "topic": "emission_standards",
  "mode": "live",
  "summary": "总体结论",
  "risk_level": "高|中|低",
  "issues": [{
    "id": "ISSUE-1",
    "category": "标准名称|标准编号|表号|污染物|限值|单位|控制位置|适用性|其他",
    "severity": "高|中|低",
    "description": "问题描述",
    "reported": "报告中所填内容",
    "correct_basis": { "standard_name": "", "standard_no": "", "clause": "", "pollutant": "", "limit": "", "unit": "", "control_location": "", "reference": "" },
    "suggestion": "修改建议"
  }],
  "retrieved_sources": [{ "rank": 1, "score": 0.9, "source_id": "", "title": "", "snippet": "" }]
}
```

## 七、已知限制 / 待办

1. 审核主题当前仅 `emission_standards`（排放标准准确性），其余题型（环境质量现状、工程参数等）后续接入。
2. 检索查询使用报告标准关键词拼接；大文件会按预算截断上下文（12000 字符），必要时再调。
3. `.env` 中的 API Key 请在 DashScope 控制台轮换（该 Key 若曾在聊天中明文出现）。
4. 未做用户鉴权；演示用途时请勿对公网长期暴露。