# backend/tests/test_profile_update.py
import os
import io
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app
from app.infrastructure.database.session import get_db
from app.domain.game.entities import PlayerProfile
from app.infrastructure.auth import create_game_auth_token


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture(autouse=True)
def override_db_dependency(mock_db):
    def get_db_override():
        yield mock_db
    app.dependency_overrides[get_db] = get_db_override
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def mock_audit_log():
    with patch("app.application.audit_log.audit_log_app_service.AuditLogAppService.record_log") as mock_record:
        yield mock_record


def test_update_player_profile_success(mock_db):
    client = TestClient(app)
    token = create_game_auth_token("player123")
    
    mock_profile = PlayerProfile(
        player_id="player123",
        nickname="NewNick",
        avatar_url="/api/uploads/avatars/avatar_player123_abc.png",
        beans=12000,
        total_games=10,
        wins=6,
    )

    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo.get_or_create_profile.return_value = mock_profile
        mock_repo_class.return_value = mock_repo

        response = client.post(
            "/api/game/profile/player123/update",
            json={
                "nickname": "NewNick",
                "avatar_url": "/api/uploads/avatars/avatar_player123_abc.png"
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["nickname"] == "NewNick"
        assert data["avatar_url"] == "/api/uploads/avatars/avatar_player123_abc.png"
        
        mock_repo.update_nickname.assert_called_once_with("player123", "NewNick")
        mock_repo.update_avatar_url.assert_called_once_with("player123", "/api/uploads/avatars/avatar_player123_abc.png")


def test_update_player_profile_validation_error(mock_db):
    client = TestClient(app)
    token = create_game_auth_token("player123")

    # 昵称过长（大于 20 字符）
    response = client.post(
        "/api/game/profile/player123/update",
        json={"nickname": "a" * 21},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_upload_player_avatar_success(mock_db):
    client = TestClient(app)
    token = create_game_auth_token("player123")

    # 模拟 open() 保存文件
    with patch("app.interfaces.api.game_routes.open", create=True) as mock_open, \
         patch("app.interfaces.api.game_routes.os.makedirs") as mock_makedirs, \
         patch("app.interfaces.api.game_routes.os.path.exists", return_value=True):
        
        # 准备一个内存里的模拟图片文件
        file_data = b"\x89PNG\r\n\x1a\nfake-image-bytes"
        file_obj = io.BytesIO(file_data)
        
        response = client.post(
            "/api/game/profile/player123/upload-avatar",
            files={"file": ("test.png", file_obj, "image/png")},
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["avatar_url"].startswith("/api/uploads/avatars/avatar_player123_")
        assert data["avatar_url"].endswith(".png")


def test_upload_player_avatar_invalid_mime(mock_db):
    client = TestClient(app)
    token = create_game_auth_token("player123")

    file_obj = io.BytesIO(b"some-text-data")
    
    response = client.post(
        "/api/game/profile/player123/upload-avatar",
        files={"file": ("test.txt", file_obj, "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert response.status_code == 400
    assert response.json()["detail"] == "只允许上传图片格式的文件"


def test_upload_player_avatar_rejects_oversized_file(mock_db):
    client = TestClient(app)
    token = create_game_auth_token("player123")
    oversized = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024 + 1))

    response = client.post(
        "/api/game/profile/player123/upload-avatar",
        files={"file": ("big.png", oversized, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "头像文件不能超过" in response.json()["detail"]


def test_upload_player_avatar_rejects_fake_image_payload(mock_db):
    client = TestClient(app)
    token = create_game_auth_token("player123")
    fake_image = io.BytesIO(b"not-an-image")

    response = client.post(
        "/api/game/profile/player123/upload-avatar",
        files={"file": ("fake.png", fake_image, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "头像文件内容不是支持的图片格式"


def test_update_player_password_success(mock_db):
    client = TestClient(app)
    token = create_game_auth_token("player123")

    from app.infrastructure.database.models import UserORM
    from app.infrastructure.auth import hash_password
    stored_hash = hash_password("old-pwd-123")
    mock_user = UserORM(
        player_id="player123",
        password=stored_hash
    )

    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo.get_user_by_player_id.return_value = mock_user
        mock_repo_class.return_value = mock_repo

        response = client.post(
            "/api/game/profile/player123/password",
            json={
                "old_password": "old-pwd-123",
                "new_password": "new-pwd-456"
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "密码修改成功" in data["message"]
        
        mock_repo.get_user_by_player_id.assert_called_once_with("player123")
        mock_repo.update_user_password.assert_called_once()


def test_update_player_password_wrong_old(mock_db):
    client = TestClient(app)
    token = create_game_auth_token("player123")

    from app.infrastructure.database.models import UserORM
    from app.infrastructure.auth import hash_password
    stored_hash = hash_password("old-pwd-123")
    mock_user = UserORM(
        player_id="player123",
        password=stored_hash
    )

    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo.get_user_by_player_id.return_value = mock_user
        mock_repo_class.return_value = mock_repo

        response = client.post(
            "/api/game/profile/player123/password",
            json={
                "old_password": "wrong-old-pwd",
                "new_password": "new-pwd-456"
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400
        assert "旧密码输入错误" in response.json()["detail"]


def test_update_player_password_same_old_new(mock_db):
    client = TestClient(app)
    token = create_game_auth_token("player123")

    from app.infrastructure.database.models import UserORM
    from app.infrastructure.auth import hash_password
    stored_hash = hash_password("old-pwd-123")
    mock_user = UserORM(
        player_id="player123",
        password=stored_hash
    )

    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo.get_user_by_player_id.return_value = mock_user
        mock_repo_class.return_value = mock_repo

        response = client.post(
            "/api/game/profile/player123/password",
            json={
                "old_password": "old-pwd-123",
                "new_password": "old-pwd-123"
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400
        assert "新密码不能与旧密码相同" in response.json()["detail"]
