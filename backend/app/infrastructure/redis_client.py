import os
import logging
from redis.asyncio import Redis, ConnectionPool
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("hmp_ws_service")

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# 创建异步连接池
pool = ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=REDIS_DB,
    decode_responses=True,
    socket_connect_timeout=2.0
)

redis_client = Redis(connection_pool=pool)

async def is_query_debounced(key: str, expire_seconds: int = 3) -> bool:
    """
    判断查询是否需要防抖。
    使用 Redis 的 SET key 1 EX expire_seconds NX 原子操作。
    若设置成功（返回 True），说明之前没有这个缓存，无需防抖；
    若设置失败（返回 None/False），说明已存在缓存，需要防抖，并且通过 EXPIRE 顺延过期时间实现滑动窗口。
    若 Redis 连接异常，则返回 False（不防抖，优雅降级）。
    """
    try:
        # SETEX with NX
        result = await redis_client.set(key, "1", ex=expire_seconds, nx=True)
        if result:
            return False
            
        # 触发防抖：顺延过期时间
        await redis_client.expire(key, expire_seconds)
        return True
    except Exception as e:
        logger.warning(f"Redis debounce failed (degraded to write log): {e}")
        return False
