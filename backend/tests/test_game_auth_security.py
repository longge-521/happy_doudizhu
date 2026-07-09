import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from main import app
from app.infrastructure.auth import create_game_auth_token

client = TestClient(app)


def test_register_password_min_length():
    # 测试注册时新密码长度小于 6 会被拦截（FastAPI/Pydantic 验证）
    response = client.post("/api/game/auth/register", json={
        "username": "new_user_1",
        "password": "12345",  # 5 位，应被拒
        "nickname": "Nick"
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "密码长度至少为 6 位"


def test_login_failure_uniform_message():
    # 测试登录失败时统一返回“用户名或密码不正确”
    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        
        # 1. 模拟账号不存在
        mock_repo.get_user_by_username.return_value = None
        response1 = client.post("/api/game/auth/login", json={
            "username": "non_exist",
            "password": "some_password"
        })
        assert response1.status_code == 400
        assert response1.json()["detail"] == "用户名或密码不正确"
        
        # 2. 模拟密码错误
        mock_user = MagicMock()
        mock_user.password = "hashed_pass"
        mock_repo.get_user_by_username.return_value = mock_user
        
        with patch("app.interfaces.api.game_routes.verify_password", return_value=False):
            response2 = client.post("/api/game/auth/login", json={
                "username": "exist_user",
                "password": "wrong_password"
            })
            assert response2.status_code == 400
            assert response2.json()["detail"] == "用户名或密码不正确"


def test_update_password_min_length_enforcement():
    # 测试修改密码时，新密码小于 6 会被拦截
    token = create_game_auth_token("player_test_pwd")
    response = client.post(
        "/api/game/profile/player_test_pwd/password",
        json={
            "old_password": "old_pass_456",
            "new_password": "123"  # 3 位，应被拒
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "新密码长度至少为 6 位"
