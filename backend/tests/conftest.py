"""测试库隔离：每个测试模块文件头指定了自己的 SZT_DB_PATH，
此 module 级 autouse fixture 在各模块的 client fixture 之前重置引擎单例，
确保 lifespan 建表/灌数落到该模块自己的临时库。"""
import pytest


@pytest.fixture(scope="module", autouse=True)
def _reset_db_engine():
    from app.database import reset_engine

    reset_engine()
    yield
