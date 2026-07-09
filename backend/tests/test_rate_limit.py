import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from main import app


@pytest.mark.asyncio
async def test_rate_limit_ip_blocking():
    """测试 IP 维度限流：超出容量后返回 429 报错，且带有中文友好提示"""
    client = TestClient(app)
    
    # 模拟 Redis 返回 0 (限流拦截)
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = 0
    
    with patch("app.infrastructure.redis_client.redis_client.eval", new=mock_redis.eval):
        # 1. 尝试登录，由于 Redis 模拟拦截，直接触发 IP 限流
        response = client.post(
            "/api/game/auth/login",
            json={"username": "testuser", "password": "password123"}
        )
        assert response.status_code == 429
        assert "您的操作过于频繁" in response.json()["detail"]


@pytest.mark.asyncio
async def test_rate_limit_user_blocking():
    """测试账号维度限流：当 IP 维度通过但账号限流拦截时，返回对应 429 提示"""
    client = TestClient(app)
    
    # 第一次评估（IP 限流校验）返回 1（通过），第二次评估（账号限流校验）返回 0（拦截）
    mock_redis = AsyncMock()
    mock_redis.eval.side_effect = [1, 0]
    
    with patch("app.infrastructure.redis_client.redis_client.eval", new=mock_redis.eval):
        response = client.post(
            "/api/game/auth/login",
            json={"username": "testuser", "password": "password123"}
        )
        assert response.status_code == 429
        assert "此账号操作过于频繁" in response.json()["detail"]


@pytest.mark.asyncio
async def test_rate_limit_graceful_fallback():
    """测试灾备降级：当 Redis 出现连接异常时，限流模块应捕获错误并优雅放行，不阻断业务"""
    client = TestClient(app)
    
    # 模拟 Redis 执行 eval 报错（例如 ConnectionError）
    mock_redis = AsyncMock()
    mock_redis.eval.side_effect = Exception("Redis connection refused")
    
    # 模拟数据库查询不到用户，以便接口最终返回 400 (用户名密码错误) 而非 500 (限流崩溃) 或 429
    mock_db = MagicMock()
    mock_db.get_user_by_username.return_value = None
    
    with patch("app.infrastructure.redis_client.redis_client.eval", new=mock_redis.eval), \
         patch("app.infrastructure.database.game_repository.SQLGameRepository.get_user_by_username", new=mock_db.get_user_by_username):
        
        response = client.post(
            "/api/game/auth/login",
            json={"username": "testuser", "password": "password123"}
        )
        # 如果限流优雅降级了，它会透传到后面的业务校验，因为查不到用户而返回 400（不是 429 限流也不是 500 崩溃）
        assert response.status_code == 400
        assert "用户名或密码不正确" in response.json()["detail"]
