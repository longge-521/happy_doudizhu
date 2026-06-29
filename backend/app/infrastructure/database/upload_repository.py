from typing import List, Optional
from sqlalchemy.orm import Session
from app.domain.upload.entities import UploadedFile
from app.domain.upload.repositories import UploadedFileRepository
from app.infrastructure.database.models import UploadedFileORM
from app.infrastructure.database.generic_repository import GenericSQLRepository

class SQLUploadedFileRepository(GenericSQLRepository[UploadedFile, UploadedFileORM], UploadedFileRepository):
    """UploadedFileRepository 契约的 MySQL 具体实现"""

    def __init__(self, db: Session):
        super().__init__(db, UploadedFileORM, UploadedFile)

    def save(self, uploaded_file: UploadedFile) -> UploadedFile:
        orm_file = self.db.query(UploadedFileORM).filter(UploadedFileORM.filename == uploaded_file.filename).first()
        if orm_file:
            orm_file.file_path = uploaded_file.file_path
            orm_file.file_size_mb = uploaded_file.file_size_mb
            orm_file.created_at = uploaded_file.created_at
            self.db.flush()
            return self._to_domain(orm_file)

        orm_file = UploadedFileORM(
            filename=uploaded_file.filename,
            file_path=uploaded_file.file_path,
            file_size_mb=uploaded_file.file_size_mb,
            created_at=uploaded_file.created_at
        )
        self.db.add(orm_file)
        self.db.flush()
        self.db.refresh(orm_file)
        uploaded_file.id = orm_file.id
        return uploaded_file

    def find_by_filename(self, filename: str) -> Optional[UploadedFile]:
        orm_file = self.db.query(UploadedFileORM).filter(UploadedFileORM.filename == filename).first()
        return self._to_domain(orm_file) if orm_file else None

    def find_all(self) -> List[UploadedFile]:
        # 重写以提供符合前端排序的按创建时间倒序列表
        orm_files = self.db.query(UploadedFileORM).order_by(UploadedFileORM.created_at.desc()).all()
        return [self._to_domain(f) for f in orm_files]
