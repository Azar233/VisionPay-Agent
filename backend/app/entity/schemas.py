"""
Pydantic 请求/响应模型
用于 API 接口的数据验证和序列化

分层原则：
  - Create 模型：创建资源时的请求体
  - Update 模型：更新资源时的请求体（所有字段可选）
  - Response 模型：API 返回的响应体（过滤敏感字段）
  - List 模型：分页列表查询的参数和响应
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectBaseModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


# ══════════════════════════════════════════════════════════════
# 一、用户与权限
# ══════════════════════════════════════════════════════════════

# --- 认证相关 ---

class UserRegister(ProjectBaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class UserLogin(ProjectBaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class UserBrief(ProjectBaseModel):
    """用户简要信息（嵌入在 Token 响应中）"""
    id: int
    username: str
    email: str
    avatar: Optional[str] = None
    is_superuser: bool = False
    roles: list[str] = []

    model_config = {
        "from_attributes": True,
    }


class TokenResponse(ProjectBaseModel):
    """登录成功响应"""
    access_token: str
    token_type: str = "bearer"
    user: UserBrief


# --- 用户管理 ---

class UserResponse(ProjectBaseModel):
    """用户详情响应"""
    id: int
    username: str
    email: str
    phone: Optional[str] = None
    avatar: Optional[str] = None
    is_active: bool
    is_superuser: bool
    roles: list[str] = []
    last_login_at: Optional[datetime] = None
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class UserUpdate(ProjectBaseModel):
    """用户信息更新"""
    phone: Optional[str] = None
    avatar: Optional[str] = None
    email: Optional[str] = None


class ChangePassword(ProjectBaseModel):
    """修改密码"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


# --- 角色权限 ---

class RoleResponse(ProjectBaseModel):
    """角色响应"""
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    is_system: bool
    permissions: list[str] = []  # 权限编码列表
    created_at: datetime

    class Config:
        from_attributes = True


class RoleCreate(ProjectBaseModel):
    """创建角色"""
    name: str = Field(..., min_length=2, max_length=50, description="角色标识")
    display_name: str = Field(..., description="角色显示名")
    description: Optional[str] = None
    permission_codes: list[str] = Field(default=[], description="权限编码列表")


class PermissionResponse(ProjectBaseModel):
    """权限响应"""
    id: int
    code: str
    name: str
    module: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
# 二、检测业务
# ══════════════════════════════════════════════════════════════

# --- 检测场景 ---

class SceneCreate(ProjectBaseModel):
    """创建检测场景"""
    name: str = Field(..., description="场景标识，如 remote_sensing")
    display_name: str = Field(..., description="场景显示名，如 遥感目标检测")
    description: Optional[str] = None
    category: str = Field(..., description="分类：agriculture/industry/remote_sensing/medical/traffic")
    class_names: list[str] = Field(..., description="类别列表")
    class_names_cn: Optional[dict[str, str]] = Field(None, description="中文名映射")


class SceneResponse(ProjectBaseModel):
    """检测场景响应"""
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    category: str
    class_names: list
    class_names_cn: Optional[dict] = None
    is_active: bool
    default_model: Optional["ModelVersionBrief"] = None
    created_at: datetime

    class Config:
        from_attributes = True


# --- 检测任务 ---

class DetectionTaskResponse(ProjectBaseModel):
    """检测任务响应"""
    id: int
    user_id: int
    scene_id: int
    scene_name: Optional[str] = None
    model_version_id: Optional[int] = None
    task_type: str
    status: str
    total_images: int
    total_objects: int
    total_inference_time: float
    conf_threshold: float
    iou_threshold: float
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True,
        "protected_namespaces": (),
    }


class DetectionResultResponse(ProjectBaseModel):
    """单条检测结果响应"""
    id: int
    task_id: int
    image_path: str
    annotated_image_url: Optional[str] = None
    class_name: str
    class_name_cn: Optional[str] = None
    class_id: int
    confidence: float
    bbox: list  # [x1, y1, x2, y2]
    inference_time: Optional[float] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DetectionTaskDetail(ProjectBaseModel):
    """检测任务详情（含结果列表）"""
    task: DetectionTaskResponse
    results: list[DetectionResultResponse] = []


# --- 检测统计 ---

class DetectionStatistics(ProjectBaseModel):
    """检测统计数据"""
    total_tasks: int
    total_images: int
    total_objects: int
    avg_inference_time: float
    class_distribution: dict[str, int]  # 各类别检测次数
    daily_trend: list[dict]             # 每日检测趋势
    scene_distribution: dict[str, int]  # 各场景检测次数


# ══════════════════════════════════════════════════════════════
# 三、商品价格
# ══════════════════════════════════════════════════════════════

class ProductPriceCreate(ProjectBaseModel):
    """创建/更新商品价格"""
    category_id: int = Field(..., description="检测类别 ID")
    sku_name: Optional[str] = Field(None, description="SKU 英文名")
    name: Optional[str] = Field(None, description="商品中文名")
    barcode: Optional[str] = Field(None, description="商品条码")
    unit_price: float = Field(..., ge=0, description="单价（元）")
    currency: str = Field(default="CNY", description="货币")


class ProductPriceUpdate(ProjectBaseModel):
    """部分更新商品价格（所有字段可选）"""
    sku_name: Optional[str] = Field(None, description="SKU 英文名")
    name: Optional[str] = Field(None, description="商品中文名")
    barcode: Optional[str] = Field(None, description="商品条码")
    unit_price: Optional[float] = Field(None, ge=0, description="单价（元）")
    currency: Optional[str] = Field(None, description="货币")


class ProductPriceResponse(ProjectBaseModel):
    """商品价格响应"""
    id: int
    category_id: int
    sku_name: Optional[str] = None
    name: Optional[str] = None
    barcode: Optional[str] = None
    unit_price: float
    currency: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "protected_namespaces": (),
    }


class CheckoutItemQuantity(ProjectBaseModel):
    """结算清单中由客户端确认的类别和数量。"""
    class_id: int = Field(..., ge=0, le=199, description="YOLO 类别 ID（0-199）")
    quantity: int = Field(..., ge=1, le=99, description="确认后的商品数量")


class CheckoutCalculateRequest(ProjectBaseModel):
    """服务端重新计价请求；单价始终从数据库读取。"""
    items: list[CheckoutItemQuantity] = Field(..., min_length=1, max_length=200)


class MockPaymentConfirmRequest(ProjectBaseModel):
    """模拟付款确认；金额始终由服务端订单决定。"""
    payment_method: Literal["wechat", "alipay"] = "wechat"


class MockPaymentOrderView(ProjectBaseModel):
    """电脑端和手机端共享的只读订单快照。"""
    order_uuid: str
    status: Literal["pending", "paid", "expired"]
    currency: str
    amount: float
    item_count: int
    items: list[dict]
    payment_method: Optional[str] = None
    created_at: datetime
    expires_at: datetime
    paid_at: Optional[datetime] = None


class MockPaymentOrderCreated(MockPaymentOrderView):
    """创建订单时额外返回一次不可预测的扫码令牌。"""
    payment_token: str


class MockPaymentStatusResponse(ProjectBaseModel):
    order_uuid: str
    status: Literal["pending", "paid", "expired"]
    expires_at: datetime
    paid_at: Optional[datetime] = None


# ══════════════════════════════════════════════════════════════
# 四、模型管理
# ══════════════════════════════════════════════════════════════

# --- 训练任务 ---

class TrainingTaskCreate(ProjectBaseModel):
    """创建训练任务"""
    scene_id: int = Field(..., description="关联场景 ID")
    model_name: str = Field(default="yolov11n", description="基础模型")
    epochs: int = Field(default=100, ge=1, le=500, description="训练轮数")
    img_size: int = Field(default=640, description="图像尺寸")
    batch_size: int = Field(default=16, ge=1, le=512, description="Global batch size")
    device: str = Field(default="0", description="Training device: cpu, 0, 0,1,2,3, or 0-7")
    optimizer: str = Field(default="SGD", description="优化器")
    lr0: float = Field(default=0.01, description="初始学习率")
    augment_config: Optional[dict] = Field(None, description="数据增强配置")
    dataset_path: Optional[str] = Field(None, description="数据集目录，默认 datasets/vision_pay")
    data_yaml: Optional[str] = Field(None, description="data.yaml 路径，默认在数据集目录下查找")

    model_config = {
        "protected_namespaces": (),
    }


class TrainingRunImportRequest(ProjectBaseModel):
    """导入 sbatch/离线训练输出目录。"""
    scene_id: int = Field(..., description="关联场景 ID")
    run_dir: str = Field(..., description="Ultralytics run 目录，包含 results.csv 和 weights/")
    task_uuid: Optional[str] = Field(None, description="导入后的任务 ID；默认从 run_dir 名称推断")
    status: str = Field(
        default="completed",
        pattern="^(completed|failed|cancelled)$",
        description="导入后的任务状态",
    )
    model_name: Optional[str] = Field(None, description="基础模型；默认读取 args.yaml")
    epochs: Optional[int] = Field(None, ge=1, le=1000, description="训练轮数；默认读取 args.yaml/results.csv")
    img_size: Optional[int] = Field(None, ge=32, description="图像尺寸；默认读取 args.yaml")
    batch_size: Optional[int] = Field(None, ge=1, le=4096, description="Global batch size；默认读取 args.yaml")
    device: Optional[str] = Field(None, description="训练设备；默认读取 args.yaml")
    optimizer: Optional[str] = Field(None, description="优化器；默认读取 args.yaml")
    lr0: Optional[float] = Field(None, description="初始学习率；默认读取 args.yaml")
    augment_config: Optional[dict] = Field(None, description="数据增强配置；可选")
    dataset_path: Optional[str] = Field(None, description="数据集目录；默认由 data_yaml 推断")
    data_yaml: Optional[str] = Field(None, description="data.yaml 路径；默认读取 args.yaml")
    log_path: Optional[str] = Field(None, description="sbatch/训练日志路径；可选，会导入尾部日志")

    model_config = {
        "protected_namespaces": (),
    }


class TrainingTaskResponse(ProjectBaseModel):
    """训练任务响应"""
    id: int
    user_id: int
    scene_id: int
    scene_name: Optional[str] = None
    task_uuid: str
    status: str
    model_name: str
    epochs: int
    current_epoch: int
    progress: int
    img_size: int
    batch_size: int
    device: str
    dataset_size: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True,
        "protected_namespaces": (),
    }


class TrainingMetricResponse(ProjectBaseModel):
    """训练指标响应（单 epoch）"""
    epoch: int
    box_loss: Optional[float] = None
    cls_loss: Optional[float] = None
    dfl_loss: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    map50: Optional[float] = None
    map50_95: Optional[float] = None
    lr: Optional[float] = None

    class Config:
        from_attributes = True

class ModelValidateRequest(ProjectBaseModel):
    """模型评估请求"""
    split: str = Field(default="val", pattern="^(train|val|test)$", description="评估集划分")
    conf: float = Field(default=0.001, ge=0, le=1, description="置信度阈值")
    iou: float = Field(default=0.6, ge=0, le=1, description="NMS IoU 阈值")
    img_size: Optional[int] = Field(default=None, ge=32, description="评估图像尺寸")
    device: Optional[str] = Field(default=None, description="评估设备，如 cpu 或 0")


class ModelExportRequest(ProjectBaseModel):
    """模型导出请求"""
    version: Optional[str] = Field(default=None, description="模型版本号，如 v1.0.0")
    description: Optional[str] = Field(default=None, description="版本说明")
    set_default: bool = Field(default=True, description="是否设置为场景默认模型")


class ModelExportResponse(ProjectBaseModel):
    """模型导出响应"""
    message: str
    model_version: dict
    model_path: str
    model_dir: str
    report_path: Optional[str] = None


# --- 模型版本 ---

class ModelVersionBrief(ProjectBaseModel):
    """模型版本简要信息"""
    id: int
    version: str
    model_name: str
    model_type: str
    map50: Optional[float] = None
    is_default: bool
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "protected_namespaces": (),
    }


class ModelVersionResponse(ProjectBaseModel):
    """模型版本详情"""
    id: int
    scene_id: int
    scene_name: Optional[str] = None
    training_task_id: Optional[int] = None
    version: str
    model_name: str
    model_type: str
    status: str
    model_path: str
    minio_url: Optional[str] = None
    map50: Optional[float] = None
    map50_95: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    per_class_ap: Optional[dict] = None
    description: Optional[str] = None
    file_size: Optional[int] = None
    is_default: bool
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "protected_namespaces": (),
    }


class ModelVersionCreate(ProjectBaseModel):
    """手动上传模型版本"""
    scene_id: int
    version: str = Field(..., description="版本号")
    model_name: str = Field(..., description="模型名称")
    model_type: str = Field(default="yolov11n", description="模型类型")
    description: Optional[str] = None

    model_config = {
        "protected_namespaces": (),
    }


# ══════════════════════════════════════════════════════════════
# 四、智能体对话
# ══════════════════════════════════════════════════════════════

class ChatSessionCreate(ProjectBaseModel):
    """创建对话会话"""
    title: Optional[str] = None


class ChatSessionResponse(ProjectBaseModel):
    """对话会话响应"""
    id: int
    session_uuid: str
    title: Optional[str] = None
    status: str
    message_count: int
    last_message_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMessageRequest(ProjectBaseModel):
    """发送消息请求"""
    session_id: Optional[int] = Field(None, description="会话 ID（为空则自动创建新会话）")
    content: str = Field(..., min_length=1, max_length=5000, description="消息内容")


class ChatMessageResponse(ProjectBaseModel):
    """对话消息响应"""
    id: int
    session_id: int
    role: str
    content: str
    agent_used: Optional[str] = None
    tool_calls: Optional[list] = None
    tool_result: Optional[str] = None
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatHistoryResponse(ProjectBaseModel):
    """对话历史响应（含会话信息和消息列表）"""
    session: ChatSessionResponse
    messages: list[ChatMessageResponse] = []


# ══════════════════════════════════════════════════════════════
# 五、系统运维
# ══════════════════════════════════════════════════════════════

class OperationLogResponse(ProjectBaseModel):
    """操作日志响应"""
    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    module: str
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    description: Optional[str] = None
    ip_address: Optional[str] = None
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
# 六、通用模型
# ══════════════════════════════════════════════════════════════

class ApiResponse(ProjectBaseModel):
    """统一 API 响应"""
    code: int = 200
    message: str = "success"
    data: Optional[dict | list] = None


class PageParams(ProjectBaseModel):
    """分页查询参数"""
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


class PageResponse(ProjectBaseModel):
    """分页响应"""
    total: int
    page: int
    page_size: int
    total_pages: int
    items: list


class HealthResponse(ProjectBaseModel):
    """健康检查响应"""
    status: str = "healthy"
    app_name: str
    version: str
    database: Optional[str] = None
    redis: Optional[str] = None
    minio: Optional[str] = None
