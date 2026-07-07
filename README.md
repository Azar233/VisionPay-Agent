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

执行数据库迁移（首次或模型变更后）：

```bash
# 生成迁移脚本
alembic revision --autogenerate -m "init: create tables"

# 执行迁移
alembic upgrade head
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

### 4. 配置并启动前端

```bash
# 新开一个终端，进入前端目录
cd frontend

# 安装依赖（首次）
npm install

# 配置环境变量（首次）
cp .env.example .env
# 编辑 .env 中的 API 地址等配置
```

**`.env` 关键配置项**：

```env
# 后端 API 地址（Vite 开发服务器代理目标）
VITE_API_BASE_URL=http://localhost:8000

# 应用名称
VITE_APP_TITLE=My Agent Platform

# MinIO 文件访问地址
VITE_MINIO_URL=http://localhost:9000
```

启动前端开发服务器：

```bash
npm run dev
```

访问：<http://localhost:5173>

**前端页面路由**：

| 路由 | 页面 | 说明 |
| ---- | ---- | ---- |
| `/login` | 登录页 | 用户登录表单 |
| `/register` | 注册页 | 用户注册表单 |
| `/chat` | 智能对话 | Day 11 完善 |
| `/detection` | 检测工作台 | Day 8 完善 |
| `/training` | 模型训练 | Day 6 完善 |
| `/history` | 历史记录 | Day 10 完善 |
| `/dashboard` | 数据看板 | Day 10 完善 |

> 未登录状态下访问任何受保护页面会自动跳转到 `/login`；已登录用户访问登录/注册页会自动跳转到首页。

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
│   ├── alembic.ini             # Alembic 配置
│   ├── alembic/                # 数据库迁移脚本
│   └── app/
│       ├── api/                # API 路由
│       ├── config/             # 配置管理
│       ├── core/               # 核心逻辑
│       ├── database/           # 数据库层
│       ├── entity/             # 数据实体
│       ├── services/           # 业务服务
│       └── storage/            # 存储层
└── frontend/                   # Vue 3 + Vite 前端
    ├── index.html              # HTML 入口
    ├── vite.config.js          # Vite 配置（别名、代理、SCSS）
    ├── package.json            # 项目依赖
    ├── .env                    # 环境变量（不提交 Git）
    ├── .env.example            # 环境变量模板（提交 Git）
    ├── public/
    │   └── favicon.svg         # 网站图标
    └── src/
        ├── main.js             # 应用入口（注册插件）
        ├── App.vue             # 根组件（路由出口）
        ├── api/                # API 接口层
        │   └── auth.js         # 认证 API（login/register/me）
        ├── assets/
        │   └── styles/         # 全局样式
        │       ├── variables.scss  # SCSS 变量
        │       ├── reset.scss      # 样式重置
        │       └── global.scss     # 全局样式
        ├── components/
        │   └── layout/         # 布局组件
        │       ├── AppHeader.vue   # 顶部导航栏
        │       ├── AppSidebar.vue  # 侧边栏菜单
        │       └── MainLayout.vue  # 主布局
        ├── router/
        │   └── index.js        # 路由配置 + 导航守卫
        ├── stores/             # Pinia 状态管理
        │   ├── index.js        # Pinia 实例
        │   ├── user.js         # 用户状态
        │   └── agent.js        # 智能体状态
        ├── utils/              # 工具函数
        │   ├── request.js      # Axios 封装
        │   ├── stream.js       # SSE 流式处理
        │   └── markdown.js     # Markdown 渲染
        └── views/              # 页面组件
            ├── LoginPage.vue       # 登录页
            ├── RegisterPage.vue    # 注册页
            ├── ChatPage.vue        # 智能对话（占位）
            ├── DetectionPage.vue   # 检测工作台（占位）
            ├── TrainingPage.vue    # 模型训练（占位）
            ├── HistoryPage.vue     # 历史记录（占位）
            └── DashboardPage.vue   # 数据看板（占位）
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

### 后端开发

```bash
cd backend
.venv\Scripts\activate         # 激活虚拟环境（Windows）
python main.py                 # 启动后端（端口 8000）
alembic revision --autogenerate -m "描述"  # 生成迁移
alembic upgrade head           # 执行迁移
alembic downgrade -1           # 回滚上一版本
```

### 前端开发

```bash
cd frontend
npm install                    # 安装依赖
npm run dev                    # 启动开发服务器（端口 5173）
npm run build                  # 构建生产版本
npm run preview                # 预览生产构建
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

### 基础环境

```bash
git --version                  # ✅ git version 2.x.x
python --version               # ✅ Python 3.10+
node --version                 # ✅ v18+
docker --version               # ✅ Docker version 24.0+
docker compose version         # ✅ Docker Compose v2.x+
docker compose ps              # ✅ 所有服务状态为 Up / healthy
```

### API 接口验证（PowerShell）

```powershell
# 1. 健康检查
Invoke-RestMethod -Uri http://localhost:8000/api/health
# 预期：{"status":"healthy","app_name":"My Agent Platform","version":"0.1.0"}

# 2. 注册用户
$body = @{username="verify_user";email="verify@test.com";password="123456"} | ConvertTo-Json; Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/auth/register -ContentType "application/json" -Body $body
# 预期：返回 201，包含用户信息

# 3. 登录获取 Token
$body = @{username="verify_user";password="123456"} | ConvertTo-Json; $resp = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/auth/login -ContentType "application/json" -Body $body; $resp.access_token
# 预期：输出 access_token 字符串

# 4. 用 Token 获取当前用户信息（用上一步输出的 Token 替换 YOUR_TOKEN）
Invoke-RestMethod -Uri http://localhost:8000/api/auth/me -Headers @{"Authorization"="Bearer YOUR_TOKEN"}
# 预期：返回当前用户信息
```

### 服务连通验证

```bash
# 验证 Redis
docker compose exec redis redis-cli ping
# 期望：PONG

# 验证 MinIO — 浏览器访问 http://localhost:9001
# 用户名：minioadmin  密码：minioadmin
```

### 前端页面验证

1. 确保后端服务已启动（`cd backend && python main.py`）
2. 确保前端开发服务器已启动（`cd frontend && npm run dev`）
3. 浏览器访问 <http://localhost:5173>

| 验证项 | 操作 | 预期结果 |
| ------ | ---- | ---- |
| 路由守卫 | 直接访问 `/` 或 `/chat` | 自动跳转到 `/login` |
| 登录页面 | 访问 `/login` | 显示登录表单，紫色渐变背景 |
| 注册页面 | 点击"立即注册" | 跳转到 `/register`，显示注册表单 |
| 表单验证 | 提交空表单 | 显示验证错误提示 |
| 注册流程 | 填写用户名/邮箱/密码并提交 | 注册成功跳转到登录页 |
| 登录流程 | 使用已注册账号登录 | 登录成功跳转到智能对话页 |
| 侧边栏导航 | 点击各菜单项 | 页面切换正常，URL 变化 |
| 退出登录 | 点击右上角用户名 → 退出登录 | 清除 Token，跳转登录页 |
| 路由守卫* | 退出后直接访问 `/detection` | 自动跳转到登录页 |

全部通过后，开发环境即搭建完成 🎉
