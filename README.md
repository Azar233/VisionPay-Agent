# My Agent Platform

基于 YOLOv11 的目标检测智能体平台，融合 LangChain/LangGraph 智能体框架与 YOLOv11 目标检测模型，提供遥感目标检测能力。

## 技术栈

| 层级 | 技术 |
|------|------|
| **后端框架** | FastAPI + Uvicorn |
| **智能体** | LangChain + LangGraph + OpenAI API |
| **目标检测** | YOLOv11 (Ultralytics) + OpenCV |
| **数据库** | PostgreSQL 15 + Pgvector（向量存储） |
| **缓存** | Redis 7 |
| **对象存储** | MinIO |
| **前端** | Vue 3 + Vite + Element Plus |
| **容器化** | Docker Compose |

---

## 环境要求

| 工具 | 最低版本 | 验证命令 |
|------|---------|---------|
| Git | 2.30+ | `git --version` |
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| Docker | 24.0+ | `docker --version` |
| Docker Compose | 2.0+ | `docker compose version` |

---

## 快速开始

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd agent-platform
```

### 2. 启动基础设施服务（Docker）

确保 Docker Desktop 已启动，然后在项目根目录执行：

```bash
# 拉取镜像（首次运行）
docker compose pull

# 启动所有服务（后台运行）
docker compose up -d

# 查看服务状态
docker compose ps
```

启动的服务：

| 服务 | 地址 | 说明 |
|------|------|------|
| PostgreSQL + Pgvector | `localhost:5432` | 数据库 + 向量扩展 |
| Redis | `localhost:6379` | 缓存 / 对话历史 |
| MinIO API | `localhost:9000` | 对象存储 API |
| MinIO Console | <http://localhost:9001> | 对象存储控制台 |

MinIO 控制台登录凭据：`minioadmin` / `minioadmin`

> Ollama（本地 LLM）默认关闭，如需启用请取消 `docker-compose.yml` 中 `ollama` 服务的注释。

### 3. 配置并启动后端

```bash
# 进入后端目录
cd backend

# 创建虚拟环境（首次）
python -m venv .venv

# 激活虚拟环境
# Windows CMD:
.venv\Scripts\activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（首次）
cp .env.example .env
# 编辑 .env 中的数据库密码、API Key 等配置
```

**`.env` 关键配置项**（需与 `docker-compose.yml` 保持一致）：

```env
# 数据库
DB_HOST=localhost
DB_PORT=5432
DB_NAME=my_agent
DB_USER=my_admin
DB_PASSWORD=my_admin
DATABASE_URL=postgresql://my_admin:my_admin@localhost:5432/my_agent

# Redis
REDIS_URL=redis://localhost:6379/0

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

启动后端服务：

```bash
# 在 backend/ 目录下，确保虚拟环境已激活
python main.py
# 或
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

访问：

- **API 根路径**：<http://localhost:8000>
- **Swagger 文档**：<http://localhost:8000/docs>
- **ReDoc 文档**：<http://localhost:8000/redoc>
- **健康检查**：<http://localhost:8000/api/health>

### 4. 启动前端

```bash
# 新开一个终端
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

访问：<http://localhost:5173>

---

## 项目结构

```
agent-platform/
├── docker-compose.yml          # Docker 服务编排
├── README.md
├── backend/
│   ├── main.py                 # FastAPI 入口
│   ├── requirements.txt        # Python 依赖
│   ├── .env                    # 环境变量（不提交 Git）
│   ├── .env.example            # 环境变量模板（提交 Git）
│   └── app/
│       ├── api/                # API 路由
│       ├── config/             # 配置管理
│       ├── core/               # 核心逻辑
│       ├── database/           # 数据库层
│       ├── entity/             # 数据实体
│       ├── services/           # 业务服务
│       └── storage/            # 存储层
└── frontend/                   # Vue 3 + Vite 前端
    ├── src/
    ├── public/
    ├── package.json
    └── vite.config.js
```

---

## 常用命令

### Docker 服务管理

```bash
docker compose up -d           # 启动所有服务
docker compose ps              # 查看状态
docker compose logs -f         # 查看日志
docker compose down            # 停止服务（保留数据）
docker compose down -v         # 停止并删除数据卷（⚠️ 清空数据）
```

### 服务验证

```bash
# 验证 Redis
docker compose exec redis redis-cli ping
# 期望：PONG

# 验证 PostgreSQL
docker compose exec postgres psql -U my_admin -d my_agent -c "SELECT version();"

# 验证 MinIO — 浏览器访问 http://localhost:9001 （见下方 MinIO Console 链接）
```

---

## 环境验证清单

```bash
git --version                  # ✅ git version 2.x.x
python --version               # ✅ Python 3.10+
node --version                 # ✅ v18+
docker --version               # ✅ Docker version 24.0+
docker compose version         # ✅ Docker Compose v2.x+
docker compose ps              # ✅ 所有服务状态为 Up / healthy
```

全部通过后，开发环境即搭建完成 🎉
