import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base, get_db
import os

# 测试数据库
TEST_DATABASE_URL = "sqlite:///./test.db"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite 特有参数
)

TestSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


def override_get_db():
    """覆盖 FastAPI 的 get_db 依赖,使用测试数据库"""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# 导入所有模型(确保 Base.metadata 包含所有表定义)
# 注意：你需要确保你有 app.entity.db_models，如果没有请调整路径
from app.entity import db_models  # noqa: E402, F401
from main import app  # noqa: E402

# 覆盖依赖
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """创建测试数据库表(所有测试共享)"""
    Base.metadata.create_all(bind=test_engine)
    yield
    # 测试结束后清理
    Base.metadata.drop_all(bind=test_engine)
    # 显式释放连接池，解除对 SQLite 文件的占用
    test_engine.dispose()

    if os.path.exists("./test.db"):
        os.remove("./test.db")


@pytest.fixture
def client():
    """提供 FastAPI 测试客户端"""
    return TestClient(app)


@pytest.fixture
def db_session():
    """提供独立的数据库会话"""
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# 解决多个测试用例数据冲突的清理夹具 (手册补充的排错方案)
@pytest.fixture(autouse=True)
def clean_database(db_session):
    """每个测试后清理数据"""
    yield
    db_session.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        db_session.execute(table.delete())
    db_session.commit()
