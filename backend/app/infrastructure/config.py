import os
import uuid
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 动态定位 backend/ 目录
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """系统全局配置类。

    支持自动从系统环境变量 and .env 文件中加载，类型不匹配时自动抛出异常。
    """

    # 1. 基础配置
    INSTANCE_ID: str = Field(
        default_factory=lambda: f"inst-{uuid.uuid4().hex[:8]}",
        description="应用实例唯一标识ID"
    )
    PORT: int = Field(default=18088, description="后端服务运行端口")
    APP_ENV: str = Field(
        default="development", description="运行环境：development/production"
    )
    AUTO_INIT_DB: Optional[bool] = Field(
        default=None, description="是否自动初始化数据库表结构"
    )

    # 2. MySQL 数据库配置
    DB_HOST: str = Field(default="127.0.0.1")
    DB_PORT: int = Field(default=3306)
    DB_USER: str = Field(default="root")
    DB_PASSWORD: str = Field(default="123456")
    DB_NAME: str = Field(default="happy_doudizhu")

    # 3. Redis 缓存配置
    REDIS_HOST: str = Field(default="127.0.0.1")
    REDIS_PORT: int = Field(default=6379)
    REDIS_PASSWORD: Optional[str] = Field(default=None)
    REDIS_DB: int = Field(default=0)

    # 4. RabbitMQ 消息队列配置
    MQ_HOST: str = Field(default="127.0.0.1")
    MQ_PORT: int = Field(default=5672)
    MQ_USER: str = Field(default="guest")
    MQ_PASSWORD: str = Field(default="guest")
    MQ_EXCHANGE_NAME: str = Field(
        default="happy_doudizhu_site_messages_exchange"
    )

    # 5. 安全与凭证配置
    API_TOKEN: Optional[str] = Field(
        default=None, description="敏感接口安全校验Token"
    )
    GAME_AUTH_SECRET: Optional[str] = Field(
        default=None, description="游戏访问令牌签名密钥；生产环境必须显式配置"
    )
    GAME_AUTH_TOKEN_TTL_SECONDS: int = Field(
        default=7 * 24 * 3600, description="Token生命周期(秒)"
    )
    DISTRIBUTED_MODE: bool = Field(
        default=False, description="是否启用分布式游戏架构模式"
    )

    # 6. 大文件上传配置
    UPLOAD_MAX_CHUNK_BYTES: int = Field(
        default=4 * 1024 * 1024, description="单分片上传上限"
    )
    UPLOAD_MAX_BYTES: int = Field(
        default=512 * 1024 * 1024, description="单文件总大小限制"
    )
    UPLOAD_DIR: Optional[str] = Field(default=None, description="文件存储主目录")
    TEMP_DIR: Optional[str] = Field(default=None, description="临时上传分片目录")

    # 声明配置解析行为：支持读取 .env 文件
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略 .env 文件里多余 of 未声明变量
    )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.strip().lower() in {"prod", "production"}

    def validate_production_settings(self) -> None:
        if not self.is_production:
            return
        if not self.GAME_AUTH_SECRET or len(self.GAME_AUTH_SECRET) < 32:
            raise RuntimeError(
                "GAME_AUTH_SECRET must be explicitly configured with at least "
                "32 characters in production"
            )

    @property
    def should_auto_init_db(self) -> bool:
        if self.AUTO_INIT_DB is not None:
            return self.AUTO_INIT_DB
        return not self.is_production


# 实例化全局单例配置
settings = Settings()
