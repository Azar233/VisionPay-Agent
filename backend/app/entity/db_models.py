"""
数据库模型定义

表结构总览：
  用户权限：users, roles, permissions, user_roles, role_permissions
  检测业务：detection_scenes, detection_tasks, detection_results
  模型管理：training_tasks, training_metrics, model_versions
  智能体：  chat_sessions, chat_messages
  系统运维：operation_logs
  商品价格：product_prices
  模拟支付：mock_payment_orders
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey,
    JSON, Text, Boolean, Enum, Table, BigInteger, Numeric,
    Index, UniqueConstraint, text,
)
from sqlalchemy.orm import relationship

from app.database.session import Base


# ══════════════════════════════════════════════════════════════
# 一、用户与权限（RBAC）
# ══════════════════════════════════════════════════════════════

class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True, comment="用户名")
    nickname = Column(String(50), nullable=True, comment="展示昵称，可重复、可修改")
    email = Column(String(100), unique=True, nullable=False, index=True, comment="邮箱")
    hashed_password = Column(String(255), nullable=False, comment="加密密码")
    customer_mode_password_hash = Column(
        String(255),
        nullable=True,
        comment="顾客展示模式退出密码哈希；为空时使用系统默认密码",
    )
    phone = Column(String(20), nullable=True, comment="手机号")
    avatar = Column(String(500), nullable=True, comment="头像 URL")
    agent_custom_instructions = Column(
        Text,
        nullable=True,
        comment="用户级 Agent 响应偏好，仅用于语言、语气和输出格式",
    )
    is_active = Column(Boolean, default=True, comment="是否启用")
    is_superuser = Column(Boolean, default=False, comment="是否超级管理员")
    last_login_at = Column(DateTime, nullable=True, comment="最后登录时间")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关联
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    detection_tasks = relationship("DetectionTask", back_populates="user")
    training_tasks = relationship("TrainingTask", back_populates="user")
    dataset_versions_created = relationship(
        "DatasetVersion",
        back_populates="creator",
        foreign_keys="DatasetVersion.created_by",
    )
    chat_sessions = relationship("ChatSession", back_populates="user")
    operation_logs = relationship("OperationLog", back_populates="user")


class Role(Base):
    """角色表"""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, comment="角色标识，如 admin/operator/viewer")
    display_name = Column(String(100), nullable=False, comment="角色显示名，如 管理员/操作员/访客")
    description = Column(String(500), nullable=True, comment="角色描述")
    is_system = Column(Boolean, default=False, comment="是否系统内置角色（不可删除）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    # 关联
    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    """权限表"""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(100), unique=True, nullable=False, comment="权限编码，如 detection:task:create")
    name = Column(String(100), nullable=False, comment="权限名称")
    module = Column(String(50), nullable=False, comment="所属模块：auth/detection/training/agent/system")
    description = Column(String(500), nullable=True, comment="权限描述")

    # 关联
    role_permissions = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")


class UserRole(Base):
    """用户-角色关联表（多对多）"""
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")


class RolePermission(Base):
    """角色-权限关联表（多对多）"""
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"), nullable=False, index=True)

    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")


# ══════════════════════════════════════════════════════════════
# 二、检测业务
# ══════════════════════════════════════════════════════════════

class DetectionScene(Base):
    """检测场景配置表
    每个小组/业务方向一个场景，如：遥感检测、工业缺陷、农业病害等
    场景决定了使用哪个模型、检测哪些类别
    """
    __tablename__ = "detection_scenes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, comment="场景标识，如 remote_sensing")
    display_name = Column(String(100), nullable=False, comment="场景显示名，如 遥感目标检测")
    description = Column(Text, nullable=True, comment="场景描述")
    category = Column(String(50), nullable=False, comment="场景分类：agriculture/industry/remote_sensing/medical/traffic")
    class_names = Column(JSON, nullable=False, comment="类别列表，如 [\"airplane\",\"storage-tank\"]")
    class_names_cn = Column(JSON, nullable=True, comment="类别中文名映射，如 {\"airplane\":\"飞机\"}")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, comment="创建人")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联
    detection_tasks = relationship("DetectionTask", back_populates="scene")
    model_versions = relationship("ModelVersion", back_populates="scene")
    training_tasks = relationship("TrainingTask", back_populates="scene")
    dataset_versions = relationship("DatasetVersion", back_populates="scene")


class DetectionTask(Base):
    """检测任务表 — 每次检测操作生成一条任务记录"""
    __tablename__ = "detection_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="操作用户")
    scene_id = Column(Integer, ForeignKey("detection_scenes.id"), nullable=False, index=True, comment="使用的检测场景")
    model_version_id = Column(Integer, ForeignKey("model_versions.id"), nullable=True, comment="使用的模型版本")
    task_type = Column(String(20), nullable=False, comment="检测类型：single/batch/folder/video/camera")
    status = Column(String(20), default="pending", comment="状态：pending/processing/completed/failed")

    # 检测统计
    total_images = Column(Integer, default=0, comment="处理图像总数")
    total_objects = Column(Integer, default=0, comment="检测到目标总数")
    total_inference_time = Column(Float, default=0, comment="总推理耗时（ms）")

    # 检测参数
    conf_threshold = Column(Float, default=0.25, comment="置信度阈值")
    iou_threshold = Column(Float, default=0.45, comment="NMS IoU 阈值")
    image_size = Column(Integer, default=640, comment="推理图像尺寸")

    # 错误信息
    error_message = Column(Text, nullable=True, comment="失败时的错误信息")

    # 分析与建议（AI 生成）
    analysis_report = Column(Text, nullable=True, comment="分析报告（Markdown 格式）")
    analysis_suggestion = Column(Text, nullable=True, comment="专业建议")
    risk_level = Column(String(20), nullable=True, comment="风险等级：low/medium/high/critical")
    analyzed_at = Column(DateTime, nullable=True, comment="分析完成时间")

    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")

    # 关联
    user = relationship("User", back_populates="detection_tasks")
    scene = relationship("DetectionScene", back_populates="detection_tasks")
    model_version = relationship("ModelVersion", back_populates="detection_tasks")
    results = relationship("DetectionResult", back_populates="task", cascade="all, delete-orphan")


class DetectionResult(Base):
    """检测结果表 — 每张图像中每个检测到的目标一条记录"""
    __tablename__ = "detection_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("detection_tasks.id"), nullable=False, index=True, comment="所属检测任务")
    image_path = Column(String(500), nullable=False, comment="原始图像路径")
    annotated_image_url = Column(String(500), nullable=True, comment="标注图像 MinIO URL")

    # 单个目标信息
    class_name = Column(String(50), nullable=False, index=True, comment="类别名称")
    class_name_cn = Column(String(50), nullable=True, comment="类别中文名")
    class_id = Column(Integer, nullable=False, comment="类别 ID")
    confidence = Column(Float, nullable=False, comment="置信度 0~1")
    bbox = Column(JSON, nullable=False, comment="边界框 [x1, y1, x2, y2]")

    # 图像级信息（冗余存储，方便查询）
    inference_time = Column(Float, nullable=True, comment="该图推理耗时（ms）")
    image_width = Column(Integer, nullable=True, comment="图像宽度")
    image_height = Column(Integer, nullable=True, comment="图像高度")

    created_at = Column(DateTime, default=datetime.now)

    # 关联
    task = relationship("DetectionTask", back_populates="results")


# ══════════════════════════════════════════════════════════════
# 三、模型管理
# ══════════════════════════════════════════════════════════════

class TrainingTask(Base):
    """模型训练任务表"""
    __tablename__ = "training_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="操作用户")
    scene_id = Column(Integer, ForeignKey("detection_scenes.id"), nullable=False, index=True, comment="关联场景")
    dataset_version_id = Column(
        Integer,
        ForeignKey("dataset_versions.id"),
        nullable=True,
        index=True,
        comment="训练所使用的不可变数据集版本",
    )
    task_uuid = Column(String(100), unique=True, nullable=False, index=True, comment="任务唯一标识")
    status = Column(String(20), default="pending", comment="状态：pending/running/completed/failed/cancelled")

    # 训练配置
    model_name = Column(String(50), default="yolov11n", comment="基础模型：yolov11n/s/m/l/x")
    epochs = Column(Integer, default=100, comment="训练轮数")
    img_size = Column(Integer, default=640, comment="图像尺寸")
    batch_size = Column(Integer, default=16, comment="批次大小")
    device = Column(String(20), default="0", comment="Training device: cpu/0/0,1/0-7")
    optimizer = Column(String(20), default="SGD", comment="优化器：SGD/Adam/AdamW")
    lr0 = Column(Float, default=0.01, comment="初始学习率")
    augment_config = Column(JSON, nullable=True, comment="数据增强配置")

    # 训练进度
    current_epoch = Column(Integer, default=0, comment="当前轮数")
    progress = Column(Integer, default=0, comment="进度百分比 0~100")

    # 数据集信息
    dataset_path = Column(String(500), nullable=True, comment="数据集路径")
    dataset_size = Column(Integer, nullable=True, comment="数据集图像数量")
    data_yaml = Column(String(500), nullable=True, comment="data.yaml 路径")
    dataset_content_hash = Column(String(128), nullable=True, comment="训练时的数据集内容指纹快照")

    # 错误信息
    error_message = Column(Text, nullable=True, comment="失败错误信息")

    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    started_at = Column(DateTime, nullable=True, comment="开始训练时间")
    completed_at = Column(DateTime, nullable=True, comment="训练完成时间")

    # 关联
    user = relationship("User", back_populates="training_tasks")
    scene = relationship("DetectionScene", back_populates="training_tasks")
    dataset_version = relationship("DatasetVersion", back_populates="training_tasks")
    metrics = relationship("TrainingMetric", back_populates="task", cascade="all, delete-orphan")
    model_versions = relationship("ModelVersion", back_populates="training_task")


class TrainingMetric(Base):
    """训练指标表 — 每个 epoch 记录一条，用于绘制训练曲线"""
    __tablename__ = "training_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("training_tasks.id"), nullable=False, index=True, comment="所属训练任务")
    epoch = Column(Integer, nullable=False, comment="当前轮数")

    # 损失值
    box_loss = Column(Float, nullable=True, comment="边界框损失")
    cls_loss = Column(Float, nullable=True, comment="分类损失")
    dfl_loss = Column(Float, nullable=True, comment="DFL 损失")

    # 评估指标
    precision = Column(Float, nullable=True, comment="精确率")
    recall = Column(Float, nullable=True, comment="召回率")
    map50 = Column(Float, nullable=True, comment="mAP@0.50")
    map50_95 = Column(Float, nullable=True, comment="mAP@0.50:0.95")

    # 学习率
    lr = Column(Float, nullable=True, comment="当前学习率")

    created_at = Column(DateTime, default=datetime.now)

    # 关联
    task = relationship("TrainingTask", back_populates="metrics")


class ModelVersion(Base):
    """模型版本管理表 — 每次训练产出或手动上传的模型版本"""
    __tablename__ = "model_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scene_id = Column(Integer, ForeignKey("detection_scenes.id"), nullable=False, index=True, comment="所属场景")
    training_task_id = Column(Integer, ForeignKey("training_tasks.id"), nullable=True, comment="来源训练任务（可为空，支持手动上传）")
    dataset_version_id = Column(
        Integer,
        ForeignKey("dataset_versions.id"),
        nullable=True,
        index=True,
        comment="模型训练所使用的数据集版本",
    )

    version = Column(String(50), nullable=False, comment="版本号，如 v1.0.0")
    model_name = Column(String(100), nullable=False, comment="模型名称")
    model_type = Column(String(50), default="yolov11n", comment="模型类型：yolov11n/s/m/l/x")
    status = Column(String(20), default="active", comment="状态：active/archived/deleted")

    # 模型文件
    model_path = Column(String(500), nullable=False, comment="本地模型文件路径")
    minio_url = Column(String(500), nullable=True, comment="MinIO 存储 URL")

    # 评估指标（训练完成后写入）
    map50 = Column(Float, nullable=True, comment="mAP@0.50")
    map50_95 = Column(Float, nullable=True, comment="mAP@0.50:0.95")
    precision = Column(Float, nullable=True, comment="精确率")
    recall = Column(Float, nullable=True, comment="召回率")
    per_class_ap = Column(JSON, nullable=True, comment="各类别 AP，如 {\"airplane\":0.85,\"tank\":0.72}")

    # 元信息
    description = Column(Text, nullable=True, comment="版本描述/变更说明")
    file_size = Column(BigInteger, nullable=True, comment="模型文件大小（字节）")
    is_default = Column(Boolean, default=False, comment="是否为该场景的默认模型")

    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    # 关联
    scene = relationship("DetectionScene", back_populates="model_versions")
    training_task = relationship("TrainingTask", back_populates="model_versions")
    dataset_version = relationship("DatasetVersion", back_populates="model_versions")
    detection_tasks = relationship("DetectionTask", back_populates="model_version")


# ══════════════════════════════════════════════════════════════
# 四、数据集版本管理
# ══════════════════════════════════════════════════════════════

class DatasetVersion(Base):
    """An immutable dataset release after it leaves the draft state."""

    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint("scene_id", "version", name="uq_dataset_versions_scene_version"),
        Index(
            "uq_dataset_versions_current_scene",
            "scene_id",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current = 1"),
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    scene_id = Column(
        Integer,
        ForeignKey("detection_scenes.id"),
        nullable=False,
        index=True,
        comment="所属检测场景",
    )
    parent_id = Column(
        Integer,
        ForeignKey("dataset_versions.id"),
        nullable=True,
        index=True,
        comment="派生自哪个数据集版本",
    )
    version = Column(String(50), nullable=False, comment="数据集版本号")
    name = Column(String(150), nullable=False, comment="数据集显示名称")
    description = Column(Text, nullable=True, comment="版本说明")
    status = Column(
        String(20),
        nullable=False,
        default="draft",
        index=True,
        comment="draft/ready/archived",
    )
    is_current = Column(Boolean, nullable=False, default=False, index=True)

    storage_path = Column(String(1000), nullable=False, comment="版本根目录或对象存储 URI")
    data_yaml_path = Column(String(1000), nullable=False, comment="YOLO data.yaml 路径")
    manifest_path = Column(String(1000), nullable=True, comment="数据集 manifest 路径")
    content_hash = Column(String(128), nullable=True, index=True, comment="不可变内容指纹")

    class_count = Column(Integer, nullable=False, default=0)
    train_image_count = Column(Integer, nullable=False, default=0)
    val_image_count = Column(Integer, nullable=False, default=0)
    test_image_count = Column(Integer, nullable=False, default=0)
    train_annotation_count = Column(Integer, nullable=False, default=0)
    val_annotation_count = Column(Integer, nullable=False, default=0)
    test_annotation_count = Column(Integer, nullable=False, default=0)

    extra_metadata = Column(JSON, nullable=True, comment="来源、采集批次等扩展元数据")
    validation_report = Column(JSON, nullable=True, comment="最近一次逻辑或目录校验报告")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    validated_at = Column(DateTime, nullable=True)
    frozen_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)

    scene = relationship("DetectionScene", back_populates="dataset_versions")
    creator = relationship(
        "User",
        back_populates="dataset_versions_created",
        foreign_keys=[created_by],
    )
    parent = relationship("DatasetVersion", remote_side=[id], back_populates="children")
    children = relationship("DatasetVersion", back_populates="parent")
    classes = relationship(
        "DatasetClassMapping",
        back_populates="dataset_version",
        cascade="all, delete-orphan",
        order_by="DatasetClassMapping.class_index",
    )
    training_tasks = relationship("TrainingTask", back_populates="dataset_version")
    model_versions = relationship("ModelVersion", back_populates="dataset_version")
    images = relationship(
        "DatasetImage",
        back_populates="dataset_version",
        cascade="all, delete-orphan",
    )


class Product(Base):
    """Stable product identity shared by all dataset and model versions."""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_key = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    sku_name = Column(String(200), nullable=True)
    barcode = Column(String(100), nullable=True, unique=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    extra_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    dataset_mappings = relationship("DatasetClassMapping", back_populates="product")
    annotations = relationship("DatasetAnnotation", back_populates="product")
    prices = relationship("ProductPrice", back_populates="product")


class DatasetClassMapping(Base):
    """Snapshot the meaning of every model class index for one dataset version."""

    __tablename__ = "dataset_class_mappings"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id",
            "class_index",
            name="uq_dataset_class_mappings_version_index",
        ),
        UniqueConstraint(
            "dataset_version_id",
            "product_key",
            name="uq_dataset_class_mappings_version_product",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_version_id = Column(
        Integer,
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    class_index = Column(Integer, nullable=False, comment="YOLO class_id")
    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=True,
        index=True,
        comment="跨版本稳定商品 ID",
    )
    product_key = Column(
        String(100),
        nullable=False,
        comment="跨版本稳定的商品键，后续可关联商品主表",
    )
    category_id = Column(Integer, nullable=True, comment="兼容现有 RPC category_id")
    class_name = Column(String(200), nullable=False)
    display_name = Column(String(200), nullable=True)
    extra_metadata = Column(JSON, nullable=True)

    dataset_version = relationship("DatasetVersion", back_populates="classes")
    product = relationship("Product", back_populates="dataset_mappings")


class DatasetImage(Base):
    """File-level image index for one dataset version."""

    __tablename__ = "dataset_images"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "relative_path", name="uq_dataset_images_version_path"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_version_id = Column(
        Integer,
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    split = Column(String(20), nullable=False, index=True)
    relative_path = Column(String(1000), nullable=False)
    label_relative_path = Column(String(1000), nullable=True)
    checksum = Column(String(64), nullable=True, index=True)
    file_size = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    dataset_version = relationship("DatasetVersion", back_populates="images")
    annotations = relationship(
        "DatasetAnnotation",
        back_populates="image",
        cascade="all, delete-orphan",
    )


class DatasetAnnotation(Base):
    """Normalized YOLO annotation bound to a stable product."""

    __tablename__ = "dataset_annotations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_image_id = Column(
        Integer,
        ForeignKey("dataset_images.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    class_index = Column(Integer, nullable=False, index=True)
    x_center = Column(Float, nullable=False)
    y_center = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    source = Column(String(30), nullable=False, default="imported")

    image = relationship("DatasetImage", back_populates="annotations")
    product = relationship("Product", back_populates="annotations")


# ══════════════════════════════════════════════════════════════
# 四、智能体对话
# ══════════════════════════════════════════════════════════════

class ChatSession(Base):
    """对话会话表 — 每次对话创建一个会话"""
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="所属用户")
    session_uuid = Column(String(100), unique=True, nullable=False, index=True, comment="会话唯一标识")
    title = Column(String(200), nullable=True, comment="会话标题（取第一条消息摘要）")
    status = Column(String(20), default="active", comment="状态：active/archived")
    message_count = Column(Integer, default=0, comment="消息数量")
    last_message_at = Column(DateTime, nullable=True, comment="最后消息时间")
    context_state = Column(JSON, nullable=False, default=dict, comment="结构化会话任务状态")
    context_summary = Column(Text, nullable=True, comment="较早对话的增量摘要")
    summarized_message_id = Column(Integer, nullable=True, comment="摘要覆盖到的最后消息 ID")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联
    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan",
                            order_by="ChatMessage.created_at")


class ChatMessage(Base):
    """对话消息表 — 每条消息（用户/AI/工具调用）一条记录"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True, comment="所属会话")
    role = Column(String(20), nullable=False, comment="消息角色：user/assistant/tool/system")
    content = Column(Text, nullable=False, comment="消息内容")

    # 智能体路由信息
    agent_used = Column(String(50), nullable=True, comment="处理的 Agent：supervisor/detection/analysis/qa")
    tool_calls = Column(JSON, nullable=True, comment="工具调用记录，如 [{\"tool\":\"detect_objects\",\"args\":{...}}]")
    tool_result = Column(Text, nullable=True, comment="工具调用返回结果")

    # 元信息
    tokens_used = Column(Integer, nullable=True, comment="Token 消耗量")
    latency_ms = Column(Integer, nullable=True, comment="响应耗时（毫秒）")

    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")

    # 关联
    session = relationship("ChatSession", back_populates="messages")


class AgentHandoff(Base):
    """Human-in-the-loop handoff from an Agent to a management page."""

    __tablename__ = "agent_handoffs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    handoff_uuid = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_uuid = Column(String(100), nullable=False, index=True)
    domain = Column(String(50), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="ready_for_handoff", index=True)
    context = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class AgentPendingOperation(Base):
    """Persisted, user-confirmed Agent write operation."""

    __tablename__ = "agent_pending_operations"
    __table_args__ = (
        UniqueConstraint("operation_uuid", name="uq_agent_pending_operations_uuid"),
        UniqueConstraint(
            "user_id",
            "preview_idempotency_key",
            name="uq_agent_pending_operations_user_preview_key",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_uuid = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_uuid = Column(String(100), nullable=False, index=True)
    domain = Column(String(50), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)
    risk_level = Column(String(10), nullable=False)
    status = Column(String(30), nullable=False, default="pending", index=True)
    parameters = Column(JSON, nullable=False, default=dict)
    impact = Column(JSON, nullable=False, default=dict)
    request_fingerprint = Column(String(64), nullable=False, index=True)
    preview_idempotency_key = Column(String(100), nullable=True)
    execution_idempotency_key = Column(String(100), nullable=True, index=True)
    confirmation_token_hash = Column(String(64), nullable=False)
    token_expires_at = Column(DateTime, nullable=False, index=True)
    token_consumed_at = Column(DateTime, nullable=True)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    executed_at = Column(DateTime, nullable=True)


# ══════════════════════════════════════════════════════════════
# 五、系统运维
# ══════════════════════════════════════════════════════════════

class OperationLog(Base):
    """操作审计日志表 — 记录用户关键操作"""
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="操作用户（可为空表示系统操作）")
    username = Column(String(50), nullable=True, comment="冗余用户名，方便查询")

    # 操作信息
    module = Column(String(50), nullable=False, comment="操作模块：auth/detection/training/agent/system")
    action = Column(String(50), nullable=False, comment="操作类型：create/update/delete/login/export")
    target_type = Column(String(50), nullable=True, comment="操作对象类型：user/task/model/session")
    target_id = Column(String(100), nullable=True, comment="操作对象 ID")
    description = Column(String(500), nullable=True, comment="操作描述")

    # 请求信息
    ip_address = Column(String(50), nullable=True, comment="客户端 IP")
    user_agent = Column(String(500), nullable=True, comment="客户端 User-Agent")
    request_method = Column(String(10), nullable=True, comment="HTTP 方法")
    request_path = Column(String(500), nullable=True, comment="请求路径")

    # 结果
    status = Column(String(20), default="success", comment="操作结果：success/failure")
    error_message = Column(Text, nullable=True, comment="失败时的错误信息")

    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")

    # 关联
    user = relationship("User", back_populates="operation_logs")


# ══════════════════════════════════════════════════════════════
# 六、商品价格
# ══════════════════════════════════════════════════════════════

class ProductPrice(Base):
    """商品价格表 — 每个 category_id 对应一个 SKU 的单价"""
    __tablename__ = "product_prices"

    product = relationship("Product", back_populates="prices")
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True, unique=True, index=True)
    category_id = Column(Integer, unique=True, nullable=False, index=True, comment="检测类别 ID，对应 instances_train2019.json")
    sku_name = Column(String(100), nullable=True, comment="SKU 英文名")
    name = Column(String(100), nullable=True, comment="商品中文名")
    barcode = Column(String(50), nullable=True, comment="商品条码")
    unit_price = Column(Float, nullable=False, default=0.0, comment="单价（元）")
    currency = Column(String(10), default="CNY", comment="货币")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")


# ══════════════════════════════════════════════════════════════
# 七、模拟支付订单
# ══════════════════════════════════════════════════════════════

class MockPaymentOrder(Base):
    """仅用于演示扫码支付流程，不连接真实资金渠道。"""
    __tablename__ = "mock_payment_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_uuid = Column(String(36), unique=True, nullable=False, index=True)
    payment_token = Column(String(64), unique=True, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    currency = Column(String(10), nullable=False, default="CNY")
    amount = Column(Numeric(10, 2), nullable=False)
    item_count = Column(Integer, nullable=False)
    items_snapshot = Column(JSON, nullable=False)
    payment_method = Column(String(20), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="下单用户（当前登录账号）")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
    paid_at = Column(DateTime, nullable=True)
