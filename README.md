# VisionPay Agent Platform

VisionPay 是一个基于 YOLOv11 的零售商品自动结账智能体平台（ACO）。项目面向收银台多商品堆叠场景，使用 Retail Product Checkout Dataset 训练视觉检测模型，实现商品定位、细粒度品类识别，并为后续购物结算清单生成提供视觉识别能力。

**核心能力：**
- 🔍 **商品定位** — 输入收银台真实多商品堆叠图像，自动定位图像中每个商品
- 🏷️ **品类识别** — 精准识别商品的细分品类（种类繁多、外观相似、相互遮挡）
- 🧾 **自动结算** — 生成最终购物结算清单，实现高效准确的自动化结算

当前进度已完成：

- 后端 FastAPI 基础架构、认证、健康检查和数据库迁移。
- Retail Product Checkout Dataset 的 COCO 到 YOLO 格式转换、划分、验证、bbox 修复和标注可视化。
- YOLOv11 本地训练服务 `TrainingService`。
- 训练任务 API：启动、列表、状态、指标、停止、结果下载。
- 前端模型训练监控页面：任务列表、创建训练任务、ECharts loss/mAP 曲线。
- Day 8 商品识别 Agent：DeepSeek Tool Calling、SSE 流式对话、单图/多图/ZIP 检测。
- 智能识别工作台：附件拖拽、阈值控制、快捷直检、标注图与商品类别汇总。

## 技术栈

| 层级 | 技术 |
| ---- | ---- |
| 后端框架 | FastAPI + Uvicorn |
| 训练/检测 | Ultralytics YOLOv11 + OpenCV |
| 智能体 | LangChain + LangGraph + OpenAI API |
| 数据库 | PostgreSQL 15 + Pgvector |
| 缓存 | Redis 7 |
| 对象存储 | MinIO |
| 前端 | Vue 3 + Vite + Element Plus + ECharts |
| 容器 | Docker Compose |

## 环境要求

| 工具 | 建议版本 | 验证命令 |
| ---- | -------- | -------- |
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| Docker Desktop | 24+ | `docker --version` |
| Docker Compose | 2+ | `docker compose version` |

## 快速启动

### 1. 克隆项目

```bash
git clone https://github.com/Azar233/agent-platform
cd agent-platform
```

### 2. 启动基础服务

确保 Docker Desktop 已启动：

```powershell
docker compose up -d postgres redis minio
docker compose ps
```

基础服务：

| 服务 | 地址 | 用途 |
| ---- | ---- | ---- |
| PostgreSQL | `localhost:5432` | 用户、场景、训练任务和指标 |
| Redis | `localhost:6379` | 缓存和后续对话历史 |
| MinIO API | `localhost:9000` | 图片、模型等对象存储 |
| MinIO Console | <http://localhost:9001> | 存储桶管理，默认账号 `minioadmin/minioadmin` |

当前 `docker-compose.yml` 使用的数据库配置：

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=vp_agent
DB_USER=vp_admin
DB_PASSWORD=vp_admin
```

后端 `backend/.env` 必须与上面的数据库名、用户名和密码一致。PostgreSQL 容器的数据卷只会在首次创建时初始化数据库；如果你改过数据库名或用户，但旧 volume 还在，需要同步 `.env` 或重建数据库 volume。

### 3. 配置并启动后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

复制并修改环境变量：

```powershell
Copy-Item .env.example .env
```

`backend/.env` 中至少确认这些值：

```env
APP_NAME=VisionPay Agent Platform
APP_VERSION=0.1.0

DB_HOST=localhost
DB_PORT=5432
DB_NAME=vp_agent
DB_USER=vp_admin
DB_PASSWORD=vp_admin

REDIS_HOST=localhost
REDIS_PORT=6379

MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=vp-images
MINIO_SECURE=false

ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8080

# DeepSeek V4 Flash（模型标识以控制台实际提供的名称为准）
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

# 可选：直接指定检测权重；留空时查找场景默认模型或最新训练 best.pt
DETECTION_MODEL_PATH=
```

执行数据库迁移并启动后端：

```powershell
alembic upgrade head
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/health/detail
```

API 文档：

```text
http://127.0.0.1:8000/docs
```

### 4. 启动前端

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

访问：

```text
http://127.0.0.1:5173
```

前端请求封装使用 `baseURL: /api`，Vite 代理会把 `/api/*` 转发到 `http://localhost:8000`。

### 使用 IP Webcam 接入手机摄像头

`/checkout` 支持读取 Android IP Webcam 提供的 MJPEG 视频流。后端会代理手机的 HTTP 视频流，
因此前端没有跨域或 HTTPS 混合内容问题；当前不会存储视频，也尚未发送给 YOLO。

1. 手机和电脑连接同一个 Wi-Fi。在 IP Webcam 中滚动到底部，点击“启动服务器”。
2. 当前前端固定使用 `http://192.168.1.109:8080`。先在电脑浏览器打开该地址，确认电脑能够
   访问手机；建议原型阶段关闭 IP Webcam 的登录/密码验证。
3. 正常启动后端和前端，在电脑打开 `http://127.0.0.1:5173/checkout`。
4. 进入页面或点击“Webcam”模式后会自动连接直播画面；切换到“图片上传”模式会断开视频流。

如果手机 IP 发生变化，请修改 `frontend/src/views/CustomerCheckoutPage.vue` 中的
`IP_WEBCAM_URL` 常量。

接口 `/api/camera/ip-webcam/stream` 只接受私有局域网 IP 以及 `/video`、`/videofeed` 路径，
避免被用于代理公网或任意内部地址。如果连接失败，请检查 Windows 防火墙、手机是否仍在运行服务器，
以及路由器是否开启了 AP/客户端隔离。

前端路由：

| 路由 | 页面 | 当前状态 |
| ---- | ---- | -------- |
| `/login` | 登录 | 已完成 |
| `/register` | 注册 | 已完成 |
| `/training` | 模型训练 | Day 6 已完成 |
| `/chat` | 通用智能对话 | 后续实现 |
| `/detection` | 商品检测 Agent、单图/多图/ZIP 工作台 | Day 8 已完成 |
| `/history` | 历史记录 | 后续完善 |
| `/dashboard` | 数据看板 | 后续完善 |

### Day 8 商品识别接口

所有接口都需要 JWT 登录态。前端 `/detection` 已接入以下能力：

| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| `GET` | `/api/chat/status` | 查看 DeepSeek Agent 配置状态 |
| `POST` | `/api/chat/upload` | 上传对话图片或 ZIP 附件 |
| `POST` | `/api/chat/stream` | DeepSeek Tool Calling + SSE 流式响应 |
| `POST` | `/api/chat/sessions` | 创建检测对话 |
| `GET` | `/api/chat/sessions` | 获取历史检测对话 |
| `GET` | `/api/chat/sessions/{session_uuid}` | 恢复历史消息与检测结果 |
| `DELETE` | `/api/chat/sessions/{session_uuid}` | 删除检测对话 |
| `POST` | `/api/detection/single` | 单图 YOLO 商品检测 |
| `POST` | `/api/detection/batch` | 多图批量检测 |
| `POST` | `/api/detection/zip` | ZIP 解压与批量检测 |

快捷“立即识别”按钮直接调用检测 API；自然语言指令通过 DeepSeek Agent 自动选择单图、多图或 ZIP Tool。检测模型按 `DETECTION_MODEL_PATH`、场景默认模型、最新完成训练的 `best.pt` 顺序选择。

## 数据集导入

训练数据统一放在：

```text
backend/datasets/vision_pay/
```

标准 YOLO 目录结构：

```text
backend/datasets/vision_pay/
├── data.yaml
├── images/
│   ├── train/
│   ├── val/
│   └── test/
└── labels/
    ├── train/
    ├── val/
    └── test/
```

### 方式一：单个 COCO JSON + images 目录

适用于：

```text
dataset/
├── images/
└── instances_train2019.json
```

执行：

```powershell
cd backend

python tools\convert_coco.py `
  --source C:\path\to\dataset `
  --json instances_train2019.json `
  --output datasets\vision_pay `
  --train-ratio 0.8 `
  --val-ratio 0.1 `
  --test-ratio 0.1 `
  --seed 42 `
  --clean
```

### 方式二：COCO 已分好 train/val/test

适用于：

```text
dataset/
├── train2019/
├── val2019/
├── test2019/
├── instances_train2019.json
├── instances_val2019.json
└── instances_test2019.json
```

执行：

```powershell
cd backend

python tools\convert_coco_splits.py `
  --source C:\path\to\dataset `
  --train-dir train2019 `
  --val-dir val2019 `
  --test-dir test2019 `
  --train-json instances_train2019.json `
  --val-json instances_val2019.json `
  --test-json instances_test2019.json `
  --output datasets\vision_pay `
  --clean
```

### 验证和可视化

导入完成后先验证：

```powershell
cd backend
python tools\verify_dataset.py datasets\vision_pay
```

如果提示 bbox 越界或坐标格式问题：

```powershell
python tools\fix_bbox.py datasets\vision_pay
python tools\verify_dataset.py datasets\vision_pay
```

抽样可视化标注：

```powershell
python tools\visualize_annotations.py --count 10 --output datasets\vision_pay\vis_output
python tools\visualize_annotations.py --grid --output datasets\vision_pay\vis_output\overview.jpg
```

`data.yaml` 是 YOLO 训练入口文件，记录数据集根目录、训练/验证/测试图片目录、类别数量和类别名称。训练服务默认查找：

```text
backend/datasets/vision_pay/data.yaml
```

### RPC 官方划分说明

Retail Product Checkout Dataset 的官方 split 不是普通的随机同分布划分：

- `train` 是单商品多角度图，每张图只有一个标注目标。
- `val/test` 是真实多商品结算图，平均每张图约 12 个目标，并包含旋转、遮挡和堆叠。
- 官方 JSON 的 200 个类别 ID 和名称在三个 split 中一致，COCO 到 YOLO 的连续类别映射可以共用。

因此官方 `val/test` 应保留为最终场景评估集，不能回流训练。只用单商品图训练时，普通 YOLO Mosaic 只能部分模拟多目标布局，无法充分模拟真实堆叠遮挡。正式训练应增加由 `train` 单商品素材生成的多商品合成场景，或采集并标注真实多商品训练图。

建议按以下顺序定位训练问题：

1. 关闭增强，在少量训练图上做过拟合测试，确认标签和优化链路能达到接近满分的 train 指标。
2. 单独评估 `split=train`。train 指标高而官方 val 指标低表示场景分布偏移，不是 COCO 类别映射错误。
3. 从单商品素材按商品分组建立同分布 holdout，用于观察分类是否收敛；官方 val 继续用于衡量结算场景泛化。
4. 正式训练使用 100 个以上 epoch，并观察 `results.csv`。5 epoch 仅用于流程冒烟测试，默认 3 epoch warmup 后几乎没有充分优化。

`verify_dataset.py` 会报告每个 split 的目标密度、类别覆盖和明显的 split 分布偏移。前端“场景增强”会启用平面旋转、翻转、Mosaic 和少量 MixUp，以缩小单商品图与结算图之间的差异，但它不能替代多商品场景训练数据。

如果从其他电脑复制了已经生成好的 `datasets/vision_pay`，需要确认 `data.yaml` 里的 `path` 指向当前电脑真实路径。最稳妥的方式是重新运行导入脚本生成。

## 跑通一次训练

训练前置条件：

1. PostgreSQL、Redis、MinIO 已启动。
2. 后端已执行 `alembic upgrade head`。
3. `backend/datasets/vision_pay/data.yaml` 存在，且 `verify_dataset.py` 无格式错误。
4. 数据库中存在一个 `DetectionScene`，前端创建训练任务时需要填写它的 `scene_id`。

### 1. 创建 Vision Pay 场景

如果数据库里还没有场景，在 `backend/` 目录执行：

```powershell
python -c "from app.database.session import SessionLocal; from app.entity.db_models import DetectionScene; db=SessionLocal(); s=db.query(DetectionScene).filter_by(name='vision_pay').first(); s=s or DetectionScene(name='vision_pay', display_name='Vision Pay', description='视觉识别购物结算系统', category='retail', class_names=['product']); db.add(s); db.commit(); db.refresh(s); print('scene_id=', s.id); db.close()"
```

记录输出的 `scene_id`。这里的 `class_names` 只是场景元信息；YOLO 训练实际使用的类别数量和类别名来自 `datasets/vision_pay/data.yaml`。

### 2. 注册和登录

可以在前端页面注册，也可以用 PowerShell 调接口：

```powershell
$body = @{username="trainer";email="trainer@example.com";password="123456"} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/auth/register -ContentType "application/json" -Body $body

$body = @{username="trainer";password="123456"} | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/auth/login -ContentType "application/json" -Body $body
$token = $login.access_token
```

### 3. 用 API 启动小训练

第一次建议只跑 1 个 epoch，先验证流程：

```powershell
$headers = @{Authorization="Bearer $token"}
$body = @{
  scene_id = 1
  model_name = "yolov11n"
  epochs = 1
  batch_size = 2
  img_size = 640
  device = "cpu"
  optimizer = "SGD"
  lr0 = 0.01
  dataset_path = "datasets/vision_pay"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/training/start -Headers $headers -ContentType "application/json" -Body $body
```

把 `scene_id = 1` 换成实际场景 ID。

项目内部模型名 `yolov11n` 会映射为 Ultralytics 权重 `yolo11n.pt`。首次训练可能需要联网下载权重；如果下载失败，可以手动把 `yolo11n.pt` 放到后端工作目录或 Ultralytics 缓存目录后重试。

训练输出目录：

```text
backend/runs/train/task_<task_uuid>/
├── results.csv
├── weights/
│   ├── best.pt
│   └── last.pt
└── ...
```

### 4. 在前端启动训练并查看图表

1. 启动后端：`cd backend && uvicorn main:app --host 127.0.0.1 --port 8000 --reload`
2. 启动前端：`cd frontend && npm run dev -- --host 127.0.0.1`
3. 打开 <http://127.0.0.1:5173>
4. 注册或登录用户。
5. 进入左侧「模型训练」页面。
6. 点击「新建训练任务」。
7. 填写参数：

```text
检测场景: 上面创建的 scene_id
基础模型: YOLOv11n
训练轮数: 1 或 5
批次大小: 2 或 4
图像尺寸: 640
训练设备: CPU
优化器: SGD
初始学习率: 0.01
数据集目录: datasets/vision_pay
```

8. 点击「启动训练」。
9. 在任务列表点击「监控」。

训练监控页每 5 秒轮询状态和指标：

| 接口 | 作用 |
| ---- | ---- |
| `GET /api/training/tasks` | 获取训练任务列表 |
| `GET /api/training/status/{task_id}` | 获取任务状态和最新 epoch 指标 |
| `GET /api/training/metrics/{task_id}` | 获取所有 epoch 指标 |

图表说明：

| 图表 | 指标 |
| ---- | ---- |
| 训练损失曲线 | `Box Loss`、`Cls Loss`、`DFL Loss` |
| 评估指标曲线 | `mAP@50`、`mAP@50-95`、`Precision`、`Recall` |

训练完成后，任务状态会变为「已完成」，可以点击「结果」下载 `results.csv`。

### 5. 训练 API

| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| `POST` | `/api/training/start` | 创建并启动训练任务 |
| `GET` | `/api/training/tasks` | 获取当前用户训练任务 |
| `GET` | `/api/training/status/{task_id}` | 查询任务状态和最新指标 |
| `GET` | `/api/training/metrics/{task_id}` | 查询训练指标历史 |
| `POST` | `/api/training/stop/{task_id}` | 停止运行中的训练任务 |
| `GET` | `/api/training/results/{task_uuid}` | 下载 `results.csv` |

所有训练接口都需要登录后的 JWT：`Authorization: Bearer <token>`。

## 项目结构

```text
agent-platform/
├── docker-compose.yml
├── README.md
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── health.py
│   │   │   └── training.py
│   │   ├── config/
│   │   │   └── settings.py
│   │   ├── core/
│   │   │   ├── exceptions.py
│   │   │   ├── logger.py
│   │   │   └── security.py
│   │   ├── database/
│   │   │   └── session.py
│   │   ├── entity/
│   │   │   ├── db_models.py
│   │   │   └── schemas.py
│   │   ├── middleware/
│   │   │   └── request_logger.py
│   │   ├── services/
│   │   │   └── user_service.py
│   │   ├── storage/
│   │   │   └── minio_client.py
│   │   └── training/
│   │       ├── data_converter.py
│   │       ├── dataset_splitter.py
│   │       └── training_service.py
│   ├── tools/
│   │   ├── convert_coco.py
│   │   ├── convert_coco_splits.py
│   │   ├── fix_bbox.py
│   │   ├── verify_dataset.py
│   │   └── visualize_annotations.py
│   ├── datasets/
│   │   └── vision_pay/
│   └── runs/
│       └── train/
└── frontend/
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── api/
        │   ├── auth.js
        │   └── training.js
        ├── assets/
        │   └── styles/
        ├── components/
        │   └── layout/
        ├── router/
        │   └── index.js
        ├── stores/
        ├── utils/
        │   ├── markdown.js
        │   ├── request.js
        │   └── stream.js
        └── views/
            ├── ChatPage.vue
            ├── DashboardPage.vue
            ├── DetectionPage.vue
            ├── HistoryPage.vue
            ├── LoginPage.vue
            ├── RegisterPage.vue
            └── TrainingPage.vue
```

`backend/datasets/`、`backend/runs/`、`backend/.ultralytics/`、模型权重和日志属于本地运行产物，不提交 Git。

## 常用命令

### Docker

```powershell
docker compose up -d postgres redis minio
docker compose ps
docker compose logs -f postgres
docker compose logs -f redis
docker compose logs -f minio
docker compose down
```

### 后端

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
pytest -q
```

### 前端

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
npm run build
```

### 数据集

```powershell
cd backend
python tools\verify_dataset.py datasets\vision_pay
python tools\fix_bbox.py datasets\vision_pay
python tools\visualize_annotations.py --count 10 --output datasets\vision_pay\vis_output
```

## 验证清单

提交 Day6 更新前建议至少跑：

```powershell
cd backend
pytest -q

cd ..\frontend
npm run build
```

运行环境检查：

| 检查项 | 命令或页面 | 预期 |
| ------ | ---------- | ---- |
| Docker 服务 | `docker compose ps` | PostgreSQL、Redis、MinIO 为 Up/healthy |
| 后端健康 | `http://127.0.0.1:8000/api/health` | 返回健康状态 |
| 详细健康 | `http://127.0.0.1:8000/api/health/detail` | database、redis、minio 正常 |
| 前端 | `http://127.0.0.1:5173` | 可打开登录页 |
| 数据集 | `python tools\verify_dataset.py datasets\vision_pay` | 无格式错误 |
| 训练页 | `/training` | 可新建任务、查看任务列表和曲线 |

## 常见问题

### 后端连不上 PostgreSQL

优先检查三处是否一致：

```text
docker-compose.yml 中 POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD
backend/.env 中 DB_NAME / DB_USER / DB_PASSWORD
当前 Docker volume 里已经初始化过的数据库
```

如果旧 volume 中仍是旧数据库，修改 `.env` 不会自动创建新数据库。

### `/api/training/start` 返回 `data.yaml 不存在`

确认数据集目录存在：

```powershell
cd backend
Test-Path datasets\vision_pay\data.yaml
python tools\verify_dataset.py datasets\vision_pay
```

前端训练表单里的「数据集目录」使用相对路径：

```text
datasets/vision_pay
```

### 首次训练卡在下载权重

`yolov11n` 会映射为 Ultralytics 的 `yolo11n.pt`。首次训练可能联网下载权重，网络不可用时会失败。可以提前手动下载 `yolo11n.pt` 并放到后端工作目录或 Ultralytics 缓存目录后重试。

### 前端没有训练曲线

先确认任务不是刚创建还没进入第一个 epoch。曲线数据来自 `training_metrics` 表，训练 callback 或最终 `results.csv` 解析后才会出现。若任务状态为 `failed`，查看后端终端日志和 `training_tasks.error_message`。

### 点击「结果」下载失败

只有 `completed` 状态且 `backend/runs/train/task_<task_uuid>/results.csv` 存在时才可下载。下载接口需要登录态，前端会通过 Axios 自动携带 JWT。
