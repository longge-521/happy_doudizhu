import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from main import app


def test_liveness_check():
    """测试 liveness_check 在任何情况下均能成功返回 200 探活成功"""
    client = TestClient(app)
    response = client.get("/api/game/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "live": True}


@pytest.mark.asyncio
async def test_readiness_check_success():
    """测试就绪度检查在所有基础设施健全的情况下返回 200"""
    client = TestClient(app)
    
    mock_db = MagicMock()
    mock_db.execute.return_value = None
    
    # 模拟正常运行的 Redis ping 和 RabbitMQ bus
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True
    
    mock_bus = MagicMock()
    mock_bus.channel = MagicMock()
    mock_bus.channel.is_closed = False
    
    with patch("sqlalchemy.orm.Session.execute", new=mock_db.execute), \
         patch("app.infrastructure.redis_client.redis_client.ping", new=mock_redis.ping):
        
        # 挂载 message_bus
        app.state.game_message_bus = mock_bus
        
        response = client.get("/api/game/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "ready": True}


@pytest.mark.asyncio
async def test_readiness_check_db_failure():
    """测试就绪度检查在数据库异常时返回 503，但 liveness 依然返回 200"""
    client = TestClient(app)
    
    # 数据库抛出异常
    mock_db = MagicMock()
    mock_db.execute.side_effect = Exception("DB Connection Lost")
    
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True
    
    mock_bus = MagicMock()
    mock_bus.channel = MagicMock()
    mock_bus.channel.is_closed = False
    
    with patch("sqlalchemy.orm.Session.execute", new=mock_db.execute), \
         patch("app.infrastructure.redis_client.redis_client.ping", new=mock_redis.ping):
        
        app.state.game_message_bus = mock_bus
        
        # 1. 验证 readiness 返回 503 隔离流量
        response_ready = client.get("/api/game/health/ready")
        assert response_ready.status_code == 503
        assert "Database check failed" in response_ready.json()["detail"]
        
        # 2. 验证 liveness 仍正常工作，防止被容器管理器无意义强制杀死重启
        response_live = client.get("/api/game/health/live")
        assert response_live.status_code == 200


@pytest.mark.asyncio
async def test_readiness_check_redis_failure():
    """测试就绪度检查在 Redis 故障时返回 503"""
    client = TestClient(app)
    
    mock_db = MagicMock()
    mock_db.execute.return_value = None
    
    # Redis ping 报错
    mock_redis = AsyncMock()
    mock_redis.ping.side_effect = Exception("Redis ping timeout")
    
    mock_bus = MagicMock()
    mock_bus.channel = MagicMock()
    mock_bus.channel.is_closed = False
    
    with patch("sqlalchemy.orm.Session.execute", new=mock_db.execute), \
         patch("app.infrastructure.redis_client.redis_client.ping", new=mock_redis.ping):
        
        app.state.game_message_bus = mock_bus
        
        response = client.get("/api/game/health/ready")
        assert response.status_code == 503
        assert "Redis check failed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_readiness_check_rabbitmq_failure():
    """测试就绪度检查在 RabbitMQ 断开时返回 503"""
    client = TestClient(app)
    
    mock_db = MagicMock()
    mock_db.execute.return_value = None
    
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True
    
    # RabbitMQ 状态置为已关闭
    mock_bus = MagicMock()
    mock_bus.channel = MagicMock()
    mock_bus.channel.is_closed = True # 连接断开
    
    with patch("sqlalchemy.orm.Session.execute", new=mock_db.execute), \
         patch("app.infrastructure.redis_client.redis_client.ping", new=mock_redis.ping):
        
        app.state.game_message_bus = mock_bus
        
        response = client.get("/api/game/health/ready")
        assert response.status_code == 503
        assert "RabbitMQ check failed" in response.json()["detail"]
