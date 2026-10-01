# Railway 部署指南（环评AI知识库智能审查系统）

## 一、架构说明

为了"给一个链接就能让别人打开完整可用的系统"，采用**单容器部署**：

```
Railway 容器（一个 URL）
├── 前端 Vue3 静态文件（构建后的 dist）
├── FastAPI 后端（/api/* 接口）
└── 精简检索索引（3 文件，约 46MB）
```

前端通过同源相对路径 `/api/*` 调用后端，无需跨域、无需额外配置。
分享时只需要把这个 Railway URL 发给对方即可。

> 之前配好的 GitHub Pages 仍是可选的"演示态"落地页（无后端时前端会自动回退到内置示例）。
> 真实 AI 审核要靠 Railway 这个地址。

## 二、已准备好的部署文件

| 文件 | 作用 |
|------|------|
| `Dockerfile` | 两阶段构建：Node 构建前端 + Python 运行后端 |
| `.dockerignore` | 排除实验数据、密钥、缓存等，只打包运行所需 |
| `railway.json` | Railway 配置：Dockerfile 构建 + `/api/health` 健康检查 |
| `app/deploy/kb_slim/` | 精简索引 3 文件（6824 条，已验证 BM25/FAISS 对齐可检索） |
| `app/deploy/slim_index.py` | 精简索引生成脚本（可复现） |

## 三、前置条件

1. 一个 GitHub 账号与仓库（本项目已初始化过 git）。
2. 一个 Railway 账号（可用 GitHub 账号登录，需绑定信用卡领取 $5 试用额度）。
3. 你的 DashScope API Key（即本地 `.env` 里填的那个 `sk-...`，**不要**贴到公开仓库）。
4. Docker 或 Node（方法 A 不需要本地 Docker，Railway 云端构建）。

## 四、方法 A：GitHub 仓库 → Railway（推荐）

### 第 1 步：提交代码到 GitHub（含精简索引）

```powershell
cd "d:\华南理工项目\环评审核幻觉实验"
git add -A
git status          # 确认 .env、00~07 数据目录没有被纳入
git commit -m "添加 Railway 部署配置与精简索引"
git push
```

> 注意：`.gitignore` 已排除 `03_知识库/` 等原始数据（200MB+）与 `.env`。
> 精简索引 `app/deploy/kb_slim/`（46MB，公开法规条文）会正常提交。

### 第 2 步：在 Railway 新建项目并连仓库

1. 登录 https://railway.app → 点击 **New Project**。
2. 选择 **Deploy from GitHub repo**，授权后选中该项目仓库。
3. Railway 会自动识别根目录的 `Dockerfile` 和 `railway.json` 并开始构建。
   （首次构建约 3~6 分钟，之后改代码自动重新部署。）

### 第 3 步：设置环境变量（关键 → 决定真实 AI 还是演示态）

进入项目 → 服务 → **Variables**，添加：

| 变量名 | 值 | 说明 |
|--------|----|------|
| `LLM_API_KEY` | `sk-你本地的密钥` | DashScope 密钥 |
| `MOCK_MODE` | `false` | 关闭演示模式，走真实模型 |
| `LLM_MODEL` | `qwen3-8b`（或 `qwen3-32b`） | 可选，8b 更快更省，32b 更强 |

- 想先免费跑通链路、不花 API 钱：**不要设** `LLM_API_KEY`，或设 `MOCK_MODE=true`，
  系统会返回内置示例结果（上传文件解析仍正常）。
- 若模型非流式调用报错，后端已内置 `enable_thinking: false` 兼容处理，无需额外设置。

### 第 4 步：拿到链接并分享

1. 部署完成后，在服务页点 **Settings → Networking → Generate Public Domain**。
2. 得到类似 `https://xxx.up.railway.app` 的地址，直接分享即可。

## 五、方法 B：`railway up` 本地部署（不把索引提交到 GitHub）

若不想让 46MB 索引进入公开仓库，可本地直传：

```powershell
# 安装 Railway CLI（任选其一）
npm i -g @railway/cli
# 或 winget install Railway.Railway

railway init         # 首次会引导登录（用 GitHub 登录）
railway up           # 打包当前目录（按 .dockerignore 筛选）上传云端构建
```

之后同样在服务面板设环境变量、生成 Public Domain。

## 六、验证

1. 浏览器打开 Railway URL → 应显示前端界面。
2. 打开 `https://xxx.up.railway.app/api/health` → 应返回 JSON，
   `mock_mode` 为 `false`、`api_configured` 为 `true` 即代表真实模式已生效。
3. 点"加载内置示例"或上传一份报告文本/PDF/DOCX，看是否返回带证据和风险等级的审核结果。

## 七、成本与时长说明

- Railway 试用额度约 $5，免费档 512MB 内存 / 1GB 磁盘；本系统精简后约占用一半内存，可正常跑。
- 额度用尽或试用到期后服务停跑；届时重新计费或换平台即可。
- DashScope API 按 token 计费（qwen3-8b 每次审核约几分钱），与 Railway 试用额度无关。