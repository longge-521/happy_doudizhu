import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from main import app
from app.infrastructure.database.session import get_db
from app.domain.message.entities import SiteMessage
from datetime import datetime

# Mock 数据库
@pytest.fixture
def mock_db():
    db = MagicMock()
    return db

# Mock MQ 适配器
@pytest.fixture
def mock_mq():
    mq = MagicMock()
    return mq

def test_send_message_api(mock_db, mock_mq, monkeypatch):
    # 覆盖 get_db 依赖注入
    app.dependency_overrides[get_db] = lambda: mock_db
    
    # Mock SiteMessage 实体返回
    mock_msg = SiteMessage(
        id=101,
        sender="test_sender",
        receiver="test_receiver",
        content="hello test",
        is_read=0,
        created_at=datetime.now()
    )
    
    # Mock 仓储的 save 方法
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.refresh = MagicMock()
    
    # Mock RabbitMQ 发送
    app.state.mq_adapter = mock_mq
    mock_mq.publish_broadcast = MagicMock()
    
    # 临时禁用 Token 校验
    from app.infrastructure import auth
    monkeypatch.setattr(auth, "API_TOKEN", "")
    
    client = TestClient(app)
    
    # 1. 正常请求
    payload = {
        "sender": "test_sender",
        "receiver": "test_receiver",
        "content": "hello test"
    }
    response = client.post("/api/messages/send", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert "id" in response.json()

    # 2. 字段校验不通过 (缺失 receiver)
    payload_invalid = {
        "sender": "test_sender",
        "content": "hello test"
    }
    response = client.post("/api/messages/send", json=payload_invalid)
    assert response.status_code == 422 # Pydantic validation error

    # 3. 字段校验不通过 (content 长度过长)
    payload_too_long = {
        "sender": "test_sender",
        "receiver": "test_receiver",
        "content": "x" * 1001 # 限制为 1000
    }
    response = client.post("/api/messages/send", json=payload_too_long)
    assert response.status_code == 422 # Pydantic validation error

    # 清理 overrides
    app.dependency_overrides.clear()
