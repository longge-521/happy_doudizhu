from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.upload.entities import UploadedFile

class UploadedFileRepository(ABC):
    """已上传文件仓储的抽象接口契约。"""

    @abstractmethod
    def save(self, uploaded_file: UploadedFile) -> UploadedFile:
        """保存已上传文件记录，支持创建或更新"""
        pass

    @abstractmethod
    def find_by_filename(self, filename: str) -> Optional[UploadedFile]:
        """根据文件名查找记录，用于排重校验"""
        pass

    @abstractmethod
    def find_all(self) -> List[UploadedFile]:
        """获取所有已上传文件列表记录"""
        pass

    @abstractmethod
    def delete_by_id(self, file_id: int) -> Optional[UploadedFile]:
        """根据 ID 删除已上传文件记录，返回被删除的实体"""
        pass

