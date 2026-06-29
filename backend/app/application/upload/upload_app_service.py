import asyncio
import logging
from typing import List, Union
from app.infrastructure.storage.local_storage_adapter import LocalStorageAdapter

logger = logging.getLogger("hmp_ws_service")

class UploadAppService:
    """文件上传与合并应用服务类：组装物理存储、上传状态会话并执行合并大文件的业务用例。"""

    def __init__(self, storage_adapter: LocalStorageAdapter):
        self.storage_adapter = storage_adapter

    def get_completed_chunks(self, upload_id: str) -> List[int]:
        """获取指定上传会话中已完成的所有分片索引。"""
        return self.storage_adapter.get_completed_chunks(upload_id)

    def save_chunk(self, upload_id: str, chunk_index: int, data: Union[bytes, memoryview]):
        """保存单个分片数据。"""
        self.storage_adapter.save_chunk(upload_id, chunk_index, data)

    async def merge_chunks(self, upload_id: str, filename: str, total_chunks: int) -> str:
        """异步在线程池中调用存储适配器进行分片物理合并。"""
        return await asyncio.to_thread(
            self.storage_adapter.merge_chunks,
            upload_id,
            filename,
            total_chunks
        )

    def abort_upload(self, upload_id: str):
        """中止上传，清理临时目录。"""
        self.storage_adapter.abort_upload(upload_id)

    def cleanup_stale_uploads(self, timeout_hours: float = 2.0) -> int:
        """清理已超时的临时分片文件。"""
        return self.storage_adapter.cleanup_stale_uploads(timeout_hours)
