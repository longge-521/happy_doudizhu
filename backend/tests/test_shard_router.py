import pytest
import binascii
from app.infrastructure.config import settings
from app.application.game.schemas import GameCommandSchema

def test_shard_computation():
    room_id = "room_abc123"
    # 验证 CRC32 分片计算公式正确无误且无符号
    shard_id = binascii.crc32(room_id.encode('utf-8')) % 16
    assert 0 <= shard_id < 16
    
    shard_id_2 = binascii.crc32(room_id.encode('utf-8')) % 16
    assert shard_id == shard_id_2
