# backend/tests/test_game_api.py
import pytest
import datetime
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app
from app.infrastructure.database.session import get_db
from app.domain.game.entities import PlayerProfile, GameRecord


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
    # 模拟审计日志服务，防止测试在没有真实数据库连接时触发审计日志写入失败
    with patch("app.application.audit_log.audit_log_app_service.AuditLogAppService.record_log") as mock_record:
        yield mock_record


def test_get_player_profile(mock_db):
    client = TestClient(app)
    mock_profile = PlayerProfile(
        player_id="player123",
        nickname="TestNick",
        beans=12000,
        total_games=10,
        wins=6
    )

    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo.get_or_create_profile.return_value = mock_profile
        mock_repo_class.return_value = mock_repo

        response = client.get("/api/game/profile/player123")
        assert response.status_code == 200
        data = response.json()
        assert data["player_id"] == "player123"
        assert data["nickname"] == "TestNick"
        assert data["beans"] == 12000
        assert data["total_games"] == 10
        assert data["wins"] == 6
        assert data["win_rate"] == 0.6
        mock_repo.get_or_create_profile.assert_called_once_with("player123", "player123")


def test_get_game_history(mock_db):
    client = TestClient(app)
    now = datetime.datetime.now()
    mock_records = [
        GameRecord(
            room_id="room1",
            player_id="player123",
            role="landlord",
            result="win",
            score_change=3000,
            multiplier=3,
            created_at=now
        ),
        GameRecord(
            room_id="room2",
            player_id="player123",
            role="farmer",
            result="lose",
            score_change=-1000,
            multiplier=1,
            created_at=now
        )
    ]

    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo.get_history.return_value = mock_records
        mock_repo_class.return_value = mock_repo

        response = client.get("/api/game/history/player123?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["room_id"] == "room1"
        assert data[0]["role"] == "landlord"
        assert data[0]["result"] == "win"
        assert data[0]["score_change"] == 3000
        assert data[0]["multiplier"] == 3
        assert data[0]["created_at"] == now.isoformat()
        mock_repo.get_history.assert_called_once_with("player123", 5)


def test_get_leaderboard(mock_db):
    client = TestClient(app)
    mock_profiles = [
        PlayerProfile(player_id="p1", nickname="Nick1", beans=50000, total_games=20, wins=15),
        PlayerProfile(player_id="p2", nickname="Nick2", beans=30000, total_games=10, wins=5),
    ]

    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo.get_leaderboard.return_value = mock_profiles
        mock_repo_class.return_value = mock_repo

        response = client.get("/api/game/leaderboard?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["rank"] == 1
        assert data[0]["player_id"] == "p1"
        assert data[0]["beans"] == 50000
        assert data[0]["win_rate"] == 0.75
        assert data[1]["rank"] == 2
        assert data[1]["player_id"] == "p2"
        assert data[1]["beans"] == 30000
        assert data[1]["win_rate"] == 0.50
        mock_repo.get_leaderboard.assert_called_once_with(10)


def test_register_user(mock_db):
    client = TestClient(app)
    mock_user = MagicMock()
    mock_user.player_id = "player123"
    mock_user.username = "testuser"
    mock_profile = MagicMock()
    mock_profile.nickname = "TestNick"

    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo.get_user_by_username.return_value = None
        mock_repo.create_user_and_profile.return_value = (mock_user, mock_profile)
        mock_repo_class.return_value = mock_repo

        response = client.post("/api/game/auth/register", json={
            "username": "testuser",
            "password": "password123",
            "nickname": "TestNick"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["player_id"] == "player123"
        assert data["nickname"] == "TestNick"
        assert data["username"] == "testuser"
        mock_repo.get_user_by_username.assert_called_once_with("testuser")
        mock_repo.create_user_and_profile.assert_called_once_with("testuser", "password123", "TestNick")


def test_login_user(mock_db):
    client = TestClient(app)
    mock_user = MagicMock()
    mock_user.player_id = "player123"
    mock_user.username = "testuser"
    mock_user.password = "password123"
    mock_profile = PlayerProfile(
        player_id="player123",
        nickname="TestNick",
        beans=12000,
        total_games=10,
        wins=6
    )

    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo.get_user_by_username.return_value = mock_user
        mock_repo.get_or_create_profile.return_value = mock_profile
        mock_repo_class.return_value = mock_repo

        response = client.post("/api/game/auth/login", json={
            "username": "testuser",
            "password": "password123"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["player_id"] == "player123"
        assert data["nickname"] == "TestNick"
        assert data["username"] == "testuser"
        mock_repo.get_user_by_username.assert_called_once_with("testuser")


def test_update_player_beans(mock_db):
    client = TestClient(app)
    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_profile = MagicMock()
        mock_profile.beans = 25000
        mock_repo.get_or_create_profile.return_value = mock_profile
        mock_repo_class.return_value = mock_repo
        
        # 测试成功设置欢乐豆
        response = client.post("/api/game/profile/player123/beans", json={"beans": 25000})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["beans"] == 25000
        mock_repo.update_beans.assert_called_once_with("player123", 25000)


