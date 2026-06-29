import base64
import hashlib
import hmac
import json
import os
import logging
import secrets
import time
from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader, APIKeyQuery

logger = logging.getLogger("hmp_ws_service")

# 从环境变量中获取安全令牌，默认可为空以维持开发兼容性
API_TOKEN = os.getenv("API_TOKEN", "")

# 声明凭证获取策略
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)
api_key_query = APIKeyQuery(name="token", auto_error=False)
game_auth_query = APIKeyQuery(name="auth_token", auto_error=False)

PASSWORD_HASH_PREFIX = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 260000
GAME_AUTH_TOKEN_TTL_SECONDS = int(os.getenv("GAME_AUTH_TOKEN_TTL_SECONDS", str(7 * 24 * 3600)))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _game_auth_secret() -> bytes:
    secret = os.getenv("GAME_AUTH_SECRET") or API_TOKEN or os.getenv("API_TOKEN")
    if not secret and _is_production_env():
        raise RuntimeError("GAME_AUTH_SECRET or API_TOKEN must be configured in production")
    if not secret:
        secret = "hmp-dev-game-auth-secret"
    return secret.encode("utf-8")


def _is_production_env() -> bool:
    return os.getenv("APP_ENV", "").lower() in {"prod", "production"}


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization[7:]
    return authorization


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"{PASSWORD_HASH_PREFIX}${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_password: str) -> bool:
    parts = stored_password.split("$")
    if len(parts) != 4 or parts[0] != PASSWORD_HASH_PREFIX:
        return hmac.compare_digest(stored_password, password)

    _, iterations_raw, salt, expected_digest = parts
    try:
        iterations = int(iterations_raw)
    except ValueError:
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        iterations,
    ).hex()
    return hmac.compare_digest(digest, expected_digest)


def create_game_auth_token(player_id: str, ttl_seconds: int = GAME_AUTH_TOKEN_TTL_SECONDS) -> str:
    payload = {
        "player_id": player_id,
        "exp": int(time.time()) + ttl_seconds,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded_payload = _b64url_encode(payload_json)
    signature = hmac.new(_game_auth_secret(), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded_payload}.{_b64url_encode(signature)}"


def verify_game_auth_token(token: str) -> str:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            _game_auth_secret(),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        supplied_signature = _b64url_decode(encoded_signature)
        if not hmac.compare_digest(expected_signature, supplied_signature):
            raise ValueError("bad signature")

        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("expired token")
        player_id = payload.get("player_id")
        if not player_id:
            raise ValueError("missing player_id")
        return str(player_id)
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing game auth token")


def require_game_player_id(
    authorization: str = Security(api_key_header),
    auth_token: str = Security(game_auth_query),
) -> str:
    token = _extract_bearer_token(authorization) or auth_token
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing game auth token")
    return verify_game_auth_token(token)

def verify_token(
    request: Request, 
    authorization: str = Security(api_key_header), 
    token: str = Security(api_key_query)
) -> bool:
    """
    HTTP 路由依赖注入验证方法。
    若环境变量未配置 API_TOKEN，则不进行拦截（以兼容开发与本地调试环境）。
    如果配置了，客户端必须提供匹配的 Bearer Token 或 Query Token 参数。
    """
    if not API_TOKEN and not _is_production_env():
        return True
    if not API_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: API_TOKEN must be configured in production"
        )
        
    extracted_token = None
    if authorization:
        if authorization.lower().startswith("bearer "):
            extracted_token = authorization[7:]
        else:
            extracted_token = authorization
            
    if not extracted_token and token:
        extracted_token = token
        
    if not extracted_token or extracted_token != API_TOKEN:
        logger.warning("Unauthenticated HTTP access request rejected.")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing API_TOKEN"
        )
    return True

def verify_ws_token(query_params) -> bool:
    """
    WebSocket 连接校验辅助方法。
    """
    if not API_TOKEN and not _is_production_env():
        return True
    if not API_TOKEN:
        logger.warning("Rejected WebSocket access because API_TOKEN is missing in production.")
        return False
    
    token = query_params.get("token")
    return token == API_TOKEN
